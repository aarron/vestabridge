"""Configuration loaded from the environment / .env file.

All sensitive values and tunables live in `.env` (see `.env.example`).
"""

import os

from dotenv import load_dotenv

# Load .env from the project root if present. Existing environment variables
# (e.g. those set by systemd) take precedence over the file.
load_dotenv(override=False)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# --- Meshtastic / Heltec ----------------------------------------------------
HELTEC_SERIAL_PORT = os.getenv("HELTEC_SERIAL_PORT", "/dev/ttyUSB0")

# Which received mesh messages get shown on the board.
# MESH_CHANNELS: comma-separated channel names to relay (e.g. "MyChannel").
#   Empty or "*" means relay every channel (including the public primary).
# MESH_RELAY_DIRECT: also relay direct (1-to-1) messages addressed to this node,
#   regardless of channel.
_mesh_channels_raw = os.getenv("MESH_CHANNELS", "").strip()
MESH_CHANNELS = (
    []
    if _mesh_channels_raw in ("", "*")
    else [c.strip() for c in _mesh_channels_raw.split(",") if c.strip()]
)
MESH_RELAY_DIRECT = os.getenv("MESH_RELAY_DIRECT", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# --- Vestaboard Local API ---------------------------------------------------
VESTABOARD_LOCAL_IP = os.getenv("VESTABOARD_LOCAL_IP", "")
VESTABOARD_API_TOKEN = os.getenv("VESTABOARD_API_TOKEN", "")
VESTABOARD_PORT = _int("VESTABOARD_PORT", 7000)
VESTABOARD_TIMEOUT = _int("VESTABOARD_TIMEOUT", 10)

# --- Twilio -----------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
FLASK_PORT = _int("FLASK_PORT", 5000)

# The public URL Twilio uses to reach the /sms webhook (your Cloudflare Tunnel
# hostname, e.g. https://sms.example.com/sms). Twilio computes its request
# signature against this exact URL, so signature validation only works if it
# matches what is configured in the Twilio console. Leave blank to fall back to
# the URL Flask reconstructs from request headers (works when the proxy
# forwards Host + X-Forwarded-Proto correctly).
TWILIO_WEBHOOK_URL = os.getenv("TWILIO_WEBHOOK_URL", "")

# --- Logging ----------------------------------------------------------------
LOG_DIR = os.getenv("LOG_DIR", "/var/log/vestabridge")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
