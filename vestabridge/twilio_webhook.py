"""Service 2 — Twilio SMS webhook.

A small Flask app that receives inbound-SMS webhook POSTs from Twilio,
validates the request signature, and relays the message body to the Vestaboard.

Run (production, via gunicorn):
    gunicorn -b 0.0.0.0:5000 vestabridge.twilio_webhook:app
Run (development):
    python -m vestabridge.twilio_webhook
"""

from flask import Flask, Response, abort, request
from twilio.request_validator import RequestValidator
from werkzeug.middleware.proxy_fix import ProxyFix

from . import config
from .logging_setup import setup_logging
from .vestaboard import send_to_vestaboard

logger = setup_logging("twilio-webhook")

app = Flask(__name__)
# Honor X-Forwarded-Proto / Host from the Cloudflare Tunnel so request.url is
# reconstructed as the public https URL Twilio signed against.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

_validator = RequestValidator(config.TWILIO_AUTH_TOKEN)

_EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _signed_url() -> str:
    """The URL Twilio used when computing its signature.

    Prefer the explicitly configured public URL (most reliable behind a
    tunnel); otherwise trust the proxy-corrected request URL.
    """
    return config.TWILIO_WEBHOOK_URL or request.url


@app.route("/sms", methods=["POST"])
def sms() -> Response:
    signature = request.headers.get("X-Twilio-Signature", "")
    if not _validator.validate(_signed_url(), request.form, signature):
        logger.warning(
            "Rejected SMS webhook with invalid signature (from=%s)",
            request.form.get("From", "unknown"),
        )
        abort(403)

    body = (request.form.get("Body") or "").strip()
    sender = request.form.get("From", "unknown")
    logger.info("SMS from %s: %r", sender, body)

    if body:
        try:
            send_to_vestaboard(body, source=f"SMS:{sender}", logger=logger)
        except Exception:
            logger.exception("Failed to relay SMS to Vestaboard")
            # 500 tells Twilio the delivery failed (it may retry).
            return Response("error", status=500)

    # Empty TwiML = received OK, send no auto-reply.
    return Response(_EMPTY_TWIML, mimetype="application/xml")


@app.route("/health", methods=["GET"])
def health() -> Response:
    return Response("ok", mimetype="text/plain")


if __name__ == "__main__":
    logger.info("Starting Twilio webhook (dev server) on port %s", config.FLASK_PORT)
    app.run(host="0.0.0.0", port=config.FLASK_PORT)
