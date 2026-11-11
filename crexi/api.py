"""The /crexi/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Caching lives here (cache.cached_call, keyed on the validated params):
search pages, broker searches, stats and suggestions cache their own
responses; a listing record (the asset + its brokers + gallery, + spaces
for a lease) is cached under (market, id) alone so a link and a bare id
share one fetch, and properties/details, leases/details and
auctions/details all read that one row; a broker profile is cached under
its slug, and a numeric broker id resolves to the slug through a second
small cached row, so every broker endpoint for one person costs one
profile fetch.
"""
import math

from cache import cached_call
from crexi import cache_config as ttl
from crexi import parsers, refs
from crexi.fetch import (CrexiNotFound, fetch_asset, fetch_asset_brokers, fetch_auction, fetch_broker,
                         fetch_brokers_search, fetch_gallery, fetch_public_profile, fetch_search, fetch_spaces,
                         fetch_stats, fetch_suggestions)


# ---- shared search plumbing -------------------------------------------------------

def _pagination(page, per_page, total, has_items):
    """The site refuses offset + count >= 1500, so total_pages counts the
    pages that can actually be fetched, not the pages the total implies."""
    reachable = min(total or 0, refs.MAX_SEARCH_WINDOW)
    # the last fetchable page is the one with page * per_page <= the window
    # (the schema's _window_check), so a page that straddles it is not counted
    last_page = max(1, refs.MAX_SEARCH_WINDOW // per_page)
    total_pages = min(max(1, math.ceil(reachable / per_page)), last_page) if reachable else (1 if has_items else 0)
    return {"page": page, "items_per_page": per_page, "total_pages": total_pages, "total_count": total}


def _iso_day(value):
    return f"{value}T00:00:00Z" if value else None


def _common_filters(query=None, state=None, city=None, county=None, zip=None, min_sqft=None, max_sqft=None,
                    min_acres=None, max_acres=None, building_class=None, listed_since=None, brokerage=None,
                    subtype=None, property_type=None, **_):
    body = {}
    if query:
        body["term"] = query
    if state:
        body["states"] = state
    if city:
        body["cities"] = city
    if county:
        body["counties"] = county
    if zip:
        body["zips"] = zip
    if property_type:
        body["types"] = property_type
    if subtype:
        body["subtypes"] = subtype
    # sqFtMin / sqFtMax are integers on both hosts: "1000.0" is a 400
    # "Input string '1000.0' is not a valid integer" (2026-11-10); every other
    # numeric filter takes decimals
    if min_sqft is not None:
        body["sqFtMin"] = int(round(min_sqft))
    if max_sqft is not None:
        body["sqFtMax"] = int(round(max_sqft))
    if min_acres is not None:
        body["acreageMin"] = min_acres
    if max_acres is not None:
        body["acreageMax"] = max_acres
    if building_class:
        body["classes"] = building_class
    if listed_since:
        body["activationDateMin"] = _iso_day(listed_since)
    if brokerage:
        body["brokerage"] = brokerage
    return body


def _paging(body, page, per_page, sort_order, sort_direction):
    body["count"] = per_page
    body["offset"] = (page - 1) * per_page
    body["sortOrder"] = sort_order
    body["sortDirection"] = refs.SORT_DIRECTIONS[sort_direction]
    return body


def _sale_body(data):
    body = _common_filters(**data)
    for public, site in (("min_price", "askingPriceMin"), ("max_price", "askingPriceMax"),
                         ("min_cap_rate", "capRateMin"), ("max_cap_rate", "capRateMax"),
                         ("min_price_per_sqft", "pricePerSqFtMin"), ("max_price_per_sqft", "pricePerSqFtMax"),
                         ("min_occupancy", "occupancyMin"), ("max_occupancy", "occupancyMax"),
                         ("min_remaining_term", "remainingTermMin"), ("max_remaining_term", "remainingTermMax")):
        if data.get(public) is not None:
            body[site] = data[public]
    if data.get("tenancy"):
        body["tenancies"] = [refs.SALE_TENANCIES[data["tenancy"]]]
    if data.get("tenant"):
        body["tenants"] = data["tenant"]
    if data.get("tenant_credit"):
        body["tenantCredits"] = [refs.TENANT_CREDITS[data["tenant_credit"]]]
    if data.get("lease_type"):
        body["leaseTypes"] = data["lease_type"]
    if data.get("investment_type"):
        body["investmentType"] = refs.INVESTMENT_TYPES[data["investment_type"]]
    status = refs.SALE_STATUSES.get(data.get("status") or "active")
    if status == "Auction":
        body["tradingStatuses"] = ["Auction"]
    elif status and status != "Active Listings":
        body["statuses"] = [status]
    if data.get("opportunity_zone"):
        body["isInOpportunityZone"] = True
    body["includeUnpriced"] = data.get("include_unpriced") is not False
    return _paging(body, data["page"], data["per_page"], refs.SALE_SORTS[data.get("sort") or "relevance"],
                   data.get("sort_direction") or "desc")


def _lease_body(data):
    body = _common_filters(**data)
    if data.get("tenancy"):
        body["tenancies"] = [refs.LEASE_TENANCIES[data["tenancy"]]]
    body["includeUndisclosedRate"] = data.get("include_undisclosed_rate") is not False
    return _paging(body, data["page"], data["per_page"], refs.LEASE_SORTS[data.get("sort") or "relevance"],
                   data.get("sort_direction") or "desc")


def _search(market, body, page, per_page):
    payload = fetch_search(market, body)
    rows, total = parsers.parse_search_page(payload, market)
    out = {"results": rows, "pagination": _pagination(page, per_page, total, bool(rows))}
    if market == refs.LEASE and isinstance(payload.get("totalSuiteCount"), int):
        out["total_spaces"] = payload["totalSuiteCount"]
    return out


# ---- properties/search + leases/search ---------------------------------------------

def _properties_search(**data):
    return _search(refs.SALE, _sale_body(data), data["page"], data["per_page"])


def properties_search(**data):
    return cached_call("crexi.properties_search", data, _properties_search, ttl.SEARCH_CACHE)


def _leases_search(**data):
    return _search(refs.LEASE, _lease_body(data), data["page"], data["per_page"])


def leases_search(**data):
    return cached_call("crexi.leases_search", data, _leases_search, ttl.SEARCH_CACHE)


# ---- the shared listing record -------------------------------------------------------

def _sale_record(id):
    asset = fetch_asset(refs.SALE, id)
    return {"asset": asset,
            "brokers": fetch_asset_brokers(refs.SALE, id),
            "gallery": fetch_gallery(refs.SALE, id)}


def _lease_record(id):
    asset = fetch_asset(refs.LEASE, id)
    return {"asset": asset,
            "brokers": fetch_asset_brokers(refs.LEASE, id),
            "gallery": fetch_gallery(refs.LEASE, id),
            "spaces": fetch_spaces(id)}


def _record(ref):
    """The raw record bundle for {"id", "market"}, cached per (market, id)."""
    if ref["market"] == refs.LEASE:
        return cached_call("crexi.lease_record", {"id": ref["id"]}, _lease_record, ttl.PROPERTY_CACHE)
    return cached_call("crexi.sale_record", {"id": ref["id"]}, _sale_record, ttl.PROPERTY_CACHE)


def _details(ref):
    record = _record(ref)
    if ref["market"] == refs.LEASE:
        return parsers.parse_lease_asset(record["asset"], record["brokers"], record["gallery"], record["spaces"])
    return parsers.parse_sale_asset(record["asset"], record["brokers"], record["gallery"])


def property_details(property):
    """Everything the listing page shows a signed-out visitor: the record,
    the details table (paywalled rows null), description and highlights,
    brokers and the full gallery. A lease link routes to the lease record."""
    return _details(property)


def lease_details(property):
    """The lease building record with its spaces (suite table), brokers and
    gallery. A sale link routes to the sale record."""
    return _details(property)


# ---- auctions/details ----------------------------------------------------------------

def _auction_details(id):
    record = fetch_auction(id)
    asset = _record({"id": id, "market": refs.SALE})["asset"]
    return parsers.parse_auction(record, asset)


def auction_details(property):
    if property["market"] == refs.LEASE:
        raise CrexiNotFound("lease listings are never auctioned; pass a sale listing")
    return cached_call("crexi.auction", {"id": property["id"]}, _auction_details, ttl.AUCTION_CACHE)


# ---- brokers --------------------------------------------------------------------------

def _brokers_search(query, limit):
    rows = parsers.parse_broker_search(fetch_brokers_search(query))[:limit]
    return {"query": query, "count": len(rows), "results": rows}


def brokers_search(**data):
    return cached_call("crexi.brokers_search", data, _brokers_search, ttl.BROKER_SEARCH_CACHE)


def _broker_slug(id):
    """Numeric broker id -> the profile slug (GET /brokers/<id>)."""
    return parsers.parse_broker(fetch_broker(id))


def _slug_for(broker):
    if "slug" in broker:
        return broker["slug"]
    short = cached_call("crexi.broker_by_id", {"id": broker["id"]}, _broker_slug, ttl.BROKER_CACHE)
    if not short.get("slug"):
        raise CrexiNotFound(f"broker {broker['id']} has no public profile")
    return short["slug"]


def _profile(slug):
    sale = fetch_public_profile(refs.SALE, slug)
    try:
        lease = fetch_public_profile(refs.LEASE, slug)
    except CrexiNotFound:
        lease = None
    return parsers.parse_public_profile(sale, lease)


def broker_details(broker):
    """The public profile: name, photo, about, licenses, markets, roles,
    brokerage, and the active / closed stats on both marketplaces."""
    return cached_call("crexi.broker", {"slug": _slug_for(broker)}, _profile, ttl.BROKER_CACHE)


def _broker_listings(broker, market, sort, page, per_page):
    profile = broker_details(broker)
    if not profile.get("global_id"):
        raise CrexiNotFound("broker has no listings")
    body = {"brokerGlobalIds": [profile["global_id"]]}
    sorts = refs.LEASE_SORTS if market == refs.LEASE else refs.SALE_SORTS
    body = _paging(body, page, per_page, sorts[sort], "desc")
    out = _search(market, body, page, per_page)
    out["broker"] = {"id": profile["id"], "name": profile["name"], "link": profile["link"]}
    return {"broker": out.pop("broker"), **out}


def broker_listings(**data):
    return cached_call("crexi.broker_listings", data, _broker_listings, ttl.SEARCH_CACHE)


# ---- markets/stats + locations/suggest ----------------------------------------------

def _market_stats(group_by, market):
    rows = parsers.parse_stats(fetch_stats(market, refs.STATS_GROUPS[group_by]), market)
    return {"market": market, "group_by": group_by, "count": len(rows), "results": rows}


def market_stats(**data):
    return cached_call("crexi.market_stats", data, _market_stats, ttl.STATS_CACHE)


def _locations_suggest(query, market):
    rows = parsers.parse_suggestions(fetch_suggestions(query, refs.SUGGEST_MARKETS[market]))
    return {"query": query, "count": len(rows), "results": rows}


def locations_suggest(**data):
    return cached_call("crexi.locations_suggest", data, _locations_suggest, ttl.SUGGEST_CACHE)
