"""Crexi transport: plain curl_cffi with browser-impersonated TLS against the
site's own JSON hosts. No browser, no cookies, no login, no token: every
surface the scraper uses answers a bare chrome-impersonated request with
an Origin / Referer of www.crexi.com (the www host itself is an Angular
shell behind Cloudflare and is never fetched).

Egress: the pod's own IP (config.crexi_proxy(), knob CREXI_EXIT) — pod
probe 2026-11-07 (scrapers-patchright-depl-74fddd498d-rfmk6): 200 on all 14
surfaces from the pod's own IP, 2/2 datacenter and 2/2 US residential
ports, 40 searches in a burst with no 429. A block (401 / 403 / 429 or a
challenge page where JSON was expected) drops the thread's session and
moves every new session to the fallback tier (a sticky datacenter proxy
exit, config.crexi_fallback_proxy()) for CREXI_BLOCK_COOLDOWN seconds, so
the retry rides a fresh exit.

Two hosts, one shape (crexi/refs.py API_HOST): api.crexi.com for the SALE
marketplace and api-lease.crexi.com for the LEASE marketplace. Surfaces:

  * POST /assets/search            {count, offset, filters…} -> {data, totalCount}
    (sale requires `includeUnpriced`, lease `includeUndisclosedRate`;
    offset + count must stay < 1500; count up to 500)
  * GET  /assets/<id>              the listing record; the `details` table
    carries the paywalled rows as runs of "*" (parsers null them)
  * GET  /assets/<id>/gallery      photos / videos
  * GET  /assets/<id>/brokers      listing brokers + brokerage
  * GET  /assets/<id>/spaces       (lease host) the suite table
  * GET  /auctions/<id>            (sale host) the auction record of an
    Auction-status asset
  * GET  /brokers?name=<text>      broker name search, <= 50 rows, no paging
  * GET  /brokers/<id>             broker by numeric id
  * GET  /public-profiles/<slug>   the public profile page's record (both
    hosts: the sale host carries the profile, the lease host its lease stats)
  * GET  /assets/stats?aggregateBy=AssetType|CityOrNeighborhood
  * GET  /universal-search/v2/search?SearchTypes=Sales&Query=<text>
    (sale host) address / city suggestions

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  CrexiUpstreamError  transport failure / 5xx / odd payload   — retryable
  CrexiBlocked        401 / 403 / 429 / challenge page         — retryable on a fresh exit
  CrexiBadRequest     upstream 400 that names a bad filter     — never retried
  CrexiNotFound       unknown / inactive asset, broker, slug  — never retried
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from crexi.refs import API_HOST, LEASE, SALE, SALE_API, SITE

IMPERSONATE = "chrome"
TIMEOUT = 30

# modelState messages the sale / lease hosts answer with HTTP 400 for an id
# that does not resolve to a live record
_NOT_FOUND_MESSAGES = ("Invalid asset id.", "Asset is inactive.", "Asset must be active or archived Auction.")


class CrexiUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected payload — retryable."""


class CrexiBlocked(CrexiUpstreamError, Blocked):
    """401 / 403 / 429 or a challenge page where JSON was expected — retryable."""


class CrexiBadRequest(BadRequest):
    """Upstream 400 that names a bad parameter — never retried."""


class CrexiNotFound(NotFound):
    """Asset / auction / broker / profile does not exist — never retried."""


# ---- sessions ----------------------------------------------------------------
# One session per cheroot worker thread (a curl handle is not thread-safe).
# Process-wide: after a block on the default tier every new session rides
# the fallback tier until _fallback_until.
_local = threading.local()
_fallback_until = 0.0
_fallback_lock = threading.Lock()


def _proxy():
    proxy = config.crexi_proxy()
    if proxy is None and time.time() < _fallback_until:
        proxy = config.crexi_fallback_proxy()
    return proxy


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        proxy = _proxy()
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers["accept-language"] = egress.accept_language(proxy)
        sess.headers["accept"] = "application/json, text/plain, */*"
        sess.headers["origin"] = SITE
        sess.headers["referer"] = SITE + "/"
        _local.session = sess
    return sess


def _drop_session(blocked=False):
    """Close the thread's session (fresh exit next time); a block on the
    default tier also starts the fallback cooldown for every thread."""
    global _fallback_until
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass
    if blocked and config.crexi_proxy() is None and config.crexi_fallback_proxy() is not None:
        with _fallback_lock:
            _fallback_until = max(_fallback_until, time.time() + config.CREXI_BLOCK_COOLDOWN)


def _retrying(fn):
    """Run fn() under the shared retry policy (CrexiUpstreamError only;
    NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except CrexiUpstreamError as e:
            last = e
            _drop_session(blocked=isinstance(e, CrexiBlocked))
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


# ---- request helpers -----------------------------------------------------------

def _bad_request_message(payload, text):
    """The site's two 400 shapes -> one message: {"errorCode", "modelState":
    {field: [msg]}} (the asset / search / broker routes) and RFC 9110
    {"errors": {field: [msg]}} (the paging window)."""
    if isinstance(payload, dict):
        fields = payload.get("modelState") or payload.get("errors")
        if isinstance(fields, dict) and fields:
            parts = []
            for name, msgs in fields.items():
                msgs = msgs if isinstance(msgs, list) else [msgs]
                parts.append(f"{name or 'request'}: {' '.join(str(m) for m in msgs)}")
            return "; ".join(parts)
        if payload.get("message"):
            return str(payload["message"])
    return (text or "")[:200] or "upstream 400"


def _classify(resp, label):
    """Map an HTTP response to the taxonomy; return the parsed JSON."""
    status = resp.status_code
    if status in (401, 403, 429):
        raise CrexiBlocked(f"HTTP {status} for {label}")
    if status >= 500:
        raise CrexiUpstreamError(f"HTTP {status} for {label}")
    text = resp.text
    try:
        payload = resp.json() if text else None
    except Exception:
        if status == 200:
            raise CrexiBlocked(f"non-JSON response for {label}: {text[:120]!r}")
        payload = None
    if status == 404:
        raise CrexiNotFound(f"{label} not found")
    if status == 400:
        fields = payload.get("modelState") if isinstance(payload, dict) else None
        if isinstance(fields, dict):
            for msgs in fields.values():
                msgs = msgs if isinstance(msgs, list) else [msgs]
                if any(str(m) in _NOT_FOUND_MESSAGES for m in msgs):
                    raise CrexiNotFound(f"{label} not found")
        if isinstance(payload, dict) and not fields and not payload.get("errors") and not payload.get("message"):
            # GET /brokers/<id> for an unknown id: {"errorCode": "InvalidParameters"} and nothing else
            raise CrexiNotFound(f"{label} not found")
        raise CrexiBadRequest(_bad_request_message(payload, text))
    if status != 200:
        raise CrexiUpstreamError(f"HTTP {status} for {label}")
    return payload


def _get(market, path, label, params=None):
    url = API_HOST[market] + path

    def once():
        try:
            resp = _session().get(url, params=params, timeout=TIMEOUT)
        except Exception as e:
            raise CrexiUpstreamError(f"request failed: {type(e).__name__}: {e}")
        return _classify(resp, label)
    return _retrying(once)


def _post(market, path, body, label):
    url = API_HOST[market] + path

    def once():
        try:
            resp = _session().post(url, json=body, timeout=TIMEOUT)
        except Exception as e:
            raise CrexiUpstreamError(f"request failed: {type(e).__name__}: {e}")
        return _classify(resp, label)
    return _retrying(once)


# ---- surfaces ------------------------------------------------------------------

def fetch_search(market, body):
    """POST /assets/search on the market's host -> {"data": [...],
    "totalCount": n} (the lease host adds totalSuiteCount). `body` is the
    filter dict built by api.py; the host-specific required flag is added
    here when the caller left it out."""
    body = dict(body)
    if market == LEASE:
        body.setdefault("includeUndisclosedRate", True)
    else:
        body.setdefault("includeUnpriced", True)
    payload = _post(market, "/assets/search", body, f"{market} search")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise CrexiUpstreamError(f"unexpected {market} search payload shape")
    return payload


def fetch_asset(market, asset_id):
    payload = _get(market, f"/assets/{asset_id}", f"{market} property {asset_id}")
    if not isinstance(payload, dict) or payload.get("id") is None:
        raise CrexiUpstreamError(f"unexpected {market} asset payload shape")
    return payload


def fetch_gallery(market, asset_id):
    payload = _get(market, f"/assets/{asset_id}/gallery", f"{market} property {asset_id} gallery")
    return payload if isinstance(payload, list) else []


def fetch_asset_brokers(market, asset_id):
    payload = _get(market, f"/assets/{asset_id}/brokers", f"{market} property {asset_id} brokers")
    return payload if isinstance(payload, list) else []


def fetch_spaces(asset_id):
    """The lease host's suite table (one row per space, each a list of
    {key, value, valueType, label, display} items)."""
    payload = _get(LEASE, f"/assets/{asset_id}/spaces", f"lease property {asset_id} spaces")
    return payload if isinstance(payload, list) else []


def fetch_auction(asset_id):
    """GET /auctions/<id> (sale host). A non-auction asset answers 400
    "Asset must be active or archived Auction" -> NotFound."""
    payload = _get(SALE, f"/auctions/{asset_id}", f"auction {asset_id}")
    if not isinstance(payload, dict) or payload.get("id") is None:
        raise CrexiUpstreamError("unexpected auction payload shape")
    return payload


def fetch_broker(broker_id):
    payload = _get(SALE, f"/brokers/{broker_id}", f"broker {broker_id}")
    if not isinstance(payload, dict) or payload.get("id") is None:
        raise CrexiUpstreamError("unexpected broker payload shape")
    return payload


def fetch_brokers_search(name):
    """GET /brokers?name=<text> -> up to 50 rows (the site's own cap; count
    / offset are ignored upstream)."""
    payload = _get(SALE, "/brokers", "broker search", params={"name": name})
    return payload if isinstance(payload, list) else []


def fetch_public_profile(market, slug):
    """GET /public-profiles/<slug>. The sale host carries the profile (about,
    licenses, markets, roles, brokerage, sale stats); the lease host the
    lease-side stats. An unknown slug is HTTP 404 on either host."""
    payload = _get(market, f"/public-profiles/{slug}", f"broker profile {slug}")
    if not isinstance(payload, dict):
        raise CrexiUpstreamError("unexpected public profile payload shape")
    return payload


def fetch_stats(market, aggregate_by):
    payload = _get(market, "/assets/stats", f"{market} stats", params={"aggregateBy": aggregate_by})
    return payload if isinstance(payload, list) else []


def fetch_suggestions(query, search_types):
    """GET /universal-search/v2/search (sale host) -> address / city rows."""
    params = [("SearchTypes", t) for t in search_types] + [("Query", query)]
    payload = _get(SALE, "/universal-search/v2/search", "location suggestions", params=params)
    return payload if isinstance(payload, list) else []
