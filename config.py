"""Configuration for the Crexi Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                   port the API listens on (default 8000)
    CREXI_PROXY            proxy URL for every request, e.g.
                           http://user:pass@host:port (default: none —
                           direct). Crexi's JSON APIs answer home, office
                           and cloud server IPs alike, so you very likely
                           don't need this.
    CREXI_FALLBACK_PROXY   optional proxy a blocked direct connection moves
                           to for CREXI_BLOCK_COOLDOWN seconds (default:
                           none — retries stay on your own IP)

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# After a block on a direct connection, new sessions use the fallback proxy
# (when one is set) for this many seconds.
CREXI_BLOCK_COOLDOWN = 300

CREXI_PROXY = os.environ.get("CREXI_PROXY") or None


def crexi_proxy():
    """The proxy for one curl session (None = direct)."""
    return os.environ.get("CREXI_PROXY") or None


def crexi_fallback_proxy():
    """The proxy a blocked direct session moves to (None = no fallback)."""
    return os.environ.get("CREXI_FALLBACK_PROXY") or None


# ---- added by the sync: defaults for a direct run ----
CREXI_FALLBACK_EXIT = None
CREXI_LAST_EXIT = None
def crexi_last_proxy():
    return None


def gateway_exit(exit=None):
    return None

