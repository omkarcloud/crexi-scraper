"""Offline tests for the Crexi parsers, reference resolvers and value
helpers.

    python -m pytest crexi/test_parsers.py -q

Fixtures are real api.crexi.com / api-lease.crexi.com payloads captured
2026-11-07 (crexi/fixtures/): sale search pages (a city page, auctions, by
broker, an empty page, the two 400 shapes), three sale assets (plain
office, net lease with tenants + highlights, auction) with gallery and
brokers, the auction record, a lease asset with 12 suites + spaces +
brokers + gallery, lease search pages, broker name search, broker by id,
public profiles (sale + lease hosts), stats and suggestions. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crexi import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def office():
    return P.parse_sale_asset(fixture("sale_asset_office.json"), fixture("sale_brokers.json"),
                              fixture("sale_gallery.json"))


@pytest.fixture(scope="module")
def netlease():
    return P.parse_sale_asset(fixture("sale_asset_netlease.json"), fixture("sale_brokers_netlease.json"), [])


@pytest.fixture(scope="module")
def auction_asset():
    return P.parse_sale_asset(fixture("sale_asset_auction.json"))


@pytest.fixture(scope="module")
def lease():
    return P.parse_lease_asset(fixture("lease_asset.json"), fixture("lease_brokers.json"),
                               fixture("lease_gallery.json"), fixture("lease_spaces.json"))


# ---- refs ------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2715395", {"id": 2715395, "market": "sale"}),
    ("https://www.crexi.com/properties/2715395/michigan-215-east-main-street", {"id": 2715395, "market": "sale"}),
    ("https://www.crexi.com/lease/properties/664397/x", {"id": 664397, "market": "lease"}),
    ("https://api-lease.crexi.com/assets/664397", {"id": 664397, "market": "lease"}),
])
def test_resolve_property(value, expected):
    assert refs.resolve_property(value) == expected


def test_resolve_property_default_market():
    assert refs.resolve_property("664397", refs.LEASE) == {"id": 664397, "market": "lease"}


@pytest.mark.parametrize("value", ["", "x", "https://example.com/properties/1", "https://www.crexi.com/search"])
def test_resolve_property_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_property(value)


@pytest.mark.parametrize("value,expected", [
    ("1742677", {"id": 1742677}),
    ("heatherhernd", {"slug": "heatherhernd"}),
    ("https://www.crexi.com/profile/heatherhernd", {"slug": "heatherhernd"}),
])
def test_resolve_broker(value, expected):
    assert refs.resolve_broker(value) == expected


def test_links():
    assert refs.property_link(2715395, refs.SALE, "slug") == "https://www.crexi.com/properties/2715395/slug"
    assert refs.property_link(664397, refs.LEASE) == "https://www.crexi.com/lease/properties/664397"
    assert refs.broker_link("heatherhernd") == "https://www.crexi.com/profile/heatherhernd"
    assert refs.broker_link(None) is None


# ---- value helpers ---------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("$189,900", 189900), ("54,886", 54886), ("6.2%", 6.2), ("****", None), ("", None), (None, None),
    ("No", False), ("Yes", True), ("C-2", "C-2"), ("$20/SF/YR", "$20/SF/YR"), ("1.42", 1.42), (7, 7),
    ("Office, Retail", "Office, Retail"),
])
def test_typed(value, expected):
    assert P.typed(value) == expected


@pytest.mark.parametrize("label,key", [
    ("Lot Size (SqFt)", "lot_size_sqft"), ("Price/SqFt (Land Value)", "price_per_sqft_land_value"),
    ("Brand/Tenant", "brand_tenant"), ("NOI", "noi"), ("Parking (spaces)", "parking_spaces"),
    ("Net Rentable (SqFt)", "net_rentable_sqft"), ("Year Built", "year_built"), ("R&D", "r_and_d"),
])
def test_snake(label, key):
    assert P.snake(label) == key


def test_money_per_unit_and_positive():
    assert P.money_per_unit("$0/SF") is None
    assert P.money_per_unit("$12.50/Acre") == 12.5
    assert P.money_per_unit("****") is None
    assert P.positive(0) is None and P.positive(43) == 43 and P.positive("x") is None


def test_html_helpers():
    assert P.html_text("<p>Hello&nbsp;<strong>world</strong>.​</p><p>Next</p>") == "Hello world.\nNext"
    assert P.html_list("<ul><li>​One</li><li><strong>Two</strong> x</li></ul><p></p>") == ["One", "Two x"]
    assert P.html_list("plain line") == ["plain line"]
    assert P.html_text("") is None and P.html_list(None) is None


# ---- sale search -------------------------------------------------------------------------

def test_sale_search_page():
    rows, total = P.parse_search_page(fixture("sale_search_page.json"), refs.SALE)
    assert total == 658 and len(rows) == 5
    row = rows[0]
    assert row["id"] and row["link"].startswith("https://www.crexi.com/properties/")
    assert row["market"] == "sale" and row["status"] == "On-Market"
    assert row["location"]["state_code"] == "TX" and row["location"]["city"] == "Austin"
    assert row["location"]["latitude"] and row["location"]["full_address"]
    assert row["currency"] == "USD" and isinstance(row["is_unpriced"], bool)
    assert set(row) >= {"name", "headline", "property_types", "asking_price", "brokerage", "media", "listed_on"}
    assert "urlSlug" not in row and "userIsAssetOwner" not in row


def test_sale_search_empty_and_auctions():
    # a page past the end: no rows, the total still reported
    rows, total = P.parse_search_page(fixture("sale_search_empty.json"), refs.SALE)
    assert rows == [] and total == 25
    rows, total = P.parse_search_page(fixture("sale_search_auctions.json"), refs.SALE)
    assert total == 127 and all(r["status"] == "Auction" for r in rows)
    assert rows[0]["offers_due_on"] == "2026-11-18T20:00:00Z"


def test_sale_search_row_zero_square_footage_is_null():
    rows, _ = P.parse_search_page(fixture("sale_search_by_broker.json"), refs.SALE)
    assert any(r["square_footage"] is None for r in rows)
    assert all(r["price_per_sqft_land"] in (None,) or r["price_per_sqft_land"] > 0 for r in rows)


# ---- sale asset ------------------------------------------------------------------------

def test_office_asset_core(office):
    assert office["id"] == 2715395
    assert office["link"] == "https://www.crexi.com/properties/2715395/michigan-215-east-main-street"
    assert office["name"] == "215 East Main Street" and office["status"] == "Active"
    assert office["is_auction"] is False and office["auction"] is None
    assert office["property_types"] == ["Office", "Retail"]
    assert office["subtypes"] == ["Traditional Office", "Executive Office", "Storefront"]
    assert office["asking_price"] == 189900 and office["currency"] == "USD" and office["is_unpriced"] is False
    assert office["marketing_description"].startswith("Prime Commercial Opportunity")
    assert "​" not in office["marketing_description"]
    assert office["investment_highlights"] is None
    assert office["location"]["city"] == "Spring Arbor" and office["location"]["county"] == "Jackson County"
    assert office["location"]["full_address"] == "215 East Main Street, Spring Arbor, Jackson County, MI 49283"
    assert office["other_locations"] == []
    assert office["realtor_boards"] == ["MichRIC"]
    assert office["listed_on"] == "2026-09-21T19:22:48.541Z"


def test_office_asset_paywalled_rows_are_null(office):
    b = office["building"]
    assert b["year_built"] is None and b["units"] is None and b["parking_spaces"] is None
    assert b["zoning"] == "C-2" and b["lot_size_sqft"] == 54886 and b["buildings"] == 1
    assert office["lease"] is None            # every lease row masked -> no block at all
    assert office["financials"]["price_per_sqft_land_value"] is None
    assert office["details"] == {}
    assert not any(P.is_masked(v) for v in office["financials"].values())


def test_office_asset_brokers_and_media(office):
    brokers = office["brokers"]
    assert len(brokers) == 2
    first = brokers[0]
    assert first["id"] == 1742677 and first["name"] == "Heather Herndon"
    assert first["link"] == "https://www.crexi.com/profile/heatherhernd"
    assert first["brokerage"]["name"] == "Howard Hanna Real Estate Services"
    assert first["brokerage"]["website"] == "https://www.howardhanna.com/"
    assert first["brokerage"]["location"]["city"] == "Jackson" and first["brokerage"]["location"]["latitude"] is None
    assert first["licenses"] == [{"number": "MI 6501335416", "state_code": "MI", "type": None,
                                  "brokerage_phone": "517-787-9800", "is_auctioneer": False}]
    assert first["listings_count"] == 47 and first["has_phone"] is False
    assert brokers[1]["licenses"] == [] and brokers[1]["brokerage"]["website"] is None
    media = office["media"]
    assert media["photo_count"] == 43 and len(media["photos"]) == 43
    assert media["photos"][0]["image"].startswith("https://crexi.com/images/format=auto,width=3000")
    assert media["photos"][0]["type"] == "image" and media["photos"][0]["thumbnail"]
    assert media["has_flyer"] is True and media["has_offering_memorandum"] is False


def test_netlease_asset(netlease):
    assert netlease["tenants"][0] == "Starbucks" and "Biggby Coffee" in netlease["other_tenants"]
    assert netlease["investment_highlights"][0].startswith("New 15-Year NNN Ground Lease")
    assert len(netlease["investment_highlights"]) == 10
    assert netlease["lease"]["is_ground_lease"] is False and netlease["lease"]["term"] is None
    assert netlease["building"]["square_footage"] == 646 and netlease["building"]["lot_size_acres"] == 1.42
    assert netlease["financials"]["cap_rate"] is None and netlease["financials"]["noi"] is None
    assert netlease["broker_of_record"] == {"name": "Adam Lewis", "license": "NE 20250136", "brokerage": None, "phone": None}
    assert netlease["media"]["has_offering_memorandum"] is True and netlease["media"]["photos"] == []
    assert netlease["brokers"] and netlease["details"] == {}


def test_auction_asset(auction_asset):
    assert auction_asset["is_auction"] is True and auction_asset["status"] == "Auction"
    auction = auction_asset["auction"]
    assert auction["starting_bid"] == 25000 and auction["offers_due_on"] == "2026-12-02T17:00:00Z"
    assert auction["earnest_deposit"] == 10 and auction["is_earnest_deposit_percent"] is True
    assert auction["participation_deposit"] == 10000 and auction["escrow_period_days"] == 27
    assert auction["deposit_option"] == "Credit Card"
    assert auction_asset["building"]["apn"] is None and auction_asset["building"]["lot_size_acres"] == 0.81
    assert auction_asset["brokers"] is None and auction_asset["media"]["photos"] is None
    assert auction_asset["media"]["has_due_diligence_vault"] is True
    assert auction_asset["broker_of_record"]["brokerage"] == "Saunders Real Estate"


def test_sale_asset_survives_a_sparse_payload():
    out = P.parse_sale_asset({"id": 1}, [], [])
    assert out["id"] == 1 and out["link"] == "https://www.crexi.com/properties/1"
    assert out["location"] is None and out["brokers"] == [] and out["media"]["photos"] == []
    assert out["is_unpriced"] is True and out["lease"] is None


# ---- auction record ----------------------------------------------------------------------

def test_auction_record():
    out = P.parse_auction(fixture("auction_record.json"), fixture("sale_asset_auction.json"))
    assert out["id"] == 2732040 and out["link"].endswith("/properties/2732040/Lot-9-Lake-View-Office-Park-Tavares-FL")
    assert out["status"] == "BidderRegistration" and out["type"] == "Reserve"
    assert out["starts_on"] == "2026-11-30T17:00:00Z" and out["ends_on"] == "2026-12-02T17:00:00Z"
    assert out["bidding"] == {"starting_bid": 25000, "minimum_bid": 25000, "bid_increment": 25000,
                              "is_reserve_met": False, "is_next_bid_meeting_reserve": False,
                              "is_seller_bid_disclosed": False}
    assert out["fees"] == {"transaction_fee_percent": 5, "minimum_fee": 20000}
    assert out["terms"]["starting_bid"] == 25000 and out["terms"]["escrow_period_days"] == 27
    assert out["client_manager"] == {"name": "Alex Orth", "phone": None, "email": "jorth@crexi.com"}
    assert out["stats"]["registered_bidders"] == 0 and "auctionEndsInSeconds" not in json.dumps(out)
    assert "canEditSettings" not in json.dumps(out)


def test_auction_record_without_asset():
    out = P.parse_auction(fixture("auction_record.json"))
    assert out["terms"] is None and out["link"] == "https://www.crexi.com/properties/2732040"


# ---- lease -------------------------------------------------------------------------------

def test_lease_search_page():
    rows, total = P.parse_search_page(fixture("lease_search_page.json"), refs.LEASE)
    assert total == 1137 and len(rows) == 5
    row = rows[0]
    assert row["market"] == "lease" and row["link"].startswith("https://www.crexi.com/lease/properties/657336")
    assert row["spaces_count"] == 1 and row["rentable_sqft_min"] == 28070
    assert row["rate"]["type"] == "per_year" and row["rate"]["currency"] == "USD"
    assert row["location"]["city"] == "Austin" and row["brokerage"]["name"] == "JLL - Austin, Texas"
    rows, total = P.parse_search_page(fixture("lease_search_empty.json"), refs.LEASE)
    assert rows == [] and total == 83


def test_lease_search_row_rate_range():
    rows, _ = P.parse_search_page(fixture("lease_search_by_broker.json"), refs.LEASE)
    priced = [r for r in rows if r["rate"]["yearly_display"]]
    for row in priced:
        assert row["rate"]["yearly_min"] is not None
    page, _ = P.parse_search_page(fixture("lease_search_page.json"), refs.LEASE)
    unpriced = page[0]["rate"]
    assert unpriced["yearly_min"] is None and unpriced["per_sqft_yearly_min"] is None and unpriced["yearly_display"] is None


def test_lease_asset_core(lease):
    assert lease["id"] == 664397 and lease["market"] == "lease"
    assert lease["link"] == "https://www.crexi.com/lease/properties/664397/pennsylvania-crossroads-shopping-center"
    assert lease["property_types"] == ["Retail", "Office", "Restaurant"]
    assert lease["subtypes"] == ["Traditional Office", "Retail", "Shopping Center"]
    assert lease["rate"] == {"currency": "USD", "type": "per_year", "yearly_min": 15, "yearly_max": 22,
                             "monthly_min": 1.25, "monthly_max": 1.83, "display": "$15 - $22/SF/YR"}
    assert lease["building"]["total_sqft"] == 293798 and lease["building"]["class"] == "A"
    assert lease["building"]["parking_spaces"] == 1238 and lease["building"]["year_built"] is None
    assert lease["building"]["vacant_sqft"] is None and lease["building"]["total_spaces"] is None
    assert lease["tenancy"] is None and lease["is_single_tenant"] is False
    assert lease["details"] == {}
    assert lease["location"]["submarket"] == "Central Pennsylvania" and lease["location"]["submarket_cluster"] == "York"
    assert lease["marketing_description"].startswith("The Crossroads Shopping Center is York")
    assert lease["building_highlights"][0] == "York’s best located big box retail center"
    assert len(lease["building_highlights"]) == 6


def test_lease_asset_spaces(lease):
    spaces = lease["spaces"]
    assert lease["spaces_count"] == 12 and [s["position"] for s in spaces] == list(range(1, 13))
    first = spaces[0]
    assert first["id"] == 1607492 and first["name"] == "Space 2" and first["subtypes"] == ["Retail"]
    assert first["rentable_sqft"] == 9870 and first["rentable_sqft_max"] is None
    assert first["rate"]["base_rate_per_sqft"] == 20 and first["rate"]["total_rate_per_sqft"] == 24.05
    assert first["rate"]["display"] == "$20/SF/YR" and first["rate"]["type"] == "per_year"
    assert first["rate"]["total_monthly_rent"] == pytest.approx(19780.138)
    assert first["parking"] == 1238 and first["listing_type"] == "Direct"
    assert first["lease_term"] is None and first["lease_type"] is None and first["available_on"] is None
    assert first["has_floor_plan"] is True and first["floor_plan_image"].endswith(".PNG")
    assert len(first["photos"]) == 1 and first["photos"][0]["image"].startswith("https://crexi.com/images/")
    office_space = next(s for s in spaces if s["name"] == "Space 22")
    assert office_space["subtypes"] == ["Traditional Office"] and office_space["photos"] == []


def test_lease_asset_brokers_and_media(lease):
    assert len(lease["brokers"]) == 2
    assert lease["brokers"][0]["name"] == "Michael Willner" and lease["brokers"][0]["slug"] == "michaelwillner"
    assert lease["brokers"][0]["licenses"][0] == {"number": "FLBO", "state_code": "PA", "type": "Real Estate Sales Person",
                                                   "brokerage_phone": None, "is_auctioneer": None}
    assert lease["brokers"][1]["brokerage"] is None
    assert lease["media"]["photo_count"] == 5 and len(lease["media"]["photos"]) == 5


def test_lease_asset_survives_a_sparse_payload():
    out = P.parse_lease_asset({"id": 5, "suites": [{"id": 1}]}, None, None, None)
    assert out["spaces"][0]["id"] == 1 and out["spaces"][0]["rate"]["base_rate_per_sqft"] is None
    assert out["brokers"] is None and out["media"]["photos"] is None and out["rate"]["type"] is None


def test_lease_space_rate_range_keeps_its_minimum():
    # "$4 - $4.25/SF/MO": Crexi sends baseRateSqFtMin / Max and no baseRateSqFt
    out = P.parse_lease_asset(fixture("lease_asset_range_rates.json"))
    suite = out["spaces"][0]
    assert suite["rate"]["display"] == "$4 - $4.25/SF/MO" and suite["rate"]["type"] == "per_month"
    assert suite["rate"]["base_rate_per_sqft"] == 4 and suite["rate"]["base_rate_per_sqft_max"] == 4.25
    assert suite["rentable_sqft"] == 1230 and suite["rentable_sqft_max"] is None


def test_lease_space_size_range_keeps_its_minimum():
    suite = P.parse_space({"id": 7, "rentableSqFtIsRange": True, "rentableSqFtMin": 1500, "rentableSqFtMax": 4000,
                           "baseRateSqFt": 30.0, "baseRateSqFtIsRange": False})
    assert suite["rentable_sqft"] == 1500 and suite["rentable_sqft_max"] == 4000
    assert suite["rate"]["base_rate_per_sqft"] == 30 and suite["rate"]["base_rate_per_sqft_max"] is None


# ---- brokers -----------------------------------------------------------------------------

def test_broker_search():
    rows = P.parse_broker_search(fixture("broker_search.json"))
    assert rows[0] == {"id": 1742677, "global_id": "262a7831-336b-422d-8054-1123a8d6c3d8", "slug": "heatherhernd",
                       "link": "https://www.crexi.com/profile/heatherhernd", "name": "Heather Herndon",
                       "photo": rows[0]["photo"],
                       "brokerage": {"name": "Howard Hanna Real Estate Services", "city": "Jackson",
                                     "state_code": "MI", "country": "United States"},
                       "verification": "None"}
    assert P.parse_broker_search(fixture("broker_search_empty.json")) == []
    sparse = P.parse_broker_search(fixture("broker_search_paged.json"))[0]
    assert sparse["brokerage"]["name"] is None and sparse["photo"] is None


def test_broker_by_id():
    out = P.parse_broker(fixture("broker_profile.json"))
    assert out["id"] == 1742677 and out["slug"] == "heatherhernd" and out["name"] == "Heather Herndon"
    assert out["brokerage"]["name"] == "Howard Hanna Real Estate Services" and out["brokerage"]["location"] is None
    assert out["licenses"][0]["number"] == "MI 6501335416" and out["member_since"] == "2023-09-16T01:06:39.119Z"


def test_public_profile_merged():
    out = P.parse_public_profile(fixture("public_profile.json"), fixture("public_profile_lease_host.json"))
    assert out["id"] == 1742677 and out["slug"] == "heatherhernd"
    assert out["link"] == "https://www.crexi.com/profile/heatherhernd"
    assert out["name"] == "Heather Herndon" and out["phone"] is None
    assert out["about"].startswith("Thank you for visiting!") and out["experience_years"] == 18
    assert out["licenses"] == ["MI 6501335416"] and out["designations"] == ["REALTOR"]
    assert out["markets"] == ["Michigan Center", "Parma", "Grass Lake", "Spring Arbor", "Onsted"]
    assert out["lease_markets"] == ["Spring Arbor", "Jackson"]
    assert out["specialty_property_type"] == "Retail" and out["lease_specialty_property_type"] == "Office"
    assert out["roles"]["is_listing_broker"] is True and out["roles"]["is_tenant_rep_broker"] is False
    assert out["roles"]["other_role"] is None
    assert out["brokerage"]["website"] == "https://www.howardhanna.com/"
    assert out["stats"]["sale"]["active"] == {"listings": 12, "value": 7459400.0, "square_footage": 177232}
    assert out["stats"]["sale"]["closed"]["asking_to_sale_price_percent"] == 97.0
    assert out["stats"]["lease"]["active"] == {"listings": 8, "spaces": 8}
    assert out["header_image"].startswith("https://files.crexi.com/")


def test_public_profile_sale_only():
    out = P.parse_public_profile(fixture("public_profile_cbre.json"), None)
    assert out["name"] == "CBRE Multifamily Advisors" and out["stats"]["lease"] == {"active": None, "closed": None}
    assert out["stats"]["sale"]["closed"]["listings"] == 1 and out["lease_markets"] == []
    assert out["brokerage"]["location"]["city"] == "Los Angeles"


# ---- stats / suggestions -------------------------------------------------------------------

def test_stats():
    sale = P.parse_stats(fixture("stats_sale_type.json"), refs.SALE)
    assert sale[0] == {"name": "Land", "property_type": "Land", "city": None, "state_code": None, "listings": 125937}
    lease = P.parse_stats(fixture("stats_lease_city.json"), refs.LEASE)
    assert lease[0]["city"] == "Houston" and lease[0]["state_code"] == "TX" and lease[0]["spaces"] == 7831
    assert P.parse_stats([], refs.SALE) == []


def test_suggestions():
    rows = P.parse_suggestions(fixture("universal_search_sales.json"))
    assert rows[0]["id"] == 2749073 and rows[0]["market"] == "sale"
    assert rows[0]["link"] == "https://www.crexi.com/properties/2749073"
    assert rows[0]["full_address"] == "Austin, TX" and rows[0]["latitude"] is None
    assert rows[1]["zip"] == "48843" and rows[1]["latitude"] == pytest.approx(42.6147, abs=1e-3)
    lease = P.parse_suggestions(fixture("universal_search_lease.json"))
    assert lease[0]["market"] == "lease" and lease[0]["link"].startswith("https://www.crexi.com/lease/properties/")
    assert lease[1]["neighborhood"] == "Uptown Central"
    assert P.parse_suggestions(fixture("universal_search_empty.json")) == []
