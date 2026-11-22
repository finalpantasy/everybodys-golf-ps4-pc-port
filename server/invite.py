"""Invite codes: a host's IPv4 address, TCP port and room key in 16 copy-pasteable characters.

The code packs 80 bits as 16 Crockford base32 symbols, shown in groups of four
("7K3M-Q0ZD-1XAB-9T5C"): IPv4 address (32 bits), port (16), room key (27) and a check
symbol (5) that catches a mistyped or swapped symbol. Decoding ignores case, spaces and
dashes, and reads I and L as 1 and O as 0. The runtime's launcher decodes the same format
(src/invite_code.h); keep the two in step.
"""
from __future__ import annotations

from ipaddress import IPv4Address
import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
KEY_BITS = 27
SYMBOLS = 16


def new_key() -> int:
    """A random nonzero room key."""
    return secrets.randbelow((1 << KEY_BITS) - 1) + 1


def key_text(key: int) -> str:
    """The key as the runtime's --server-key and X-Golf-Key header carry it: 7 lowercase hex digits."""
    return f"{key:07x}"


def parse_key(text: str) -> int | None:
    text = text.strip().lower()
    if not 1 <= len(text) <= 7 or any(c not in "0123456789abcdef" for c in text):
        return None
    key = int(text, 16)
    return key if 0 < key < (1 << KEY_BITS) else None


def _check(symbols: list[int]) -> int:
    # Odd weights are invertible mod 32, so any one wrong symbol changes the sum; adjacent
    # swaps change it unless the two symbols differ by 16.
    return sum((2 * i + 1) * s for i, s in enumerate(symbols)) % 32


def encode(address: str, port: int, key: int) -> str:
    if not 0 < port < 65536 or not 0 < key < (1 << KEY_BITS):
        raise ValueError("port or key out of range")
    value = int(IPv4Address(address)) << 43 | port << 27 | key
    symbols = [(value >> (5 * (14 - i))) & 31 for i in range(15)]
    symbols.append(_check(symbols))
    text = "".join(ALPHABET[s] for s in symbols)
    return "-".join(text[i:i + 4] for i in range(0, SYMBOLS, 4))


def decode(code: str) -> tuple[str, int, int] | None:
    """(address, port, key) for a valid code, else None."""
    text = "".join(code.split()).replace("-", "").upper().translate(str.maketrans("ILO", "110"))
    if len(text) != SYMBOLS or any(c not in ALPHABET for c in text):
        return None
    symbols = [ALPHABET.index(c) for c in text]
    if _check(symbols[:15]) != symbols[15]:
        return None
    value = 0
    for s in symbols[:15]:
        value = value << 5 | s
    address, port, key = value >> 43, (value >> 27) & 0xFFFF, value & ((1 << KEY_BITS) - 1)
    if not port or not key:
        return None
    return str(IPv4Address(address)), port, key
