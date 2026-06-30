# VestaBridge

A home message-display bridge for a Raspberry Pi Zero 2 W. It relays incoming
messages to a [Vestaboard](https://www.vestaboard.com/) split-flap display from
two independent sources:

- **Meshtastic (off-grid):** text messages received over the LoRa mesh via a
  USB-connected Heltec node. Works with **no internet**.
- **Twilio (online):** inbound SMS delivered to a Twilio number via a webhook,
  exposed to the internet through a Cloudflare Tunnel.

Both paths share one Vestaboard sender module, so rendering and logging are
identical regardless of source. Built for off-grid-resilient home messaging.

```
 LoRa mesh ── SenseCAP P1-Pro (roof) ─┐
                                       │ LoRa 915 MHz
                       Heltec V3 ◄─────┘
                          │ USB serial (/dev/ttyUSB0)
                          ▼
   Internet ─ Cloudflare Tunnel ─► Flask :5000 ─┐
                                                 ▼
                                   Raspberry Pi Zero 2 W
                                                 │  Vestaboard Local API
                                                 ▼  (HTTP, port 7000, LAN)
                                            Vestaboard
```

## Hardware

| Part | Model & where to buy | Notes |
|------|----------------------|-------|
| Computer | [**Raspberry Pi Zero 2 W**](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) + [official 5 V/2.5 A micro-USB supply](https://www.raspberrypi.com/products/micro-usb-power-supply/) | Runs the app 24/7. Under-powering causes random reboots / SD-card corruption — use a quality supply. |
| Storage | **microSD, 16 GB+** (32 GB here) — any reputable brand | Raspberry Pi OS Lite (64-bit), headless. |
| LoRa radio | [**Heltec WiFi LoRa 32 V3**, US 915 MHz](https://heltec.org/project/wifi-lora-32-v3/) — buy: [Rokland (US)](https://store.rokland.com/products/heltec-wifi-lora-32v3) · [Amazon](https://www.amazon.com/Heltec-Development-863-870MHz-ESP32-S3FN8-902-928MHz/dp/B0D1H1FN9Y) | ESP32-S3 + SX1262, runs stock Meshtastic. Ships with a 915 MHz antenna — **attach it before powering on** or you risk the radio. |
| Pi ↔ Heltec cable | **micro-USB-OTG → USB-C** *data* cable (or a micro-USB-OTG adapter + USB-A→USB-C data cable) | Pi port is micro-USB, Heltec is USB-C. Must be a *data* cable, and "OTG" so the Pi acts as host. The Pi powers the Heltec over it — **no battery needed**. |
| Mesh relay (outdoor) | [**SenseCAP Solar Node P1-Pro**](https://www.seeedstudio.com/SenseCAP-Solar-Node-P1-Pro-for-Meshtastic-LoRa-p-6412.html) (~$90) — also on [Amazon](https://www.amazon.com/SenseCAP-Solar-Node-P1-Pro-Communication/dp/B0FMDHBWX8) | Solar Meshtastic node on the roof; relays incoming LoRa to the indoor Heltec. Any Meshtastic node on your channel works. |
| Display | [**Vestaboard**](https://www.vestaboard.com/) (Flagship, 6×22 split-flap), on Wi-Fi | Driven over the **Local API** (LAN-only, no cloud) — enable it once (§5). Keep it on the **same LAN/subnet** as the Pi. |

**Also needed:** a [**Twilio**](https://www.twilio.com/) account + SMS-capable number (online path), a domain on [**Cloudflare**](https://www.cloudflare.com/) (for the tunnel), and a desktop with **Chrome/Edge** to flash the Heltec.

**Connectivity gotchas**
- The **Pi Zero 2 W is 2.4 GHz Wi-Fi only** — join it to a 2.4 GHz SSID on the *same network* as the Vestaboard.
- The **Meshtastic path needs no internet**; only the Twilio/SMS path does.

## Architecture

| Component | Role |
|-----------|------|
| `vestabridge/meshtastic_listener.py` | Service 1 — serial connection to Heltec, pubsub on `meshtastic.receive.text`, auto-reconnect. |
| `vestabridge/twilio_webhook.py` | Service 2 — Flask app, validates Twilio signature, accepts `POST /sms`. |
| `vestabridge/vestaboard.py` | Shared sender — word-wrap to 6×22, character encoding, Local API POST, logging. |
| `vestabridge/config.py` | Loads all config from `.env`. |
| `vestabridge/logging_setup.py` | Rotating file logs + stdout (journald). |

Neither service uses the cloud, a database, or a web UI. The Meshtastic path
has no internet dependency at all.

> **Before the Pi setup:** the Heltec must be flashed with Meshtastic firmware
> and joined to the same channel/PSK as your other mesh nodes, otherwise it
> receives nothing to relay. Flash it from a desktop browser (not the Pi) — see
> the flashing + mesh-join steps in [`SETUP-CHECKLIST.md`](SETUP-CHECKLIST.md).

---

## 1. Installation (on the Pi)

```bash
# System packages
sudo apt update
sudo apt install -y python3 python3-venv git

# Clone into /opt (the path the systemd units expect)
sudo git clone https://github.com/aarron/vestabridge.git /opt/vestabridge
sudo chown -R pi:pi /opt/vestabridge
cd /opt/vestabridge

# Virtualenv + deps
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Add the `pi` user to the `dialout` group so it can read the USB serial port
(needed by the Meshtastic service):

```bash
sudo usermod -aG dialout pi
# log out/in (or reboot) for the group change to take effect
```

---

## 2. Configure `.env`

```bash
cp .env.example .env
nano .env
```

| Variable | Notes |
|----------|-------|
| `HELTEC_SERIAL_PORT` | Serial device for the Heltec. `ls -l /dev/serial/by-id` shows a stable name — prefer that over `/dev/ttyUSB0` (see udev tip below). |
| `VESTABOARD_LOCAL_IP` | The Vestaboard's LAN IP. Set a DHCP reservation so it doesn't move. |
| `VESTABOARD_API_TOKEN` | The Local API **key** from the enablement step (section 5). |
| `VESTABOARD_PORT` | Local API port, default `7000`. |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | From the Twilio console. The auth token is used to validate webhook signatures. |
| `FLASK_PORT` | Local webhook port, default `5000`. Keep in sync with the gunicorn bind in the systemd unit. |
| `TWILIO_WEBHOOK_URL` | The **public** tunnel URL Twilio posts to, e.g. `https://sms.example.com/sms`. Must match the Twilio console exactly. |
| `LOG_DIR` | Default `/var/log/vestabridge`. Create it (below) or it falls back to `./logs`. |

Create the log directory:

```bash
sudo mkdir -p /var/log/vestabridge
sudo chown pi:pi /var/log/vestabridge
```

### Stable serial name (recommended)

USB `/dev/ttyUSB*` numbering can change across reboots. Pin it with a udev rule
(adjust the vendor/product from `lsusb`, or just use the `by-id` path):

```bash
ls -l /dev/serial/by-id
# e.g. /dev/serial/by-id/usb-Silicon_Labs_CP210x... -> ../../ttyUSB0
```

Then set `HELTEC_SERIAL_PORT=/dev/serial/by-id/usb-Silicon_Labs_CP210x...` in
`.env`.

---

## 3. Test before installing services

```bash
# Render + push a test message to the board (verifies Vestaboard config)
.venv/bin/python -m vestabridge.vestaboard "Hello from VestaBridge"

# Run the Meshtastic listener in the foreground (Ctrl-C to stop)
.venv/bin/python -m vestabridge.meshtastic_listener

# Run the webhook dev server in the foreground
.venv/bin/python -m vestabridge.twilio_webhook
```

The Vestaboard test prints an ASCII preview of the 6×22 grid before sending.

---

## 4. Install & enable the systemd units

```bash
sudo cp systemd/vestabridge-meshtastic.service /etc/systemd/system/
sudo cp systemd/vestabridge-twilio.service /etc/systemd/system/
sudo systemctl daemon-reload

sudo systemctl enable --now vestabridge-meshtastic.service
sudo systemctl enable --now vestabridge-twilio.service
```

Check status and logs:

```bash
systemctl status vestabridge-meshtastic.service
journalctl -u vestabridge-meshtastic.service -f
tail -f /var/log/vestabridge/meshtastic-listener.log
```

Both units `Restart=always`, so they recover from crashes and start on boot.
The units assume the install path `/opt/vestabridge`, user `pi`, and the venv at
`/opt/vestabridge/.venv`. Edit the unit files if yours differ.

> The Twilio unit runs gunicorn bound to `127.0.0.1:5000` — it is reachable only
> via the Cloudflare Tunnel, not directly from the LAN/internet. If you change
> `FLASK_PORT`, update the `--bind` in `vestabridge-twilio.service` to match.

---

## 5. Get the Vestaboard Local API key

The Local API runs on the Vestaboard itself over your LAN — no cloud or
subscription needed — but it must be enabled once, and the key isn't the one
most people find first.

> **⚠️ Cloud API vs Local API — don't mix them up.** The Vestaboard app's
> *Settings → API* screen issues a **Cloud Read/Write token** (`rw.vestaboard.com`,
> needs internet). That's a *different* API — the Local endpoint rejects it with
> `Local API is not enabled` (and returns HTTP 401/201, which is easy to misread
> as success). This project needs the **Local API** key (LAN-only); the off-grid
> path depends on it.

1. **Request enablement:** go to <https://www.vestaboard.com/local-api> and
   submit the enablement request for your board. The board's **owner is emailed
   an enablement token** after a short review (not instant — it can take a while).
2. **Enable the API** by POSTing that enablement token to the board (use the
   board's LAN IP if `vestaboard.local` doesn't resolve):

   ```bash
   curl -X POST \
     -H "X-Vestaboard-Local-Api-Enablement-Token: YOUR_ENABLEMENT_TOKEN" \
     http://vestaboard.local:7000/local-api/enablement
   ```

   A success looks like:

   ```json
   {"message":"Local API enabled","apiKey":"…"}
   ```

3. Put that **`apiKey`** (the value returned above — *not* the enablement token)
   in `.env` as `VESTABOARD_API_TOKEN`, and the board's LAN IP in
   `VESTABOARD_LOCAL_IP` (set a DHCP reservation so it doesn't move).

Messages are sent as a 6×22 array of Vestaboard character codes to
`http://<ip>:7000/local-api/message` with header `X-Vestaboard-Local-Api-Key`; a
successful post returns **HTTP 201** (empty body). VestaBridge handles all of the
character encoding for you.

---

## 6. Set up the Cloudflare Tunnel (Twilio path only)

The tunnel exposes the local Flask webhook to the internet without opening any
router ports. The Meshtastic path does **not** need this.

```bash
# Install cloudflared (Pi is 64-bit arm)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 \
  -o cloudflared
sudo install cloudflared /usr/local/bin/cloudflared

# Authenticate (opens a browser link to pick your Cloudflare zone)
cloudflared tunnel login

# Create a named tunnel and a DNS route
cloudflared tunnel create vestabridge
cloudflared tunnel route dns vestabridge sms.example.com
```

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: vestabridge
credentials-file: /home/pi/.cloudflared/<TUNNEL_UUID>.json

ingress:
  - hostname: sms.example.com
    service: http://127.0.0.1:5000
  - service: http_status:404
```

Run the tunnel as a service so it starts on boot:

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Set `TWILIO_WEBHOOK_URL=https://sms.example.com/sms` in `.env`.

> **Watch for zone-level redirects.** If the Cloudflare zone has a catch-all
> Redirect Rule / Page Rule (e.g. `example.com` → another site), it runs at
> the edge *before* the tunnel and will 301 your webhook away. Exclude the
> subdomain — for a Single Redirect set to "All incoming requests," switch it to
> a custom filter expression: `not (http.host eq "sms.example.com")`.

### Point Twilio at the webhook

In the Twilio console → your phone number → **Messaging** → "A message comes
in": set the webhook to `https://sms.example.com/sms`, method **HTTP POST**.

Signature validation requires the URL Twilio signs to match `TWILIO_WEBHOOK_URL`
**exactly** (scheme, host, path, no trailing slash mismatch). Text the number;
it should appear on the board within seconds. Invalid/unsigned requests get a
`403`.

---

## Message rendering

- The board is **6 rows × 22 columns**, uppercase only.
- Text is word-wrapped to 22 columns; words longer than a row are hard-split.
- Messages over 6 rows are truncated, with the last row ending in `..`.
- Unsupported characters render as blanks. Supported: A–Z, 0–9, space, and
  `! @ # $ ( ) - + & = ; : ' " % , . / ? °`.

## What this project deliberately omits

No cloud MQTT, no database / message history, no web UI, no Docker — per the
project scope.

## Troubleshooting

- **Nothing on the board:** run the section-3 Vestaboard test. 401/403 → wrong
  `VESTABOARD_API_TOKEN`; connection refused → wrong IP/port or Local API not
  enabled.
- **Serial errors / no Meshtastic messages:** confirm the port
  (`ls /dev/serial/by-id`), that `pi` is in `dialout`, and that the roof node is
  routing to the Heltec. The service auto-reconnects every 10 s.
- **Twilio 403s:** `TWILIO_WEBHOOK_URL` must match the Twilio console URL and
  `TWILIO_AUTH_TOKEN` must be correct. Check
  `journalctl -u vestabridge-twilio.service`.
