"""crexi/fetch.py exit ladder (no network): the server's own IP -> the gateway
exit after a block (CREXI_FALLBACK_EXIT) -> a datacenter exit only when
the gateway fails or is refused too (CREXI_LAST_EXIT)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import egress  # noqa: E402
from crexi import fetch  # noqa: E402
from scraper_utils.testing import hosted_only

DC = "http://dc-exit"


class _Sess:
    def __init__(self, exit):
        self.exit, self.headers, self.closed = exit, {}, False

    def close(self):
        self.closed = True


@pytest.fixture
def built(monkeypatch):
    """Every session the fetch layer builds, in order (its exit on .exit)."""
    sessions = []
    monkeypatch.setattr(config, "datacenter_proxy", lambda *a, **k: DC)
    monkeypatch.setattr(egress, "new_session",
                        lambda exit=None, impersonate="chrome", **kw: sessions.append(_Sess(exit)) or sessions[-1])
    monkeypatch.setattr(config, "CREXI_EXIT", "direct")
    monkeypatch.setattr(config, "CREXI_FALLBACK_EXIT", "gateway")
    monkeypatch.setattr(config, "CREXI_LAST_EXIT", "datacenter")
    monkeypatch.setattr(config, "MAX_RETRIES", 3)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    monkeypatch.setattr(fetch, "_fallback_until", 0.0)
    monkeypatch.setattr(fetch, "_last_until", 0.0)
    fetch._drop_session()
    fetch._local.last_try = False
    yield sessions
    fetch._drop_session()


def _call(outcomes):
    """One fetch call: each attempt rides fetch._session() and ends as the
    next outcome says ("ok", "blocked", "error"). Returns the exits tried."""
    outcomes, tried = list(outcomes), []

    def once():
        tried.append(fetch._session().exit)
        outcome = outcomes.pop(0)
        if outcome == "blocked":
            raise fetch.CrexiBlocked("HTTP 403")
        if outcome == "error":
            raise fetch.CrexiUpstreamError("HTTP 502")
        return "ok"
    try:
        fetch._retrying(once)
    except fetch.CrexiUpstreamError:
        pass
    return tried


@hosted_only
def test_the_own_ip_carries_the_traffic_and_a_transport_error_stays_on_it(built):
    assert _call(["ok"]) == [None]
    assert _call(["error", "error", "ok"]) == [None, None, None]
    assert _call(["ok"]) == [None]


@hosted_only
def test_a_block_on_the_own_ip_moves_new_sessions_to_the_gateway(built):
    assert _call(["blocked", "ok"]) == [None, "gateway"]
    assert _call(["ok"]) == ["gateway"]                 # the same gateway session, for the cooldown
    assert [s.exit for s in built] == [None, "gateway"]
    assert built[0].closed and not built[1].closed
    assert built[1].headers["accept-language"] == egress.accept_language()      # the US gateway speaks like the pod


@hosted_only
def test_the_cooldown_ends_on_the_own_ip_again(built, monkeypatch):
    assert _call(["blocked", "ok"]) == [None, "gateway"]
    monkeypatch.setattr(fetch, "_fallback_until", 0.0)
    fetch._drop_session()
    assert _call(["ok"]) == [None]


@hosted_only
def test_a_gateway_failure_makes_the_last_retry_on_the_datacenter_exit_for_that_call_only(built):
    assert _call(["blocked", "error", "ok"]) == [None, "gateway", DC]
    assert _call(["ok"]) == ["gateway"]                 # the next call is back on the gateway
    assert _call(["error", "error", "ok"]) == ["gateway", "gateway", DC]
    assert _call(["ok"]) == ["gateway"]
    assert fetch._last_until == 0.0                 # the gateway's own errors never park threads on the proxy


@hosted_only
def test_a_gateway_refusal_moves_new_sessions_to_the_datacenter_exit(built):
    assert _call(["blocked", "blocked", "ok"]) == [None, "gateway", DC]
    assert _call(["ok"]) == [DC]
    assert _call(["blocked", "ok"]) == [DC, DC]     # refused there too: a fresh datacenter exit, as before the gateway
    assert fetch._last_until > 0.0


@hosted_only
def test_no_last_exit_keeps_every_retry_on_the_gateway(built, monkeypatch):
    monkeypatch.setattr(config, "CREXI_LAST_EXIT", None)
    assert _call(["blocked", "blocked", "error"]) == [None, "gateway", "gateway"]
    assert _call(["error", "error", "error"]) == ["gateway", "gateway", "gateway"]


@hosted_only
def test_the_old_knob_values_behave_as_before(built, monkeypatch):
    monkeypatch.setattr(config, "CREXI_FALLBACK_EXIT", "datacenter")
    monkeypatch.setattr(config, "CREXI_LAST_EXIT", None)
    assert _call(["blocked", "blocked", "ok"]) == [None, DC, DC]
    assert _call(["ok"]) == [DC]
    monkeypatch.setattr(config, "CREXI_FALLBACK_EXIT", None)
    monkeypatch.setattr(fetch, "_fallback_until", 0.0)
    fetch._drop_session()
    assert _call(["blocked", "ok"]) == [None, None]     # no fallback tier: the retry stays on the own IP


@hosted_only
def test_the_gateway_as_the_main_exit_keeps_the_datacenter_exit_for_the_last_retry(built, monkeypatch):
    monkeypatch.setattr(config, "CREXI_EXIT", "gateway")
    assert _call(["ok"]) == ["gateway"]
    assert _call(["blocked", "error", "ok"]) == ["gateway", "gateway", DC]
    assert _call(["ok"]) == ["gateway"]
    assert fetch._fallback_until == 0.0 and fetch._last_until == 0.0
