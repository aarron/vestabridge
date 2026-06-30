"""Service 1 — Meshtastic listener.

Connects to the Heltec node over USB serial, subscribes to incoming text
messages on the mesh, and relays them to the Vestaboard. Reconnects
automatically if the serial link drops.

Run with:  python -m vestabridge.meshtastic_listener
"""

import threading
import time

import meshtastic
import meshtastic.serial_interface
from pubsub import pub

from . import config
from .logging_setup import setup_logging
from .vestaboard import send_to_vestaboard

logger = setup_logging("meshtastic-listener")

# Set whenever the meshtastic library reports the serial connection was lost,
# so the main loop can tear down and reconnect.
_connection_lost = threading.Event()

# Reconnect backoff (seconds) after a failed/dropped connection.
RECONNECT_DELAY = 10


def _node_label(interface, packet: dict) -> str:
    """Build a readable sender label, preferring the node's short name."""
    node_id = packet.get("fromId")
    if not node_id:
        node_num = packet.get("from")
        node_id = f"!{node_num:08x}" if isinstance(node_num, int) else "unknown"

    try:
        node = interface.nodes.get(node_id) if interface.nodes else None
        short = (node or {}).get("user", {}).get("shortName")
        if short:
            return f"{short} ({node_id})"
    except Exception:  # nodes db not ready / unexpected shape — fall back to id
        logger.debug("Could not resolve short name for %s", node_id, exc_info=True)
    return node_id


def _channel_name(interface, index: int) -> str:
    """Resolve a received packet's channel index to its name.

    The primary channel (index 0) has an empty name in the config; we report it
    as "(primary)" so it never accidentally matches a named allowlist entry.
    """
    try:
        for ch in interface.localNode.channels:
            if ch.index == index:
                return ch.settings.name or "(primary)"
    except Exception:
        logger.debug("Could not resolve channel %s", index, exc_info=True)
    return f"(channel {index})"


def _is_direct(interface, packet: dict) -> bool:
    """True if the packet is addressed directly to this node (not broadcast)."""
    to = packet.get("to")
    try:
        my_num = interface.myInfo.my_node_num
    except Exception:
        return False
    return to is not None and to == my_num


def _should_relay(channel_name: str, is_direct: bool) -> bool:
    """Apply the MESH_CHANNELS / MESH_RELAY_DIRECT policy from config."""
    if config.MESH_RELAY_DIRECT and is_direct:
        return True
    if not config.MESH_CHANNELS:  # empty allowlist == relay everything
        return True
    return channel_name in config.MESH_CHANNELS


def on_receive(packet: dict, interface) -> None:
    """pubsub callback for meshtastic.receive.text."""
    try:
        text = (packet.get("decoded") or {}).get("text")
        if not text:
            return

        channel_name = _channel_name(interface, packet.get("channel", 0))
        direct = _is_direct(interface, packet)
        label = _node_label(interface, packet)

        if not _should_relay(channel_name, direct):
            logger.info(
                "Ignoring text from %s on %s (direct=%s) — not in relay policy",
                label, channel_name, direct,
            )
            return

        origin = "DM" if direct else channel_name
        logger.info("Meshtastic text from %s [%s]: %r", label, origin, text)
        send_to_vestaboard(text, source=f"Meshtastic:{label}:{origin}", logger=logger)
    except Exception:
        logger.exception("Failed to handle / relay Meshtastic message")


def on_connection(interface, topic=pub.AUTO_TOPIC) -> None:
    """pubsub callback for meshtastic.connection.established."""
    logger.info("Meshtastic connection established")


def on_connection_lost(interface, topic=pub.AUTO_TOPIC) -> None:
    """pubsub callback for meshtastic.connection.lost."""
    logger.warning("Meshtastic connection lost")
    _connection_lost.set()


def run() -> None:
    pub.subscribe(on_receive, "meshtastic.receive.text")
    pub.subscribe(on_connection, "meshtastic.connection.established")
    pub.subscribe(on_connection_lost, "meshtastic.connection.lost")

    logger.info("Starting Meshtastic listener on %s", config.HELTEC_SERIAL_PORT)

    while True:
        _connection_lost.clear()
        interface = None
        try:
            interface = meshtastic.serial_interface.SerialInterface(
                devPath=config.HELTEC_SERIAL_PORT
            )
            # The library reads in background threads; block here until the
            # connection drops, then fall through to reconnect.
            while not _connection_lost.wait(timeout=1):
                pass
            logger.warning("Reconnecting to %s", config.HELTEC_SERIAL_PORT)
        except Exception:
            logger.exception(
                "Serial connection error; retrying in %ss", RECONNECT_DELAY
            )
            time.sleep(RECONNECT_DELAY)
        finally:
            if interface is not None:
                try:
                    interface.close()
                except Exception:
                    logger.debug("Error closing interface", exc_info=True)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logger.info("Shutting down Meshtastic listener")
