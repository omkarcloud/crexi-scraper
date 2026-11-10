"""Reference resolvers, links and the filter vocabularies for /crexi/*.

Crexi (www.crexi.com) is a US commercial real estate marketplace with two
record namespaces served by two JSON hosts:

  * SALE   properties for sale, api.crexi.com, site link
           https://www.crexi.com/properties/<id>/<slug>
  * LEASE  buildings with space for lease, api-lease.crexi.com, site link
           https://www.crexi.com/lease/properties/<id>/<slug>

The numeric asset ids of the two namespaces overlap (sale 664397 and lease
664397 are different buildings), so a bare id needs the endpoint's market
while a site link carries its own (/lease/ in the path).

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair): `property` accepts a bare asset id OR any crexi.com
property link (sale or lease, slug optional, the api hosts' /assets/<id>
too); `broker` accepts a numeric broker id, a profile slug (heatherhernd)
OR a crexi.com/profile/<slug> link. Resolvers raise ValueError with a
user-facing message (RefField turns it into a 400).

The vocabularies below are the site's own, read from api.crexi.com and
api-lease.crexi.com /lookups/* on 2026-11-07 (crexi/fixtures/lookups_*.json)
and verified one by one against POST /assets/search (a value the search
rejects answers 400 "The supplied value is invalid").
"""
import re
from urllib.parse import urlparse

SITE = "https://www.crexi.com"
SALE_API = "https://api.crexi.com"
LEASE_API = "https://api-lease.crexi.com"

SALE, LEASE = "sale", "lease"
MARKETS = (SALE, LEASE)
API_HOST = {SALE: SALE_API, LEASE: LEASE_API}

_ID_RE = re.compile(r"^[0-9]{1,10}$")
_LINK_RE = re.compile(r"^/(?:(lease)/)?properties/([0-9]{1,10})(?:/|$)")
_API_LINK_RE = re.compile(r"^/assets/([0-9]{1,10})(?:/|$)")
_PROFILE_RE = re.compile(r"^/profile/([A-Za-z0-9_.-]{1,80})(?:/|$)")
_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{2,80}$")


def _as_url(value):
    if value.startswith(("http://", "https://", "//")):
        return value if not value.startswith("//") else "https:" + value
    return None


def _host(url):
    return (urlparse(url).hostname or "").lower()


def resolve_property(value, default_market=SALE):
    """Bare asset id OR a crexi.com property link -> {"id": int, "market":
    "sale" | "lease"}. A bare id takes `default_market` (the endpoint's);
    a link decides for itself (/lease/properties/… or api-lease.crexi.com)."""
    value = (value or "").strip()
    if _ID_RE.match(value):
        return {"id": int(value), "market": default_market}
    url = _as_url(value)
    if url:
        host = _host(url)
        path = urlparse(url).path
        if host in ("www.crexi.com", "crexi.com"):
            match = _LINK_RE.match(path)
            if match:
                return {"id": int(match.group(2)), "market": LEASE if match.group(1) else SALE}
            raise ValueError("Must be a crexi.com property link "
                             "(https://www.crexi.com/properties/<id>/<slug> or "
                             "https://www.crexi.com/lease/properties/<id>/<slug>).")
        if host in ("api.crexi.com", "api-lease.crexi.com"):
            match = _API_LINK_RE.match(path)
            if match:
                return {"id": int(match.group(1)), "market": LEASE if host.startswith("api-lease") else SALE}
        raise ValueError("Must be a crexi.com link.")
    raise ValueError("Must be a Crexi asset id (2715395) or a crexi.com property link "
                     "(https://www.crexi.com/properties/2715395/michigan-215-east-main-street).")


def resolve_broker(value):
    """Numeric broker id, a profile slug OR a crexi.com/profile/<slug> link
    -> {"id": int} | {"slug": str}."""
    value = (value or "").strip()
    if _ID_RE.match(value):
        return {"id": int(value)}
    url = _as_url(value)
    if url:
        host = _host(url)
        if host not in ("www.crexi.com", "crexi.com"):
            raise ValueError("Must be a crexi.com link.")
        match = _PROFILE_RE.match(urlparse(url).path)
        if match:
            return {"slug": match.group(1)}
        raise ValueError("Must be a crexi.com broker profile link (https://www.crexi.com/profile/<slug>).")
    if _SLUG_RE.match(value) and "/" not in value:
        return {"slug": value}
    raise ValueError("Must be a Crexi broker id (1742677), a profile slug (heatherhernd) "
                     "or a profile link (https://www.crexi.com/profile/heatherhernd).")


def property_link(asset_id, market=SALE, slug=None):
    base = f"{SITE}/lease/properties/{asset_id}" if market == LEASE else f"{SITE}/properties/{asset_id}"
    return f"{base}/{slug}" if slug else base


def broker_link(slug):
    return f"{SITE}/profile/{slug}" if slug else None


# ---- US states ---------------------------------------------------------------------
STATES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY",
    "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "PR",
)

# ---- property types (GET /lookups/asset-types, 2026-11-07) ---------------------------
SALE_TYPES = ("Retail", "Multifamily", "Office", "Industrial", "Hospitality", "Mixed Use", "Land",
              "Self Storage", "Mobile Home Park", "Senior Living", "Special Purpose", "Note/Loan",
              "Business for Sale")
LEASE_TYPES = ("Retail", "Office", "Industrial", "Land", "Restaurant", "Special Purpose")

# type -> subtypes (GET /lookups/subtypes on each host, 2026-11-07)
SALE_SUBTYPES = {
    "Multifamily": ("Student Housing", "Single Family Rental Portfolio", "RV Park", "Apartment Building"),
    "Retail": ("Bank", "Convenience Store", "Day Care/Nursery", "QSR/Fast Food", "Gas Station", "Grocery Store",
               "Pharmacy/Drug", "Restaurant", "Bar", "Storefront", "Shopping Center", "Auto Shop"),
    "Office": ("Traditional Office", "Executive Office", "Medical Office", "Creative Office"),
    "Industrial": ("Distribution", "Flex", "Warehouse", "R&D", "Manufacturing", "Refrigerated/Cold Storage"),
    "Hospitality": ("Hotel", "Motel", "Casino"),
    "Land": ("Agricultural", "Residential", "Commercial", "Industrial", "Islands", "Farm", "Ranch", "Timber",
             "Hunting/Recreational"),
    "Special Purpose": ("Telecom/Data Center", "Sports/Entertainment", "Marina", "Golf Course", "School",
                        "Religious/Church", "Garage/Parking", "Car Wash", "Airport"),
    "Business for Sale": ("Business Only", "Business and Building"),
}
LEASE_SUBTYPES = {
    "Office": ("Traditional Office", "Executive Office", "Coworking", "Medical Office", "Creative Office"),
    "Industrial": ("Refrigerated/Cold Storage", "Manufacturing", "Flex", "Warehouse", "Distribution", "R&D"),
    "Land": ("Agricultural", "Residential", "Commercial", "Industrial"),
    "Special Purpose": ("Airport",),
}


def _flat(table):
    out = []
    for values in table.values():
        for v in values:
            if v not in out:
                out.append(v)
    return tuple(out)


SALE_SUBTYPE_VALUES = _flat(SALE_SUBTYPES)
LEASE_SUBTYPE_VALUES = _flat(LEASE_SUBTYPES)

# ---- other filter vocabularies (verified against /assets/search, 2026-11-07) --------
BUILDING_CLASSES = ("A", "B", "C", "D")
SALE_TENANCIES = {"vacant": "Vacant", "single": "Single", "multi": "Multi"}
LEASE_TENANCIES = {"single": "Single", "multiple": "Multiple"}
# the sale search's `leaseTypes` (the lease structure of the tenant in place)
SALE_LEASE_TYPES = {"net": "Net", "nnn": "NNN", "absolute_net": "Absolute Net", "gross": "Gross",
                    "modified": "Modified", "ground": "Ground"}
INVESTMENT_TYPES = {"institutional": "Institutional", "stabilized": "Stabilized", "value_add": "Value Add",
                    "redevelopment": "Redevelopment", "owner_user": "Owner/User", "core_plus": "Core+",
                    "core": "Core", "net_lease": "Net Lease", "sale_leaseback": "Sale/Leaseback"}
# the only two `tenantCredits` values the search accepted on 2026-11-07
TENANT_CREDITS = {"franchisee": "Franchisee", "corporate_guarantee": "Corporate Guarantee"}
# sale listing status: `statuses` values, except "Auction" which the search
# takes as a `tradingStatuses` value (api.py routes it)
SALE_STATUSES = {"active": "Active Listings", "under_contract": "Under Contract",
                 "contract_pending": "Contract Pending", "auction": "Auction"}
SALE_SORTS = {"relevance": "rank", "newest": "activatedOn", "updated": "updatedOn", "price": "price",
              "cap_rate": "capRate", "size": "sqft"}
LEASE_SORTS = {"relevance": "rank", "newest": "activatedOn", "updated": "updatedOn", "rate": "rate",
               "size": "sqft"}
SORT_DIRECTIONS = {"asc": "Ascending", "desc": "Descending"}
STATS_GROUPS = {"property_type": "AssetType", "city": "CityOrNeighborhood"}
SUGGEST_MARKETS = {"sale": ["Sales"], "lease": ["Lease"], "both": ["Sales", "Lease"]}

# The search API refuses offset + count >= 1500 ("Offset + Count must be
# less than 1500"), on both hosts.
MAX_SEARCH_WINDOW = 1499
# GET /brokers?name= answers at most 50 rows and ignores count / offset.
MAX_BROKER_RESULTS = 50
