"""Raw Crexi JSON -> clean dicts. Pure functions, no I/O.

Fixtures (crexi/fixtures/, captured 2026-11-07 from api.crexi.com and
api-lease.crexi.com): sale search pages (Austin TX, auctions, by broker,
empty, two 400 shapes), three sale assets (a plain office listing, a net
lease listing with tenants + investment highlights, an auction), their
gallery / brokers, the auction record, a lease asset (12 suites) with its
spaces / brokers / gallery, lease search pages, broker name search, broker
by id, two public profiles (sale host) + the lease host's, the stats and
universal-search rows, and the /lookups/* vocabularies. Added 2026-11-10:
lease_asset_range_rates.json (400 S Beverly Drive, suites quoted as a rate
range, which Crexi sends as baseRateSqFtMin / baseRateSqFtMax only).

Conventions: snake_case keys, `link` for URLs, booleans as questions, ISO
dates kept as the site sends them (UTC, "Z"), numbers as numbers, null for
absent values. The site renders its paywalled table rows as runs of "*"
("Year Built": "****") — those come back as null, never as the mask.
"""
import html as html_lib
import re

from crexi.refs import LEASE, SALE, broker_link, property_link

CURRENCY = "USD"

_MASK_RE = re.compile(r"^\*+$")
_NUMBER_RE = re.compile(r"^-?[0-9][0-9,]*(?:\.[0-9]+)?$")
_MONEY_RE = re.compile(r"^\$\s*(-?[0-9][0-9,]*(?:\.[0-9]+)?)$")
_PERCENT_RE = re.compile(r"^(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s*%$")
_MONEY_UNIT_RE = re.compile(r"^\$\s*(-?[0-9][0-9,]*(?:\.[0-9]+)?)\s*/\s*([A-Za-z/ ]+)$")
_TAG_RE = re.compile(r"<[^>]+>")
_LI_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.I | re.S)
_BLOCK_END_RE = re.compile(r"</(?:p|div|li|h[1-6]|tr)>|<br\s*/?>", re.I)
_ZERO_WIDTH_RE = re.compile(r"[​‌‍﻿]")
_SLUG_SPLIT_RE = re.compile(r"[^a-z0-9]+")


# ---- value helpers -------------------------------------------------------------

def is_masked(value):
    return isinstance(value, str) and bool(_MASK_RE.match(value.strip()))


def clean(value):
    """None for an empty string or a paywall mask; the value otherwise."""
    if value is None:
        return None
    if isinstance(value, str):
        value = _ZERO_WIDTH_RE.sub("", value).strip()
        if not value or is_masked(value):
            return None
    return value


def _num(text):
    text = text.replace(",", "")
    number = float(text)
    return int(number) if number.is_integer() else number


def typed(value):
    """A details-table cell -> number / bool / text / None: "$189,900" ->
    189900, "54,886" -> 54886, "6.2%" -> 6.2, "No" -> False, "****" -> None,
    "$20/SF/YR" stays text (the unit is the information)."""
    value = clean(value)
    if value is None or not isinstance(value, str):
        return value
    text = value
    if _NUMBER_RE.match(text):
        return _num(text)
    match = _MONEY_RE.match(text)
    if match:
        return _num(match.group(1))
    match = _PERCENT_RE.match(text)
    if match:
        return _num(match.group(1))
    if text.lower() in ("yes", "no"):
        return text.lower() == "yes"
    return text


def money_per_unit(value):
    """"$0/SF" / "$12.50/Acre" -> the number, None for a zero (the site's
    placeholder for 'not published')."""
    value = clean(value)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value or None
    match = _MONEY_UNIT_RE.match(value)
    if not match:
        return None
    return _num(match.group(1)) or None


def positive(value):
    """A count the site sends as 0 when unknown (squareFootage 0) -> None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value > 0 else None


def html_text(markup):
    """HTML -> plain text with block breaks as newlines (the marketing
    description is rich text; the office listing's is plain)."""
    markup = clean(markup)
    if not markup:
        return None
    text = _BLOCK_END_RE.sub("\n", markup)
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    text = _ZERO_WIDTH_RE.sub("", text).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    out = "\n".join(line for line in lines if line)
    return out or None


def html_list(markup):
    """An HTML <ul> -> list of item texts; any other markup -> its non-empty
    lines; None when nothing is left."""
    markup = clean(markup)
    if not markup:
        return None
    items = [html_text(item) for item in _LI_RE.findall(markup)]
    items = [i for i in items if i]
    if not items:
        text = html_text(markup)
        items = text.split("\n") if text else []
    return items or None


def snake(label):
    """A details-table label -> a key: "Lot Size (SqFt)" -> lot_size_sqft,
    "Price/SqFt (Land Value)" -> price_per_sqft_land_value, "Brand/Tenant"
    -> brand_tenant, "NOI" -> noi."""
    text = label.strip()
    if text.lower().startswith("price/"):
        text = "price per " + text[6:]
    text = text.replace("&", " and ")
    text = _SLUG_SPLIT_RE.sub("_", text.lower()).strip("_")
    return text


def details_table(table):
    """{"Year Built": "****", "Zoning": "C-2"} -> {"year_built": None,
    "zoning": "C-2"}; an absent table -> {}."""
    if not isinstance(table, dict):
        return {}
    return {snake(k): typed(v) for k, v in table.items() if k}


def _take(details, *keys):
    """Pop the first present key of a promoted field out of the table."""
    for key in keys:
        if key in details:
            return details.pop(key)
    return None


# ---- locations -----------------------------------------------------------------

def _state(value):
    if isinstance(value, dict):
        return clean(value.get("name")), clean(value.get("code"))
    return (clean(value), None) if isinstance(value, str) else (None, None)


def _coord(value):
    """A coordinate; 0.0 is the site's 'not geocoded' (brokerage offices)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value == 0:
        return None
    return value


def parse_location(loc):
    if not isinstance(loc, dict):
        return None
    state, state_code = _state(loc.get("state"))
    verified, verified_code = _state(loc.get("stateVerified"))
    address = clean(loc.get("address"))
    city = clean(loc.get("city")) or clean(loc.get("cityVerified"))
    zip_code = clean(loc.get("zip"))
    full = clean(loc.get("fullAddress"))
    if not full:
        parts = [address, city, clean(loc.get("county")), " ".join(p for p in (state_code or state, zip_code) if p)]
        full = ", ".join(p for p in parts if p) or None
    out = {
        "address": address,
        "city": city,
        "county": clean(loc.get("county")),
        "state": state or verified,
        "state_code": state_code or verified_code,
        "zip": zip_code,
        "country": clean(loc.get("country")),
        "full_address": full,
        "latitude": _coord(loc.get("latitude")),
        "longitude": _coord(loc.get("longitude")),
    }
    for key, raw in (("submarket", "submarket"), ("submarket_cluster", "submarketCluster")):
        if raw in loc:
            out[key] = clean(loc.get(raw))
    return out


def _locations(asset):
    """Sale assets carry `locations[]` (a portfolio has several), lease
    assets one `location`."""
    rows = asset.get("locations")
    if not isinstance(rows, list):
        rows = [asset.get("location")] if isinstance(asset.get("location"), dict) else []
    parsed = [parse_location(r) for r in rows if isinstance(r, dict)]
    return parsed[0] if parsed else None, parsed[1:]


# ---- media ---------------------------------------------------------------------

def parse_gallery(items):
    photos = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        kind = clean(item.get("type")) or "Image"
        row = {
            "id": item.get("id"),
            "type": kind.lower(),
            "image": clean(item.get("imageUrl")),
            "thumbnail": clean(item.get("mediumTnUrl")) or clean(item.get("smallTnUrl")),
        }
        for key in ("videoUrl", "url", "embedUrl"):
            if clean(item.get(key)):
                row["video"] = clean(item.get(key))
                break
        photos.append(row)
    return photos


def _media(asset, photos):
    return {
        "thumbnail": clean(asset.get("thumbnailUrl")),
        "photos": photos,
        "photo_count": len(photos) if photos is not None else positive(asset.get("numberOfImages")),
        "has_video": asset.get("hasVideo") if isinstance(asset.get("hasVideo"), bool) else None,
        "has_virtual_tour": asset.get("hasVirtualTour") if isinstance(asset.get("hasVirtualTour"), bool) else None,
        "has_offering_memorandum": asset.get("hasOM") if isinstance(asset.get("hasOM"), bool) else None,
        "has_flyer": asset.get("hasFlyer") if isinstance(asset.get("hasFlyer"), bool) else None,
    }


# ---- brokers -------------------------------------------------------------------

def _brokerage(raw):
    if not isinstance(raw, dict):
        return None
    out = {
        "name": clean(raw.get("name")),
        "logo": clean(raw.get("logoUrl")),
        "website": clean(raw.get("website")),
        "location": parse_location(raw.get("location")) if isinstance(raw.get("location"), dict) else None,
    }
    if out["location"] and not any(v for k, v in out["location"].items() if k not in ("country",)):
        out["location"] = None
    return out if any(out.values()) else None


def _licenses(raw):
    rows = []
    for item in raw.get("licenseDetails") or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "number": clean(item.get("number")),
            "state_code": clean(item.get("licenseStateCode")),
            "type": clean(item.get("typeId")),
            "brokerage_phone": clean(item.get("brokerageLicensePhone")),
            "is_auctioneer": bool(item.get("isAuctioneer")) if "isAuctioneer" in item else None,
        })
    if not rows:
        rows = [{"number": clean(n), "state_code": None, "type": None, "brokerage_phone": None, "is_auctioneer": None}
                for n in raw.get("licenses") or [] if clean(n)]
    return rows


def _name(first, last):
    parts = [clean(first), clean(last)]
    return " ".join(p for p in parts if p) or None


def parse_asset_broker(raw):
    """One row of GET /assets/<id>/brokers (sale and lease share the shape)."""
    slug = clean(raw.get("publicProfileId"))
    return {
        "id": raw.get("id"),
        "global_id": clean(raw.get("globalId")),
        "slug": slug,
        "link": broker_link(slug),
        "name": _name(raw.get("firstName"), raw.get("lastName")),
        "first_name": clean(raw.get("firstName")),
        "last_name": clean(raw.get("lastName")),
        "photo": clean(raw.get("thumbnailUrl")),
        "brokerage": _brokerage(raw.get("brokerage")),
        "licenses": _licenses(raw),
        "listings_count": raw.get("numberOfAssets") if isinstance(raw.get("numberOfAssets"), int) else None,
        "badges": [clean(b) for b in raw.get("badges") or [] if clean(b)],
        "is_platinum": bool(raw.get("isPlatinum")),
        "is_auctioneer": bool(raw.get("isAuctioneer")),
        "is_internal": bool(raw.get("isInternal")),
        "has_phone": bool(raw.get("hasPhone")),
        "has_email": bool(raw.get("hasEmail")),
        "is_contact_reveal_required": bool(raw.get("contactRevealRequired")),
        "verification": clean(raw.get("verificationMethod")),
        "member_since": clean(raw.get("createdOn")),
    }


def parse_asset_brokers(rows):
    return [parse_asset_broker(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def parse_broker_search(rows):
    """GET /brokers?name= rows."""
    out = []
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        slug = clean(raw.get("profileId"))
        out.append({
            "id": raw.get("id"),
            "global_id": clean(raw.get("globalId")),
            "slug": slug,
            "link": broker_link(slug),
            "name": clean(raw.get("fullName")),
            "photo": clean(raw.get("thumbnailUrl")),
            "brokerage": {
                "name": clean(raw.get("brokerageName")),
                "city": clean(raw.get("brokerageCity")),
                "state_code": clean(raw.get("brokerageStateCode")),
                "country": clean(raw.get("brokerageCountry")),
            },
            "verification": clean(raw.get("verificationMethod")),
        })
    return out


def parse_broker(raw):
    """GET /brokers/<id> (the short record; brokers/details prefers the
    public profile and uses this only to learn the profile slug)."""
    slug = clean(raw.get("publicProfileId"))
    return {
        "id": raw.get("id"),
        "global_id": clean(raw.get("globalId")),
        "slug": slug,
        "link": broker_link(slug),
        "name": _name(raw.get("firstName"), raw.get("lastName")),
        "first_name": clean(raw.get("firstName")),
        "last_name": clean(raw.get("lastName")),
        "photo": clean(raw.get("thumbnailUrl")),
        "brokerage": _brokerage(raw.get("brokerage")),
        "licenses": _licenses(raw),
        "is_auctioneer": bool(raw.get("isAuctioneer")),
        "verification": clean(raw.get("verificationMethod")),
        "member_since": clean(raw.get("createdOn")),
    }


def _stats_block(raw, keys):
    if not isinstance(raw, dict):
        return None
    out = {public: raw.get(site) for public, site in keys}
    return out if any(v is not None for v in out.values()) else None


def parse_public_profile(sale, lease=None):
    """GET /public-profiles/<slug> on the sale host (the profile) merged
    with the lease host's record (its lease-side stats)."""
    sale = sale or {}
    lease = lease or {}
    slug = clean(sale.get("publicProfileId")) or clean(lease.get("publicProfileId"))
    roles = sale.get("roles") if isinstance(sale.get("roles"), dict) else {}
    role_map = {
        "is_listing_broker": "isListingBroker", "is_buyside_broker": "isBuysideBroker",
        "is_landlord_broker": "isLandlordBroker", "is_tenant_rep_broker": "isTenantRepBroker",
        "is_transaction_coordinator": "isTransactionCoordinator", "is_coordinator": "isCoordinator",
    }
    parsed_roles = {public: bool(roles.get(site)) for public, site in role_map.items()}
    parsed_roles["other_role"] = clean(roles.get("otherRole")) or clean(roles.get("leaseOtherRole"))
    sale_stats = {
        "active": _stats_block(sale.get("activeAssetsStats"),
                               (("listings", "number"), ("value", "value"), ("square_footage", "squareFootage"))),
        "closed": _stats_block(sale.get("closedAssetsStats"),
                               (("listings", "number"), ("value", "value"), ("square_footage", "squareFootage"),
                                ("asking_to_sale_price_percent", "askingToSalePricePercent"))),
    }
    lease_stats = {
        "active": _stats_block(lease.get("activeAssetsStats"),
                               (("listings", "number"), ("spaces", "numberOfSuites"))),
        "closed": _stats_block(lease.get("closedAssetsStats"),
                               (("listings", "number"), ("square_footage", "squareFootage"))),
    }
    return {
        "id": sale.get("userId") or lease.get("userId"),
        "global_id": clean(sale.get("userGlobalId")) or clean(lease.get("userGlobalId")),
        "slug": slug,
        "link": broker_link(slug),
        "name": _name(sale.get("firstName") or lease.get("firstName"), sale.get("lastName") or lease.get("lastName")),
        "first_name": clean(sale.get("firstName")) or clean(lease.get("firstName")),
        "last_name": clean(sale.get("lastName")) or clean(lease.get("lastName")),
        "photo": clean(sale.get("photoUrl")),
        "header_image": clean(sale.get("headerUrl")),
        "phone": clean(sale.get("phone")),
        "about": clean(sale.get("about")),
        "experience_years": sale.get("experienceYears") if isinstance(sale.get("experienceYears"), int) else None,
        "specialty_property_type": clean(sale.get("specialityAssetType")),
        "lease_specialty_property_type": clean(lease.get("specialityAssetType")),
        "markets": [clean(m) for m in sale.get("markets") or [] if clean(m)],
        "lease_markets": [clean(m) for m in lease.get("markets") or [] if clean(m)],
        "licenses": [clean(n) for n in sale.get("licenseNumbers") or [] if clean(n)],
        "designations": [clean(d) for d in sale.get("designations") or [] if clean(d)],
        "badges": [clean(b) for b in (sale.get("badges") or lease.get("badges") or []) if clean(b)],
        "roles": parsed_roles,
        "brokerage": _brokerage(sale.get("brokerage")),
        "stats": {"sale": sale_stats, "lease": lease_stats},
        "is_platinum": bool(sale.get("isPlatinum") or lease.get("isPlatinum")),
        "hides_summary_statistics": bool(sale.get("hideSummaryStatistics")),
        "hides_closed_transactions": bool(sale.get("hideClosedTransaction")),
        "verification": clean(sale.get("verificationMethod")) or clean(lease.get("verificationMethod")),
        "updated_on": clean(sale.get("updatedOn")),
    }


# ---- sale listings -------------------------------------------------------------

def _brokerage_from_row(row):
    out = {
        "name": clean(row.get("brokerageName")),
        "logo": clean(row.get("brokerTeamLogoUrl")) or clean(row.get("brokerLogoUrl")),
        "broker_name": clean(row.get("brokerName")),
        "address": clean(row.get("fullBrokerageAddress")),
    }
    return out if any(out.values()) else None


def parse_sale_search_row(row):
    location, others = _locations(row)
    price = row.get("askingPrice")
    return {
        "id": row.get("id"),
        "link": property_link(row.get("id"), SALE, clean(row.get("urlSlug"))),
        "market": SALE,
        "name": clean(row.get("name")),
        "headline": clean(row.get("description")),
        "status": clean(row.get("status")),
        "property_types": [clean(t) for t in row.get("types") or [] if clean(t)],
        "investment_type": clean(row.get("investmentType")),
        "asking_price": price if isinstance(price, (int, float)) else None,
        "currency": CURRENCY,
        "is_unpriced": not isinstance(price, (int, float)),
        "square_footage": positive(row.get("squareFootage")),
        "price_per_sqft_land": money_per_unit(row.get("pricePerSqFtLand")),
        "price_per_acre_land": money_per_unit(row.get("pricePerAcreLand")),
        "offers_due_on": clean(row.get("offersDueOn")),
        "is_in_opportunity_zone": bool(row.get("isInOpportunityZone")),
        "is_new": bool(row.get("isNew")),
        "brokerage": _brokerage_from_row(row),
        "location": location,
        "other_locations": others,
        "media": {
            "thumbnail": clean(row.get("thumbnailUrl")),
            "photo_count": positive(row.get("numberOfImages")),
            "gallery_count": positive(row.get("numberOfGalleryItems")),
            "has_video": bool(row.get("hasVideo")),
            "has_virtual_tour": bool(row.get("hasVirtualTour")),
            "has_offering_memorandum": bool(row.get("hasOM")),
            "has_flyer": bool(row.get("hasFlyer")),
        },
        "listed_on": clean(row.get("activatedOn")),
        "updated_on": clean(row.get("updatedOn")),
    }


def parse_search_page(payload, market):
    """{"data": [...], "totalCount": n} -> (rows, total)."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    parse = parse_lease_search_row if market == LEASE else parse_sale_search_row
    parsed = [parse(r) for r in rows or [] if isinstance(r, dict)]
    total = payload.get("totalCount") if isinstance(payload, dict) else None
    return parsed, (total if isinstance(total, int) else None)


def _auction_terms(asset):
    out = {
        "starting_bid": None,       # filled from the details table by the caller
        "offers_due_on": clean(asset.get("offersDueOn")),
        "earnest_deposit": asset.get("earnestDepositAmount") if isinstance(asset.get("earnestDepositAmount"), (int, float)) else None,
        "is_earnest_deposit_percent": bool(asset.get("earnestDepositAmountInPercent")),
        "participation_deposit": asset.get("participationDepositAmount") if isinstance(asset.get("participationDepositAmount"), (int, float)) else None,
        "deposit_option": clean(asset.get("depositOption")),
        "escrow_period_days": asset.get("escrowPeriodCap") if isinstance(asset.get("escrowPeriodCap"), int) else None,
        "has_auctioneer": bool(asset.get("hasAuctioneer")),
    }
    return out


def _broker_of_record(asset):
    if not asset.get("hasBrokerOfRecord"):
        return None
    out = {
        "name": clean(asset.get("brokerOfRecordName")),
        "license": clean(asset.get("brokerOfRecordLicense")),
        "brokerage": clean(asset.get("brokerOfRecordBrokerageName")),
        "phone": clean(asset.get("brokerOfRecordPhone")),
    }
    return out if any(out.values()) else None


def _flag(asset, key):
    value = asset.get(key)
    return value if isinstance(value, bool) else None


def parse_sale_asset(asset, brokers=None, gallery=None):
    """GET /assets/<id> (sale host) + its brokers + gallery -> the
    properties/details record."""
    details = details_table(asset.get("details"))
    location, others = _locations(asset)
    status = clean(asset.get("status"))
    is_auction = status == "Auction"
    price = asset.get("askingPrice")
    starting_bid = _take(details, "starting_bid")
    tenancy = _take(details, "tenancy")
    lease = {
        "type": _take(details, "lease_type"),
        "term": _take(details, "lease_term"),
        "commencement": _take(details, "lease_commencement"),
        "expiration": _take(details, "lease_expiration"),
        "remaining_term": _take(details, "remaining_term"),
        "rent_bumps": _take(details, "rent_bumps"),
        "options": _take(details, "lease_options"),
        "is_ground_lease": _take(details, "ground_lease"),
    }
    financials = {
        "cap_rate": _take(details, "cap_rate"),
        "noi": _take(details, "noi"),
        "price_per_sqft": _take(details, "price_per_sqft"),
        "price_per_unit": _take(details, "price_per_unit"),
        "price_per_acre": _take(details, "price_per_acre"),
        "price_per_sqft_land_value": _take(details, "price_per_sqft_land_value"),
        "price_per_acre_land_value": _take(details, "price_per_acre_land_value"),
        "occupancy": _take(details, "occupancy"),
    }
    building = {
        "square_footage": _take(details, "square_footage"),
        "net_rentable_sqft": _take(details, "net_rentable_sqft"),
        "lot_size_acres": _take(details, "lot_size_acres"),
        "lot_size_sqft": _take(details, "lot_size_sqft"),
        "year_built": _take(details, "year_built"),
        "year_renovated": _take(details, "year_renovated"),
        "units": _take(details, "units"),
        "buildings": _take(details, "buildings"),
        "stories": _take(details, "stories"),
        "class": _take(details, "class"),
        "parking_spaces": _take(details, "parking_spaces"),
        "zoning": _take(details, "zoning"),
        "apn": _take(details, "apn"),
    }
    # the table repeats what the record carries as typed fields
    for key in ("asking_price", "property_type", "sub_type", "brand_tenant"):
        details.pop(key, None)
    investment_type = _take(details, "investment_type")
    tenants = [clean(t) for t in asset.get("tenants") or [] if clean(t)]
    other_tenants = [clean(t) for t in asset.get("customTenants") or [] if clean(t)]
    auction = _auction_terms(asset) if is_auction or starting_bid is not None else None
    if auction is not None:
        auction["starting_bid"] = starting_bid
    photos = parse_gallery(gallery) if gallery is not None else None
    return {
        "id": asset.get("id"),
        "link": property_link(asset.get("id"), SALE, clean(asset.get("urlSlug"))),
        "market": SALE,
        "name": clean(asset.get("name")),
        "headline": clean(asset.get("description")),
        "status": status,
        "is_auction": is_auction,
        "property_types": [clean(t) for t in asset.get("types") or [] if clean(t)],
        "subtypes": [clean(t) for t in asset.get("subtypes") or [] if clean(t)],
        "asking_price": price if isinstance(price, (int, float)) else None,
        "currency": CURRENCY,
        "is_unpriced": bool(asset.get("isUnpriced")) or not isinstance(price, (int, float)),
        "investment_type": investment_type,
        "tenancy": tenancy,
        "tenants": tenants,
        "other_tenants": other_tenants,
        "financials": financials,
        "building": building,
        "lease": lease if any(v is not None for v in lease.values()) else None,
        "details": details,
        "marketing_description": html_text(asset.get("marketingDescription")),
        "investment_highlights": html_list(asset.get("investmentHighlights")),
        "location": location,
        "other_locations": others,
        "is_address_hidden": bool(asset.get("hideAddress")),
        "auction": auction,
        "broker_of_record": _broker_of_record(asset),
        "brokers": parse_asset_brokers(brokers) if brokers is not None else None,
        "media": {**_media(asset, photos), "has_due_diligence_vault": bool(asset.get("hasVault"))},
        "is_in_opportunity_zone": bool(asset.get("isInOpportunityZone")),
        "is_note_or_loan": bool(asset.get("isNoteLoan")),
        "is_sold": bool(asset.get("isSold")),
        "is_paused": bool(asset.get("isPaused")),
        "is_private": bool(asset.get("isPrivate")),
        "is_elite": bool(asset.get("isElite")),
        "is_outdated": bool(asset.get("isOutdated")),
        "is_sell_subject_to": bool(asset.get("isSellSubjectTo")),
        "realtor_boards": [clean(b) for b in asset.get("realtorBoards") or [] if clean(b)],
        "created_on": clean(asset.get("createdOn")),
        "listed_on": clean(asset.get("activatedOn")),
        "updated_on": clean(asset.get("updatedOn")),
    }


# ---- auctions ------------------------------------------------------------------

def parse_auction(record, asset=None):
    """GET /auctions/<id> merged with the asset's own auction terms."""
    contact = record.get("clientManagerContact") if isinstance(record.get("clientManagerContact"), dict) else {}
    stats = record.get("stats") if isinstance(record.get("stats"), dict) else {}
    asset = asset or {}
    terms = _auction_terms(asset) if asset else None
    if terms is not None:
        terms["starting_bid"] = typed((asset.get("details") or {}).get("Starting Bid")) if isinstance(asset.get("details"), dict) else None
        terms.pop("has_auctioneer", None)
    slug = clean(asset.get("urlSlug")) if asset else None

    def amount(key):
        value = record.get(key)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    return {
        "id": record.get("id"),
        "link": property_link(record.get("id"), SALE, slug),
        "name": clean(record.get("propertyName")),
        "address": clean(record.get("propertyAddress")),
        "status": clean(record.get("auctionStatus")),
        "bidder_status": clean(record.get("auctionBidderStatus")),
        "type": clean(record.get("auctionType")),
        "marketing_starts_on": clean(record.get("auctionMarketingStartsOn")),
        "starts_on": clean(record.get("auctionStartsOn")),
        "ends_on": clean(record.get("auctionEndsOn")),
        "currency": CURRENCY,
        "bidding": {
            "starting_bid": amount("startingBid"),
            "minimum_bid": amount("minimumBidAmount"),
            "bid_increment": amount("bidIncrementAmount"),
            "is_reserve_met": bool(record.get("reserveMet")),
            "is_next_bid_meeting_reserve": bool(record.get("isNextBidMeetsReservePrice")),
            "is_seller_bid_disclosed": bool(record.get("isSellerBidDisclosed")),
        },
        "fees": {
            "transaction_fee_percent": amount("transactionFee"),
            "minimum_fee": amount("minimumFee"),
        },
        "terms": terms,
        "client_manager": {
            "name": clean(contact.get("name")),
            "phone": clean(contact.get("phone")),
            "email": clean(contact.get("email")),
        } if contact else None,
        "stats": {
            "registered_bidders": stats.get("numberOfRegisteredBidders"),
            "approved_bidders": stats.get("numberOfApprovedBidders"),
            "confidentiality_agreements": stats.get("numberOfCAUsers"),
            "flyer_opens": stats.get("numberOfOpenedFlyers"),
            "offering_memorandum_opens": stats.get("numberOfOpenedOMs"),
            "page_views": stats.get("numberOfPageViews"),
            "visitors": stats.get("numberOfVisitors"),
        } if stats else None,
        "has_due_diligence_vault": bool(record.get("hasVault")),
        "thumbnail": clean(record.get("thumbnailUrl")),
    }


# ---- lease listings ------------------------------------------------------------

def _rate_range(text):
    """"$15 - $22" -> (15, 22); "$18" -> (18, 18); None otherwise."""
    text = clean(text)
    if not text or not isinstance(text, str):
        return None, None
    numbers = re.findall(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)", text)
    if not numbers:
        return None, None
    values = [_num(n) for n in numbers]
    return values[0], values[-1]


def _rate_type(value):
    value = clean(value)
    return {"Per Year": "per_year", "Per Month": "per_month"}.get(value, value.lower().replace(" ", "_") if isinstance(value, str) else None)


def parse_lease_search_row(row):
    location = parse_location(row.get("location")) if isinstance(row.get("location"), dict) else None
    yearly_min, yearly_max = _rate_range(row.get("baseRateYearly"))
    monthly_min, monthly_max = _rate_range(row.get("baseRateMonthly"))
    sqft_min, sqft_max = positive(row.get("rentableSqftMin")), positive(row.get("rentableSqftMax"))
    return {
        "id": row.get("id"),
        "link": property_link(row.get("id"), LEASE, clean(row.get("urlSlug"))),
        "market": LEASE,
        "name": clean(row.get("name")),
        "headline": clean(row.get("description")),
        "status": clean(row.get("status")),
        "property_types": [clean(t) for t in row.get("types") or [] if clean(t)],
        "spaces_count": positive(row.get("numberOfSuites")),
        "rentable_sqft_min": sqft_min,
        "rentable_sqft_max": sqft_max,
        # yearly / monthly are what the site prints (a per-square-foot rate
        # for most buildings, a flat amount for some); per_sqft_yearly_* are
        # the site's own per-square-foot numbers, null when it published none
        "rate": {
            "currency": CURRENCY,
            "type": _rate_type(row.get("rateType")),
            "yearly_min": yearly_min,
            "yearly_max": yearly_max,
            "monthly_min": monthly_min,
            "monthly_max": monthly_max,
            "per_sqft_yearly_min": row.get("baseRateSqFtPerYearMin") if isinstance(row.get("baseRateSqFtPerYearMin"), (int, float)) else None,
            "per_sqft_yearly_max": row.get("baseRateSqFtPerYearMax") if isinstance(row.get("baseRateSqFtPerYearMax"), (int, float)) else None,
            "yearly_display": clean(row.get("baseRateYearly")),
            "monthly_display": clean(row.get("baseRateMonthly")),
        },
        "is_new": bool(row.get("isNew")),
        "is_outdated": bool(row.get("isOutdated")),
        "brokerage": _brokerage_from_row(row),
        "location": location,
        "media": {
            "thumbnail": clean(row.get("thumbnailUrl")),
            "photo_count": positive(row.get("numberOfImages")),
            "has_video": bool(row.get("hasVideo")),
            "has_virtual_tour": bool(row.get("hasVirtualTour")),
        },
        "listed_on": clean(row.get("activatedOn")),
    }


_SPACE_ITEM_KEYS = {
    "LeaseTerm": "lease_term", "LeaseType": "lease_type", "ExpenseRate": "expense_rate", "TotalCam": "cam",
    "SpaceUse": "space_use", "AvailableOn": "available_on", "Parking": "parking",
}


def _space_items(space_rows, suite_id):
    """The /spaces row of one suite -> {snake key: typed value} for the
    rows the suite record itself does not carry."""
    for row in space_rows or []:
        if isinstance(row, dict) and row.get("suiteId") == suite_id:
            out = {}
            for item in row.get("items") or []:
                if not isinstance(item, dict):
                    continue
                key = _SPACE_ITEM_KEYS.get(item.get("key"))
                if key:
                    value = item.get("value")
                    out[key] = [clean(v) for v in value if clean(v)] if isinstance(value, list) else typed(value)
            return out
    return {}


def _amount(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _low(suite, field):
    """`field`'s value, or a range's minimum: when `<field>IsRange` is true
    Crexi sends `<field>Min` / `<field>Max` and no `<field>` at all (a suite
    quoted "$4 - $4.25/SF/MO" has baseRateSqFtMin 4.0, baseRateSqFtMax 4.25)."""
    value = _amount(suite.get(field))
    if value is None and suite.get(f"{field}IsRange"):
        value = _amount(suite.get(f"{field}Min"))
    return value


def parse_space(suite, space_rows=None):
    extra = _space_items(space_rows, suite.get("id"))
    photos = parse_gallery(suite.get("gallery"))
    space_use = extra.get("space_use")
    if space_use is None:
        space_use = [clean(u) for u in suite.get("spaceUse") or [] if clean(u)] or None
    parking = extra.get("parking", typed(suite.get("parking")))
    return {
        "id": suite.get("id"),
        "name": clean(suite.get("name")),
        "status": clean(suite.get("status")),
        "listing_type": clean(suite.get("listingType")),
        "position": suite.get("position"),
        "subtypes": [clean(t) for t in (suite.get("subtypes") or []) + (suite.get("customSubtypes") or []) if clean(t)],
        "space_use": space_use if isinstance(space_use, list) else ([space_use] if space_use else []),
        "rentable_sqft": positive(_low(suite, "rentableSqFt")),
        "rentable_sqft_max": positive(suite.get("rentableSqFtMax")) if suite.get("rentableSqFtIsRange") else None,
        "rentable_acres": positive(_low(suite, "rentableAcre")),
        "rate": {
            "currency": CURRENCY,
            "type": _rate_type(suite.get("rateType")),
            "base_rate_per_sqft": _low(suite, "baseRateSqFt"),
            "base_rate_per_sqft_max": _amount(suite.get("baseRateSqFtMax")) if suite.get("baseRateSqFtIsRange") else None,
            "base_rate_per_acre": _low(suite, "baseRateAcre"),
            "total_rate_per_sqft": suite.get("totalRate") if isinstance(suite.get("totalRate"), (int, float)) else None,
            "total_monthly_rent": suite.get("totalMonthlyRent") if isinstance(suite.get("totalMonthlyRent"), (int, float)) else None,
            "display": clean(suite.get("displayBaseRate")),
        },
        "lease_term": extra.get("lease_term"),
        "lease_type": extra.get("lease_type"),
        "expense_rate": extra.get("expense_rate"),
        "cam": extra.get("cam"),
        "available_on": extra.get("available_on"),
        "parking": parking,
        "has_floor_plan": bool(suite.get("hasFloorPlan")),
        "floor_plan_image": clean(suite.get("floorplanImageUrl")),
        "has_flyer": bool(suite.get("hasFlyer")),
        "photos": photos,
        "is_outdated": bool(suite.get("isOutdated")),
        "listed_on": clean(suite.get("activatedOn")),
        "updated_on": clean(suite.get("updatedOn")),
    }


def parse_lease_asset(asset, brokers=None, gallery=None, spaces=None):
    """GET /assets/<id> (lease host) + brokers + gallery + spaces -> the
    leases/details record."""
    details = details_table(asset.get("details"))
    location, others = _locations(asset)
    for key in ("property_type", "subtype"):
        details.pop(key, None)
    building = {
        "total_sqft": _take(details, "total_building_sqft"),
        "vacant_sqft": _take(details, "vacant_sqft"),
        "min_divisible_sqft": _take(details, "minimum_divisible_sqft"),
        "max_contiguous_sqft": _take(details, "max_contiguous_sqft"),
        "total_spaces": _take(details, "total_building_suites"),
        "lot_size_acres": _take(details, "lot_size_acres"),
        "lot_size_sqft": _take(details, "lot_size_sqft"),
        "year_built": _take(details, "year_built"),
        "year_renovated": _take(details, "year_renovated"),
        "buildings": _take(details, "buildings"),
        "stories": _take(details, "stories"),
        "class": _take(details, "class"),
        "parking_spaces": _take(details, "total_parking_spaces"),
        "zoning": _take(details, "zoning"),
        "apn": _take(details, "apn"),
        "cross_street": _take(details, "cross_street"),
    }
    tenancy = _take(details, "tenancy")
    for key in ("submarket", "submarket_cluster"):
        details.pop(key, None)   # the location block carries them unmasked
    suites = [parse_space(s, spaces) for s in asset.get("suites") or [] if isinstance(s, dict)]
    suites.sort(key=lambda s: (s["position"] is None, s["position"] or 0))
    yearly_min, yearly_max = _rate_range(asset.get("baseRateYearly") or asset.get("rateYearlyPerSqft"))
    monthly_min, monthly_max = _rate_range(asset.get("baseRateMonthly") or asset.get("rateMonthlyPerSqft"))
    photos = parse_gallery(gallery) if gallery is not None else None
    rate_types = {s["rate"]["type"] for s in suites if s["rate"]["type"]}
    return {
        "id": asset.get("id"),
        "link": property_link(asset.get("id"), LEASE, clean(asset.get("urlSlug"))),
        "market": LEASE,
        "name": clean(asset.get("name")),
        "headline": clean(asset.get("description")),
        "status": clean(asset.get("status")),
        "property_types": [clean(t) for t in asset.get("types") or [] if clean(t)],
        "subtypes": [clean(t) for t in (asset.get("subtypes") or []) + (asset.get("customSubtypes") or []) if clean(t)],
        "tenancy": tenancy,
        "is_single_tenant": bool(asset.get("isSingleTenant")),
        # the range the site prints across the spaces (per square foot when
        # `display` ends in /SF/YR, a flat amount otherwise); each space
        # carries its own per-square-foot rate
        "rate": {
            "currency": CURRENCY,
            "type": rate_types.pop() if len(rate_types) == 1 else None,
            "yearly_min": yearly_min,
            "yearly_max": yearly_max,
            "monthly_min": monthly_min,
            "monthly_max": monthly_max,
            "display": clean(asset.get("aggregateDisplayBaseRate")),
        },
        "building": building,
        "details": details,
        "marketing_description": html_text(asset.get("marketingDescription")),
        "building_highlights": html_list(asset.get("buildingHighlights")),
        "location": location,
        "other_locations": others,
        "spaces": suites,
        "spaces_count": len(suites),
        "brokers": parse_asset_brokers(brokers) if brokers is not None else None,
        "media": _media(asset, photos),
        "is_paused": bool(asset.get("isPaused")),
        "is_outdated": bool(asset.get("isOutdated")),
        "realtor_boards": [clean(b) for b in asset.get("realtorBoards") or [] if clean(b)],
        "created_on": clean(asset.get("createdOn")),
        "listed_on": clean(asset.get("activatedOn")),
        "updated_on": clean(asset.get("updatedOn")),
    }


# ---- stats / suggestions -------------------------------------------------------

def parse_stats(rows, market):
    out = []
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        filters = raw.get("filters") if isinstance(raw.get("filters"), dict) else {}
        row = {
            "name": clean(raw.get("title")),
            "property_type": clean(filters.get("assetType")),
            "city": clean(filters.get("cityOrNeighborhood")),
            "state_code": clean(filters.get("stateCode")),
            "listings": raw.get("numberOfAssets") if isinstance(raw.get("numberOfAssets"), int) else None,
        }
        if market == LEASE:
            row["spaces"] = raw.get("numberOfSuites") if isinstance(raw.get("numberOfSuites"), int) else None
        out.append(row)
    return out


def parse_suggestions(rows):
    out = []
    for raw in rows if isinstance(rows, list) else []:
        if not isinstance(raw, dict):
            continue
        kind = (clean(raw.get("type")) or "").lower()
        market = LEASE if kind == "lease" else SALE
        ident = clean(raw.get("id")) or ""
        asset_id = int(ident.rsplit("-", 1)[-1]) if ident.rsplit("-", 1)[-1].isdigit() else None
        address = raw.get("address") if isinstance(raw.get("address"), dict) else {}
        point = address.get("location") if isinstance(address.get("location"), dict) else {}
        out.append({
            "id": asset_id,
            "market": market,
            "link": property_link(asset_id, market) if asset_id else None,
            "full_address": clean(address.get("fullAddress")),
            "street": clean(address.get("streetAddress")),
            "city": clean(address.get("city")),
            "neighborhood": clean(address.get("neighborhood")),
            "county": clean(address.get("county")),
            "state": clean(address.get("stateName")),
            "state_code": clean(address.get("stateCode")),
            "zip": clean(address.get("zip")),
            "latitude": point.get("lat") if isinstance(point.get("lat"), (int, float)) else None,
            "longitude": point.get("lon") if isinstance(point.get("lon"), (int, float)) else None,
            "slug": clean(address.get("slug")),
        })
    return out
