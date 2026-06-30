# VestaBridge — Setup Checklist

Arrival-day runbook with this deployment's real values filled in. See
`README.md` for the full explanations behind each step.

| Value | |
|-------|--|
| Inbound SMS number | **+1 555 555 0123** (SMS+MMS+voice) |
| Twilio number SID | `PNxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| Public webhook | `https://sms.example.com/sms` (POST) |
| Vestaboard | LAN IP + Local API key already in `.env` |
| Heltec node | `!xxxxxxxx` — flashed Meshtastic 2.7.15, configured ✅ |
| LoRa (your regional mesh) | region **US**, preset **MEDIUM_FAST**, slot **45** (913.125 MHz), hop **3** |
| Channels | `0` PRIMARY (your regional mesh public) · `1` SECONDARY **MyChannel** (private, key not stored here) |

---

## Phase A — Now, before hardware arrives

- [x] Twilio account verified (active, paid)
- [x] SMS number purchased + webhook pre-configured to `sms.example.com/sms`
- [x] `sms.example.com` confirmed **not** already in Cloudflare DNS
- [x] `.env` populated: Vestaboard IP + token, Twilio SID/token, webhook URL
- [x] Meshtastic CLI installed on the Mac (`pipx install meshtastic`, v2.7.9)
- [x] your regional mesh settings obtained (your mesh config page) + MyChannel private key

---

## Phase B — When the Heltec arrives: flash + join the mesh (do on the Mac)

Flash from your **Mac with Chrome/Edge**, not the Pi (the web flasher needs a
desktop browser; the Pi Zero is headless).

**✅ DONE** — flashed and configured on the Mac. For reference / reflashing:

- [x] 915 MHz antenna attached to the single LoRa U.FL connector (top edge)
- [x] Data USB-C cable (first cable was charge-only — swap if no `/dev/cu.usbserial-*` appears)
- [x] Flashed via <https://flasher.meshtastic.org> → **Heltec V3** → Stable, **Full Erase and Install**
      (gotcha: close any other Chrome tab holding the serial port — Web Serial is single-owner)

### Node config applied (Mac, over USB serial)

Region/preset/slot per your mesh config page. Commands used:

- [x] `meshtastic --set lora.region US --set lora.modem_preset MEDIUM_FAST --set lora.channel_num 45 --set lora.hop_limit 3`
- [x] `meshtastic --ch-add MyChannel` then `meshtastic --ch-set psk base64:<MyChannel key> --ch-index 1`
- [x] Verified: `meshtastic --nodes` shows neighbors at 2–4 hops; MyChannel present as Index 1 SECONDARY

> Optional: set role to `CLIENT_MUTE` (`meshtastic --set device.role CLIENT_MUTE`) since this
> node only receives for the Vestaboard and needn't rebroadcast. Left as `CLIENT` for now.

---

## Phase C — Pi install  ✅ DONE (as-built)

- [x] Imaged Raspberry Pi OS (Debian 13 Trixie) Lite 64-bit; hostname `vestabridge`,
      user `pi`, WiFi, SSH = public-key only with a dedicated `id_vestabridge` ed25519 key
- [x] Enabled passwordless sudo (`/etc/sudoers.d/010-pi-nopasswd`) so the install
      could be driven over SSH
- [x] `sudo apt update` + base packages: git, python3-venv, pip, rsync, **unattended-upgrades**
- [x] App deployed via **rsync from the Mac** (repo is private → no `git clone`/creds
      on the Pi); `.env` carried in the same hop, then `chmod 600`
- [x] venv + `pip install -r requirements.txt` (all arm64 wheels, no source builds)
- [x] `pi` already in `dialout` by default; `/var/log/vestabridge` created
- [x] Heltec on Pi → `HELTEC_SERIAL_PORT` pinned to the stable
      `/dev/serial/by-id/usb-Silicon_Labs_CP2102_...` path

## Phase D — Tunnel + services + verify  ✅ DONE

- [x] cloudflared installed via the official arm64 `.deb`
- [x] `cloudflared tunnel login` (example.com zone) → `create vestabridge` →
      `route dns vestabridge sms.example.com`
- [x] config + creds in `/etc/cloudflared/`, ingress → `http://127.0.0.1:5000`,
      run as a manual `cloudflared.service` systemd unit
- [x] **⚠️ Cloudflare redirect gotcha:** the zone had a Single Redirect (All
      incoming requests → example.org) that 301'd the subdomain before
      the tunnel. Fixed by switching that rule to a **custom filter expression**:
      `not (http.host eq "sms.example.com")` — carves out only this host.
- [x] Both app services enabled + active; survive reboot

### Vestaboard Local API — the last blocker (now resolved)

- [x] **Gotcha 1 — Cloud vs Local API.** The board was first given a Cloud
      Read/Write token (from the app's API screen). That's a *different* API
      (`rw.vestaboard.com`, needs internet) — the Local endpoint rejected it with
      "Local API is not enabled." The Local API is LAN-only and required for the
      off-grid goal.
- [x] **Enablement.** Requested an enablement token at vestaboard.com/local-api
      (owner gets emailed). POSTed it to `http://<board>:7000/local-api/enablement`
      → board returned the real `apiKey`, now in `.env` as `VESTABOARD_API_TOKEN`.
- [x] **Gotcha 2 — 201 is success.** A successful Local API message POST returns
      **HTTP 201** (empty body), not 200. The sender accepts 2xx and only fails on
      an error body ("not enabled"); a "require 200" check false-failed every send.

### Smoke tests — all passing

- [x] Vestaboard: `python -m vestabridge.vestaboard "..."` → board physically updates
- [x] Webhook: `curl https://sms.example.com/health` → `200 ok`
- [x] **SMS path:** text **(555) 555-0123** → appears on board (signature validated)
- [x] **Mesh path:** MyChannel message from another node → received, filtered, displayed

### Live system facts

- Pi on WiFi at **192.168.1.72** (Mac alias `ssh vestabridge`). **TODO:** set DHCP
  reservations for the Pi (.72) and Vestaboard (.66) so neither IP drifts.
- Update the app later with: `rsync -az --exclude=.git --exclude=.venv --exclude=.env <mac>/vestabridge/ vestabridge:/opt/vestabridge/`
  then `sudo systemctl restart vestabridge-*`.

---

Sources for the flashing steps:
- Meshtastic Web Flasher — <https://flasher.meshtastic.org/>
- Flashing Firmware (ESP32) — <https://meshtastic.org/docs/getting-started/flashing-firmware/>
