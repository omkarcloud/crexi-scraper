"""Cache TTL per /crexi/* endpoint (cache.py, keyed on the validated
params). Crexi is a live marketplace: listings activate, reprice and go
under contract daily, so the result caches are short; the record caches
are keyed on the asset / profile alone so a link and a bare id share one
row, and properties/details, leases/details and auctions/details slice
ONE cached record fetch (api._sale_record / api._lease_record).
"""
from datetime import timedelta

# One row per (market, asset id): the listing record + brokers + gallery
# (+ spaces for lease). Prices and status move daily; an hour keeps a
# browsing client on one fetch.
PROPERTY_CACHE = timedelta(hours=1)
# Search pages reorder as listings activate ("rank" is recomputed often).
SEARCH_CACHE = timedelta(minutes=30)
# The auction record carries a live countdown and bidder counts.
AUCTION_CACHE = timedelta(minutes=10)
# Broker profiles change when a listing is added; the name index rarely.
BROKER_CACHE = timedelta(hours=6)
BROKER_SEARCH_CACHE = timedelta(hours=12)
# Marketplace counts per type / city: a daily snapshot is enough.
STATS_CACHE = timedelta(hours=24)
# Address suggestions follow the listing index.
SUGGEST_CACHE = timedelta(hours=6)
