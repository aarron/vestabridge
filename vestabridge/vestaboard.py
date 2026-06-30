"""Shared Vestaboard sender.

Converts plain text into the Vestaboard 6x22 character-code grid and posts it
to the Vestaboard Local API. Used by both the Meshtastic listener and the
Twilio webhook so message rendering and logging are identical for both sources.
"""

import logging

import requests

from . import config

ROWS = 6
COLS = 22

# Vestaboard character codes. The board has no lowercase; everything is
# upper-cased before lookup. Characters with no code map to a blank (0).
# Source: https://docs.vestaboard.com/docs/characterCodes
CHAR_MAP = {
    " ": 0,
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8, "I": 9,
    "J": 10, "K": 11, "L": 12, "M": 13, "N": 14, "O": 15, "P": 16, "Q": 17,
    "R": 18, "S": 19, "T": 20, "U": 21, "V": 22, "W": 23, "X": 24, "Y": 25,
    "Z": 26,
    "1": 27, "2": 28, "3": 29, "4": 30, "5": 31, "6": 32, "7": 33, "8": 34,
    "9": 35, "0": 36,
    "!": 37, "@": 38, "#": 39, "$": 40, "(": 41, ")": 42, "-": 44, "+": 46,
    "&": 47, "=": 48, ";": 49, ":": 50, "'": 52, '"': 53, "%": 54, ",": 55,
    ".": 56, "/": 59, "?": 60, "°": 62,
}

# Module-level fallback logger (replaced by the caller's logger when provided).
_log = logging.getLogger("vestaboard")


def char_to_code(ch: str) -> int:
    """Map a single character to its Vestaboard code (blank if unsupported)."""
    return CHAR_MAP.get(ch.upper(), 0)


def wrap_text(text: str, width: int = COLS, max_rows: int = ROWS) -> list[str]:
    """Word-wrap text to `width` columns, hard-splitting over-long words.

    Returns at most `max_rows` lines (extra lines are dropped — see
    `text_to_grid` for the truncation indicator).
    """
    lines: list[str] = []
    current = ""

    for word in text.split():
        # A single word longer than the row gets hard-split across rows.
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            word = word[width:]

        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)
    return lines


def text_to_grid(text: str) -> list[list[int]]:
    """Render text to a 6x22 grid of Vestaboard character codes, centered.

    Lines are word-wrapped to 22 columns, then the block is centered both
    vertically (within the 6 rows) and horizontally (each line within its row).
    If the message overflows 6 rows, the last visible row ends with an ellipsis
    ("..") so it is clear the message was truncated.
    """
    lines = wrap_text(text)

    truncated = len(lines) > ROWS
    lines = lines[:ROWS]
    if truncated and lines:
        last = lines[-1][: COLS - 2].rstrip()
        lines[-1] = f"{last}.."

    grid = [[0] * COLS for _ in range(ROWS)]
    top_pad = (ROWS - len(lines)) // 2  # vertical centering of the block
    for i, line in enumerate(lines):
        codes = [char_to_code(c) for c in line[:COLS]]
        left_pad = (COLS - len(codes)) // 2  # horizontal centering of the line
        grid[top_pad + i][left_pad : left_pad + len(codes)] = codes
    return grid


def send_to_vestaboard(text: str, source: str, logger: logging.Logger | None = None):
    """Render `text` and POST it to the Vestaboard Local API.

    `source` is a human-readable origin label (e.g. "Meshtastic:RoofNode" or
    "SMS:+1555...") used only for logging. Raises on HTTP/connection failure so
    callers can decide how to respond; the message send is always logged with a
    timestamp (via the logger's formatter) and source.
    """
    log = logger or _log

    if not config.VESTABOARD_LOCAL_IP or not config.VESTABOARD_API_TOKEN:
        raise RuntimeError(
            "VESTABOARD_LOCAL_IP and VESTABOARD_API_TOKEN must be set in .env"
        )

    grid = text_to_grid(text)
    url = (
        f"http://{config.VESTABOARD_LOCAL_IP}:{config.VESTABOARD_PORT}"
        "/local-api/message"
    )
    headers = {
        "X-Vestaboard-Local-Api-Key": config.VESTABOARD_API_TOKEN,
        "Content-Type": "application/json",
    }

    response = requests.post(
        url, json=grid, headers=headers, timeout=config.VESTABOARD_TIMEOUT
    )
    # A successful message POST returns 2xx — the board replies 201 with an empty
    # body. raise_for_status() handles genuine HTTP errors (401/403/429/5xx). But
    # when the Local API is disabled the board still returns a 2xx, with body
    # "Local API is not enabled", so also treat an error-bearing 2xx body as a
    # failure rather than silently dropping the message.
    response.raise_for_status()
    body = response.text.strip()
    if "not enabled" in body.lower():
        raise RuntimeError(f"Vestaboard rejected the message: {body[:200]}")
    log.info("Sent to Vestaboard [source=%s]: %r", source, text)
    return response


if __name__ == "__main__":
    # Quick manual test:  python -m vestabridge.vestaboard "hello world"
    import sys

    _CODE_TO_CHAR = {code: ch for ch, code in CHAR_MAP.items()}
    message = " ".join(sys.argv[1:]) or "VESTABRIDGE TEST"

    print("Grid preview (| marks the 22-column edge):")
    for row in text_to_grid(message):
        print("".join(_CODE_TO_CHAR.get(code, "?") for code in row) + "|")

    send_to_vestaboard(message, source="CLI-test")
    print("Sent.")
