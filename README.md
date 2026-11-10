# 🏢 Crexi Scraper

Crexi Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Crexi data for free.

## ✨ What Can I Get?

- 🏢 **Full details on 250K+ properties for sale** — asking price, building facts, highlights, brokers & every photo
- 🔑 **180K+ buildings for lease** — every one of 400K+ spaces with size, asking rent & floor plan
- 🔍 **30+ search filters & live auctions** — location, type, price, cap rate, tenant brand, starting bids & reserves
- 🤝 **Every Crexi broker's profile** — licenses, brokerage, markets & active and closed deal stats

## 🎥 Example: A Full Crexi Property

```json
{
  "id": 2345196,
  "link": "https://www.crexi.com/properties/2345196/california-prime-beverly-hills-medical-office-facility",
  "name": "Prime Beverly Hills Medical Office Facility",
  "status": "Active",
  "property_types": ["Office"],
  "subtypes": ["Medical Office"],
  "asking_price": 8499000.0,
  "currency": "USD",
  "building": { "square_footage": 5352, "lot_size_sqft": 6000, "buildings": 3, "zoning": "BHC3YY" },
  "marketing_description": "Prime owner-user/investor purchase opportunity. Beautiful red brick, colonial style medical office with 3 buildings and 4 units. Ground floor units are connected and can become one large medical space...",
  "investment_highlights": [
    "Beautiful red brick, colonial style medical office with 3 buildings and 4 units",
    "Near Cedars-Sinai and UCLA Medical Centers"
  ],
  "location": {
    "full_address": "9012 West Olympic Boulevard, Beverly Hills, Los Angeles County, CA 90211",
    "latitude": 34.0591994,
    "longitude": -118.3882362
  },
  "brokers": [
    {
      "name": "Bradley Luster",
      "link": "https://www.crexi.com/profile/bradleylu",
      "brokerage": { "name": "Major Properties", "website": "https://www.majorproperties.com" },
      "licenses": [{ "number": "CA 00913803", "type": "Real Estate Broker", "brokerage_phone": "213-276-2483" }],
      "is_platinum": true
    }
  ],
  "media": {
    "photo_count": 40,
    "photos": [{ "image": "https://crexi.com/images/format=auto,width=3000,height=2000/assets/2345196/e3ddd5fcd43d4de6833f70af82c49aba.JPG" }]
  },
  "listed_on": "2026-02-06T19:03:32.982Z"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Crexi Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/crexi-scraper
cd crexi-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/properties/details?property=2345196"
```

```json
{
  "id": 2345196,
  "link": "https://www.crexi.com/properties/2345196/california-prime-beverly-hills-medical-office-facility",
  "name": "Prime Beverly Hills Medical Office Facility",
  "status": "Active",
  "property_types": ["Office"],
  "subtypes": ["Medical Office"],
  "asking_price": 8499000.0,
  "currency": "USD",
  "building": { "square_footage": 5352, "lot_size_sqft": 6000, "buildings": 3, "zoning": "BHC3YY" },
  "location": {
    "full_address": "9012 West Olympic Boulevard, Beverly Hills, Los Angeles County, CA 90211",
    "latitude": 34.0591994,
    "longitude": -118.3882362
  },
  "brokers": [
    { "name": "Bradley Luster", "link": "https://www.crexi.com/profile/bradleylu", "listings_count": 158 }
  ],
  "media": { "photo_count": 40 }
}
```

All 10 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

10 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Property Details | `/properties/details` | Asking price, building facts, highlights, brokers and every photo |
| Search Properties for Sale · for Lease | `/properties/search` · `/leases/search` | 20 per page; filter by location, type, price, cap rate, size |
| Lease Details | `/leases/details` | Every available space with size and asking rent, plus building facts |
| Auction Details | `/auctions/details` | Auction dates, starting bid, bid increment, reserve status and bidder counts |
| Search Brokers | `/brokers/search` | Brokers by name with brokerage, city and profile link |
| Broker Details | `/brokers/details` | Bio, licenses, markets, roles and active and closed deal stats |
| Broker Listings | `/brokers/listings` | Every active property a broker lists for sale or lease |
| Autocomplete Locations | `/locations/suggest` | Address suggestions with matching listings and coordinates |
| Market Stats | `/markets/stats` | Live listing counts by property type or top city |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-crexi-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-crexi-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-crexi-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/properties/search",
    params={"state": "CA", "city": "Beverly Hills", "property_type": "Retail"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Crexi Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/crexi-scraper-github-whatsapp)

[![Ask Us by Email about Crexi Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Crexi%20Scraper%20API&body=I%20need%20help%20using%20the%20Crexi%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/crexi-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/crexi-scraper)
