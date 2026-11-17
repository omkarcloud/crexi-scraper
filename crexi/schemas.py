"""Marshmallow request schemas for every /crexi/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    property   a Crexi asset id (2715395) OR any crexi.com property link;
               a bare id is a SALE listing on /crexi/properties/* and a
               LEASE listing on /crexi/leases/*, a link decides for itself
               (/lease/properties/… is a lease)
    broker     a numeric broker id (1742677), a profile slug (heatherhernd)
               OR a crexi.com/profile/<slug> link
    state      two-letter US state codes, comma-separated
    city / county / zip   comma-separated names / codes, as the site spells them

The filter vocabularies (property types, subtypes, classes, tenancies,
lease types, investment types, statuses, sorts) are the site's own
(crexi/refs.py, read from /lookups/* on 2026-11-07); every field carries a
`description` because it becomes the public docs.
"""
from marshmallow import ValidationError, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CommaListField, DateField, Flag, LimitField,
                           NonNegativeNumber, PageField, PageSizeField, Price, QueryField, RefField,
                           StrippedString)
from crexi import refs
from scraper_utils.schema import max_length as _max_length

MAX_PAGE_SIZE = 100    # the site serves up to 500; 100 keeps a page under ~200 KB
DEFAULT_PAGE_SIZE = 20


def _optional_text(description, n=200):
    return StrippedString(required=False, load_default=None, validate=_max_length(n),
                          metadata={"description": description})


class SalePropertyRefField(RefField):
    """Bare id = a sale listing; a link decides for itself."""
    resolver = staticmethod(lambda v: refs.resolve_property(v, refs.SALE))


class LeasePropertyRefField(RefField):
    """Bare id = a lease listing; a link decides for itself."""
    resolver = staticmethod(lambda v: refs.resolve_property(v, refs.LEASE))


class BrokerRefField(RefField):
    resolver = staticmethod(refs.resolve_broker)


class StateListField(CommaListField):
    def __init__(self, **kwargs):
        kwargs.setdefault("allowed", refs.STATES)
        kwargs.setdefault("max_items", 20)
        super().__init__(**kwargs)


def _names(description, max_items=10):
    return CommaListField(upper=False, max_items=max_items, metadata={"description": description})


def _values(allowed, description, max_items=10):
    return CommaListField(allowed=allowed, upper=False, max_items=max_items, metadata={"description": description})


def _mapped(value_map, description, max_items=10):
    return CommaListField(value_map=value_map, upper=False, max_items=max_items, metadata={"description": description})


def _window_check(data):
    """The search API refuses offset + count >= 1500 on both hosts."""
    page, per_page = data.get("page") or 1, data.get("per_page") or DEFAULT_PAGE_SIZE
    if page * per_page > refs.MAX_SEARCH_WINDOW:
        raise ValidationError(
            f"Crexi serves at most {refs.MAX_SEARCH_WINDOW:,} results per search (page x per_page must stay "
            f"below 1,500); narrow the filters instead of paging deeper.", "page")


class _SearchCommon(BaseSchema):
    query = _optional_text("keyword matched against listing names, addresses and descriptions")
    state = StateListField(metadata={"description": "two-letter US state codes, comma-separated (TX,CA)"})
    city = _names("city names, comma-separated (Austin,Dallas)")
    county = _names("county names as the site spells them, comma-separated (Travis County)")
    zip = CommaListField(max_items=20, metadata={"description": "US ZIP codes, comma-separated"})
    min_sqft = NonNegativeNumber(metadata={"description": "minimum building square footage"})
    max_sqft = NonNegativeNumber(metadata={"description": "maximum building square footage"})
    min_acres = NonNegativeNumber(metadata={"description": "minimum lot size in acres"})
    max_acres = NonNegativeNumber(metadata={"description": "maximum lot size in acres"})
    building_class = _values(refs.BUILDING_CLASSES, "building class, comma-separated (A,B,C,D)", 4)
    listed_since = DateField(bound="past", metadata={"description": "only listings activated on or after this date (YYYY-MM-DD)"})
    brokerage = _optional_text("brokerage name to filter by (Howard Hanna)", 120)
    sort_direction = ChoiceField(list(refs.SORT_DIRECTIONS), load_default="desc", metadata={
        "description": "asc or desc (default desc)"})
    page = PageField(max_page=refs.MAX_SEARCH_WINDOW, metadata={"description": "1-based page"})
    per_page = PageSizeField(default=DEFAULT_PAGE_SIZE, max_size=MAX_PAGE_SIZE, metadata={
        "description": f"results per page, default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}"})

    @validates_schema
    def _window(self, data, **kwargs):
        _window_check(data)


class PropertiesSearchSchema(_SearchCommon):
    property_type = _values(refs.SALE_TYPES, "property types, comma-separated: " + ", ".join(refs.SALE_TYPES))
    subtype = _values(refs.SALE_SUBTYPE_VALUES, "property subtypes, comma-separated (Warehouse, Medical Office, Gas Station, Apartment Building, …)")
    min_price = Price(metadata={"description": "minimum asking price in USD"})
    max_price = Price(metadata={"description": "maximum asking price in USD"})
    min_cap_rate = NonNegativeNumber(metadata={"description": "minimum cap rate in percent (6 = 6%)"})
    max_cap_rate = NonNegativeNumber(metadata={"description": "maximum cap rate in percent"})
    min_price_per_sqft = Price(metadata={"description": "minimum asking price per square foot in USD"})
    max_price_per_sqft = Price(metadata={"description": "maximum asking price per square foot in USD"})
    min_occupancy = NonNegativeNumber(metadata={"description": "minimum occupancy in percent"})
    max_occupancy = NonNegativeNumber(metadata={"description": "maximum occupancy in percent"})
    min_remaining_term = NonNegativeNumber(metadata={"description": "minimum remaining lease term in years (net lease listings)"})
    max_remaining_term = NonNegativeNumber(metadata={"description": "maximum remaining lease term in years"})
    tenancy = ChoiceField(list(refs.SALE_TENANCIES), metadata={"description": "vacant, single or multi"})
    tenant = _names("tenant brands on the property, comma-separated (Starbucks,Dollar General)")
    tenant_credit = ChoiceField(list(refs.TENANT_CREDITS), metadata={"description": "franchisee or corporate_guarantee"})
    lease_type = _mapped(refs.SALE_LEASE_TYPES, "lease structure of the tenant in place, comma-separated: " + ", ".join(refs.SALE_LEASE_TYPES))
    investment_type = ChoiceField(list(refs.INVESTMENT_TYPES), metadata={
        "description": "one of " + ", ".join(refs.INVESTMENT_TYPES)})
    status = ChoiceField(list(refs.SALE_STATUSES), load_default="active", metadata={
        "description": "active (default), under_contract, contract_pending or auction"})
    opportunity_zone = Flag(metadata={"description": "true = only listings in an Opportunity Zone"})
    include_unpriced = Flag(load_default=True, metadata={
        "description": "include listings without a published asking price (default true)"})
    sort = ChoiceField(list(refs.SALE_SORTS), load_default="relevance", metadata={
        "description": "relevance (default), newest, updated, price, cap_rate or size"})


class LeasesSearchSchema(_SearchCommon):
    property_type = _values(refs.LEASE_TYPES, "property types, comma-separated: " + ", ".join(refs.LEASE_TYPES))
    subtype = _values(refs.LEASE_SUBTYPE_VALUES, "space subtypes, comma-separated (Warehouse, Flex, Medical Office, Coworking, …)")
    tenancy = ChoiceField(list(refs.LEASE_TENANCIES), metadata={"description": "single or multiple"})
    include_undisclosed_rate = Flag(load_default=True, metadata={
        "description": "include buildings whose asking rate is not published (default true)"})
    sort = ChoiceField(list(refs.LEASE_SORTS), load_default="relevance", metadata={
        "description": "relevance (default), newest, updated, rate or size"})


class PropertySchema(BaseSchema):
    property = SalePropertyRefField(metadata={
        "description": "Crexi asset id (2715395) or a crexi.com property link; a bare id is a sale listing"})


class LeaseSchema(BaseSchema):
    property = LeasePropertyRefField(metadata={
        "description": "Crexi lease asset id (664397) or a crexi.com/lease/properties/… link"})


class AuctionSchema(BaseSchema):
    property = SalePropertyRefField(metadata={
        "description": "Crexi asset id or property link of an auction listing"})


class BrokersSearchSchema(BaseSchema):
    query = QueryField(metadata={"description": "broker or brokerage name to search for"})
    limit = LimitField(default=20, max_size=refs.MAX_BROKER_RESULTS, metadata={
        "description": f"results to return, default 20, max {refs.MAX_BROKER_RESULTS} (the site's own cap)"})


class BrokerSchema(BaseSchema):
    broker = BrokerRefField(metadata={
        "description": "broker id (1742677), profile slug (heatherhernd) or a crexi.com/profile/<slug> link"})


class BrokerListingsSchema(BaseSchema):
    broker = BrokerRefField(metadata={
        "description": "broker id (1742677), profile slug (heatherhernd) or a crexi.com/profile/<slug> link"})
    market = ChoiceField(list(refs.MARKETS), load_default=refs.SALE, metadata={
        "description": "sale (default) or lease listings"})
    sort = ChoiceField(["newest", "updated", "price", "size"], load_default="newest", metadata={
        "description": "newest (default), updated, price (sale only) or size"})
    page = PageField(max_page=refs.MAX_SEARCH_WINDOW, metadata={"description": "1-based page"})
    per_page = PageSizeField(default=DEFAULT_PAGE_SIZE, max_size=MAX_PAGE_SIZE, metadata={
        "description": f"results per page, default {DEFAULT_PAGE_SIZE}, max {MAX_PAGE_SIZE}"})

    @validates_schema
    def _window(self, data, **kwargs):
        _window_check(data)
        if data.get("market") == refs.LEASE and data.get("sort") == "price":
            raise ValidationError("lease listings have no asking price; sort by newest, updated or size.", "sort")


class MarketStatsSchema(BaseSchema):
    group_by = ChoiceField(list(refs.STATS_GROUPS), load_default="property_type", metadata={
        "description": "property_type (default) or city"})
    market = ChoiceField(list(refs.MARKETS), load_default=refs.SALE, metadata={
        "description": "sale (default) or lease"})


class LocationsSuggestSchema(BaseSchema):
    query = QueryField(metadata={"description": "a city, street or address fragment (Austin, 5th Street)"})
    market = ChoiceField(list(refs.SUGGEST_MARKETS), load_default="both", metadata={
        "description": "sale, lease or both (default)"})
