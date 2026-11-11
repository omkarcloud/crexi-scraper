"""Offline tests for the /crexi/* request schemas.

    python -m pytest crexi/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crexi import refs, schemas  # noqa: E402


# ---- property refs ------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2715395", {"id": 2715395, "market": "sale"}),
    (" 2715395 ", {"id": 2715395, "market": "sale"}),
    ("https://www.crexi.com/properties/2715395/michigan-215-east-main-street", {"id": 2715395, "market": "sale"}),
    ("https://www.crexi.com/properties/2715395", {"id": 2715395, "market": "sale"}),
    ("https://crexi.com/properties/2715395/?x=1", {"id": 2715395, "market": "sale"}),
    ("https://www.crexi.com/lease/properties/664397/pennsylvania-crossroads-shopping-center", {"id": 664397, "market": "lease"}),
    ("https://api.crexi.com/assets/2715395", {"id": 2715395, "market": "sale"}),
    ("https://api-lease.crexi.com/assets/664397/gallery", {"id": 664397, "market": "lease"}),
])
def test_property_schema_accepts_ids_and_links(value, expected):
    assert schemas.PropertySchema().load({"property": value}) == {"property": expected}


def test_lease_schema_defaults_a_bare_id_to_the_lease_market():
    assert schemas.LeaseSchema().load({"property": "664397"}) == {"property": {"id": 664397, "market": "lease"}}
    loaded = schemas.LeaseSchema().load({"property": "https://www.crexi.com/properties/2715395/x"})
    assert loaded["property"]["market"] == "sale"


@pytest.mark.parametrize("value,message", [
    ("", "Must not be empty."),
    ("abc", "Must be a Crexi asset id"),
    ("https://www.crexi.com/profile/heatherhernd", "Must be a crexi.com property link"),
    ("https://example.com/properties/2715395", "Must be a crexi.com link."),
])
def test_property_schema_rejects(value, message):
    with pytest.raises(ValidationError) as e:
        schemas.PropertySchema().load({"property": value})
    assert message in str(e.value.messages["property"][0])


def test_property_schema_rejects_sibling_params():
    with pytest.raises(ValidationError) as e:
        schemas.PropertySchema().load({"property": "2715395", "id": "2715395"})
    assert "id" in e.value.messages


# ---- broker refs --------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("1742677", {"id": 1742677}),
    ("heatherhernd", {"slug": "heatherhernd"}),
    ("https://www.crexi.com/profile/heatherhernd", {"slug": "heatherhernd"}),
    ("https://crexi.com/profile/heatherhernd/?tab=lease", {"slug": "heatherhernd"}),
])
def test_broker_schema_accepts(value, expected):
    assert schemas.BrokerSchema().load({"broker": value}) == {"broker": expected}


@pytest.mark.parametrize("value", ["", "a b", "https://www.crexi.com/properties/2715395", "https://example.com/profile/x"])
def test_broker_schema_rejects(value):
    with pytest.raises(ValidationError):
        schemas.BrokerSchema().load({"broker": value})


def test_broker_listings_schema():
    loaded = schemas.BrokerListingsSchema().load({"broker": "1742677", "market": "LEASE", "per_page": "5"})
    assert loaded == {"broker": {"id": 1742677}, "market": "lease", "sort": "newest", "page": 1, "per_page": 5}
    with pytest.raises(ValidationError) as e:
        schemas.BrokerListingsSchema().load({"broker": "1742677", "market": "lease", "sort": "price"})
    assert "sort" in e.value.messages
    with pytest.raises(ValidationError):
        schemas.BrokerListingsSchema().load({"broker": "1742677", "market": "rent"})


# ---- search schemas -----------------------------------------------------------------

def test_properties_search_defaults():
    loaded = schemas.PropertiesSearchSchema().load({})
    assert loaded["page"] == 1 and loaded["per_page"] == schemas.DEFAULT_PAGE_SIZE
    assert loaded["sort"] == "relevance" and loaded["sort_direction"] == "desc"
    assert loaded["status"] == "active" and loaded["include_unpriced"] is True
    assert loaded["query"] is None and loaded["state"] is None


def test_properties_search_accepts_every_filter():
    loaded = schemas.PropertiesSearchSchema().load({
        "query": "gas station", "state": "tx, ca", "city": "Austin,Dallas", "county": "Travis County",
        "zip": "78701", "property_type": "retail, Mixed use", "subtype": "gas station,warehouse",
        "min_price": "100000", "max_price": "2000000", "min_cap_rate": "5", "max_cap_rate": "9",
        "min_sqft": "1000", "max_sqft": "50000", "min_price_per_sqft": "50", "max_price_per_sqft": "900",
        "min_acres": "0.5", "max_acres": "10", "min_occupancy": "80", "max_occupancy": "100",
        "min_remaining_term": "5", "max_remaining_term": "20", "building_class": "a,b",
        "tenancy": "Single", "tenant": "Starbucks, Dollar General", "tenant_credit": "franchisee",
        "lease_type": "nnn,absolute_net", "investment_type": "net_lease", "status": "auction",
        "opportunity_zone": "true", "listed_since": "2026-10-01", "include_unpriced": "no",
        "brokerage": "Marcus & Millichap", "sort": "cap_rate", "sort_direction": "asc", "page": "2",
        "per_page": "50",
    })
    assert loaded["state"] == ["TX", "CA"]
    assert loaded["property_type"] == ["Retail", "Mixed Use"]
    assert loaded["subtype"] == ["Gas Station", "Warehouse"]
    assert loaded["lease_type"] == ["NNN", "Absolute Net"]
    assert loaded["building_class"] == ["A", "B"]
    assert loaded["tenancy"] == "single" and loaded["tenant_credit"] == "franchisee"
    assert loaded["investment_type"] == "net_lease" and loaded["status"] == "auction"
    assert loaded["opportunity_zone"] is True and loaded["include_unpriced"] is False
    assert loaded["listed_since"] == "2026-10-01"
    assert loaded["min_price"] == 100000.0 and loaded["page"] == 2 and loaded["per_page"] == 50


@pytest.mark.parametrize("params,field", [
    ({"property_type": "Healthcare"}, "property_type"),
    ({"subtype": "Castle"}, "subtype"),
    ({"state": "Texas"}, "state"),
    ({"tenancy": "owner"}, "tenancy"),
    ({"investment_type": "flip"}, "investment_type"),
    ({"status": "sold"}, "status"),
    ({"sort": "random"}, "sort"),
    ({"sort_direction": "up"}, "sort_direction"),
    ({"min_price": "-1"}, "min_price"),
    ({"listed_since": "yesterday"}, "listed_since"),
    ({"listed_since": "2099-01-01"}, "listed_since"),
    ({"per_page": "101"}, "per_page"),
    ({"page": "0"}, "page"),
    ({"bogus": "1"}, "bogus"),
])
def test_properties_search_rejects(params, field):
    with pytest.raises(ValidationError) as e:
        schemas.PropertiesSearchSchema().load(params)
    assert field in e.value.messages


def test_search_window_cap():
    schemas.PropertiesSearchSchema().load({"page": "74", "per_page": "20"})     # 1,480 <= 1,499
    with pytest.raises(ValidationError) as e:
        schemas.PropertiesSearchSchema().load({"page": "75", "per_page": "20"})  # 1,500
    assert "1,499" in e.value.messages["page"][0]
    with pytest.raises(ValidationError):
        schemas.LeasesSearchSchema().load({"page": "15", "per_page": "100"})
    with pytest.raises(ValidationError):
        schemas.BrokerListingsSchema().load({"broker": "1", "page": "15", "per_page": "100"})


def test_leases_search_schema():
    loaded = schemas.LeasesSearchSchema().load({"property_type": "office,restaurant", "subtype": "coworking",
                                                "tenancy": "multiple", "sort": "rate", "include_undisclosed_rate": "0"})
    assert loaded["property_type"] == ["Office", "Restaurant"] and loaded["subtype"] == ["Coworking"]
    assert loaded["tenancy"] == "multiple" and loaded["sort"] == "rate"
    assert loaded["include_undisclosed_rate"] is False
    with pytest.raises(ValidationError):
        schemas.LeasesSearchSchema().load({"property_type": "Multifamily"})   # sale-only type
    with pytest.raises(ValidationError):
        schemas.LeasesSearchSchema().load({"sort": "cap_rate"})
    with pytest.raises(ValidationError):
        schemas.LeasesSearchSchema().load({"min_price": "5"})                  # sale-only filter


# ---- the small schemas --------------------------------------------------------------

def test_brokers_search_schema():
    assert schemas.BrokersSearchSchema().load({"query": " cbre "}) == {"query": "cbre", "limit": 20}
    assert schemas.BrokersSearchSchema().load({"query": "cbre", "limit": "50"})["limit"] == 50
    with pytest.raises(ValidationError):
        schemas.BrokersSearchSchema().load({"query": "cbre", "limit": "51"})
    with pytest.raises(ValidationError):
        schemas.BrokersSearchSchema().load({})


def test_market_stats_schema():
    assert schemas.MarketStatsSchema().load({}) == {"group_by": "property_type", "market": "sale"}
    assert schemas.MarketStatsSchema().load({"group_by": "City", "market": "lease"}) == {"group_by": "city", "market": "lease"}
    with pytest.raises(ValidationError):
        schemas.MarketStatsSchema().load({"group_by": "state"})


def test_locations_suggest_schema():
    assert schemas.LocationsSuggestSchema().load({"query": "austin"}) == {"query": "austin", "market": "both"}
    with pytest.raises(ValidationError):
        schemas.LocationsSuggestSchema().load({"query": "austin", "market": "rent"})


def test_vocabularies_are_consistent():
    for public, token in refs.SALE_SORTS.items():
        assert token in ("rank", "activatedOn", "updatedOn", "price", "capRate", "sqft"), public
    assert set(refs.LEASE_SUBTYPE_VALUES) <= set(refs.SALE_SUBTYPE_VALUES) | {"Coworking"}
    assert refs.SALE_STATUSES["auction"] == "Auction"


def test_sqft_filters_reach_crexi_as_integers():
    # Crexi answers 400 "Input string '1000.0' is not a valid integer" to a
    # decimal sqFtMin / sqFtMax on both hosts (2026-11-10)
    from crexi import api
    sale = api._sale_body(schemas.PropertiesSearchSchema().load({"min_sqft": "1000", "max_sqft": "5000.6"}))
    assert sale["sqFtMin"] == 1000 and sale["sqFtMax"] == 5001
    assert isinstance(sale["sqFtMin"], int) and isinstance(sale["sqFtMax"], int)
    lease = api._lease_body(schemas.LeasesSearchSchema().load({"min_sqft": "2500.0"}))
    assert lease["sqFtMin"] == 2500 and isinstance(lease["sqFtMin"], int)
    assert "acreageMin" not in lease
