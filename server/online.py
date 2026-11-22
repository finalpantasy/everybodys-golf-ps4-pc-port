"""Hosting for friends: the room key, invite codes, LAN discovery and the status file.

host.py --online uses this. The launcher reads <state>/online.txt (key=value lines) to show
the invite code, and finds hosts on the home network with the LAN discovery broadcast.
"""
from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network
import os
from pathlib import Path
import socket
import threading
import time

import invite
from portmap import PortOpener, default_gateway, local_address

# UDP port of the LAN discovery broadcast (the launcher's "Find games on my network").
DISCOVERY_PORT = 48765
FIND = b"EGOLF-FIND 1"
HOST_REPLY = b"EGOLF-HOST 1 "
SHARED = IPv4Network("100.64.0.0/10")  # Tailscale and other VPNs (carrier-grade NAT range)


def load_room_key(state: Path) -> str:
    """The room key kept in <state>/room-key.txt, so a host's code stays the same between runs."""
    path = state / "room-key.txt"
    try:
        key = invite.parse_key(path.read_text(encoding="ascii"))
        if key:
            return invite.key_text(key)
    except (OSError, UnicodeDecodeError):
        pass
    text = invite.key_text(invite.new_key())
    path.write_text(text + "\n", encoding="ascii")
    return text


def local_addresses() -> list[str]:
    """This PC's IPv4 addresses that other machines might reach (home network first)."""
    found: list[str] = []
    gateway = default_gateway()
    first = local_address(gateway) if gateway else None
    if first:
        found.append(first)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            ip = IPv4Address(address)
            if not ip.is_loopback and not ip.is_link_local and address not in found:
                found.append(address)
    except OSError:
        pass
    return found


def address_kind(address: str, home: str | None) -> str:
    if address == home:
        return "lan"
    if IPv4Address(address) in SHARED:
        return "vpn"
    return "lan" if IPv4Address(address).is_private else "vpn"


class OnlineHost:
    """Writes online.txt, answers LAN discovery and (optionally) opens the router port."""

    def __init__(self, state: Path, port: int, key: str, name: str, *, open_port: bool = True,
                 web_lookup: bool = True, discovery: bool = True, discovery_port: int = DISCOVERY_PORT):
        self.state, self.port, self.key, self.name = state, port, key, name
        self.key_value = invite.parse_key(key)
        self.lock = threading.Lock()
        self.opener = PortOpener(port, web_lookup=web_lookup) if open_port else None
        self.discovery = discovery
        self.discovery_port = discovery_port
        self.sock: socket.socket | None = None
        self.write_status()

    def code(self, address: str) -> str:
        return invite.encode(address, self.port, self.key_value)

    def status_lines(self) -> list[str]:
        lines = [f"port={self.port}", f"key={self.key}"]
        addresses = local_addresses()
        home = addresses[0] if addresses else None
        for address in addresses:
            lines.append(f"{address_kind(address, home)}={address} {self.code(address)}")
        opener = self.opener
        if opener is None:
            lines += ["portmap=off", "note=Opening the router port is turned off."]
        elif not opener.done.is_set():
            lines += ["portmap=pending", "note=Asking the router to open the port..."]
        else:
            if opener.public_ip:
                lines.append(f"internet={opener.public_ip} {self.code(opener.public_ip)}")
            lines.append(f"portmap={opener.mapping.method or 'none'}")
            lines.append(f"note={opener.mapping.note}")
        return lines

    def write_status(self):
        lines = self.status_lines()
        with self.lock:
            path = self.state / "online.txt"
            temporary = path.with_suffix(".tmp")
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.replace(temporary, path)
        for line in lines:
            if line.startswith(("lan=", "vpn=", "internet=", "note=")):
                print(f"online {line}", flush=True)

    def start(self):
        if self.discovery:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("0.0.0.0", self.discovery_port))
                self.sock = sock
                threading.Thread(target=self.answer, name="lan-discovery", daemon=True).start()
            except OSError as error:
                print(f"online note=LAN discovery is off ({error.strerror or error})", flush=True)
        if self.opener:
            self.opener.start(lambda _opener: self.write_status())

    def answer(self):
        sock = self.sock
        while sock is not None:
            try:
                data, sender = sock.recvfrom(64)
            except OSError:
                return
            if data.strip() != FIND:
                continue
            address = local_address(sender[0])
            if not address:
                continue
            reply = HOST_REPLY + f"{self.code(address)} {self.name}".encode("ascii", "replace")[:80]
            try:
                sock.sendto(reply, sender)
            except OSError:
                pass

    def close(self):
        if self.sock is not None:
            sock, self.sock = self.sock, None
            sock.close()
        if self.opener is not None:
            self.opener.close()


def find_hosts(wait: float = 1.5, port: int = DISCOVERY_PORT) -> list[tuple[str, str]]:
    """(code, name) of each host on the home network that answers a broadcast (for tests and tools)."""
    found: dict[str, str] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.2)
        for target in ("255.255.255.255", "127.0.0.1"):
            try:
                sock.sendto(FIND, (target, port))
            except OSError:
                pass
        end = time.monotonic() + wait
        while time.monotonic() < end:
            try:
                data, _ = sock.recvfrom(128)
            except socket.timeout:
                continue
            except OSError:
                break
            if data.startswith(HOST_REPLY):
                code, _, name = data[len(HOST_REPLY):].decode("ascii", "replace").partition(" ")
                if invite.decode(code):
                    found[code] = name
    return sorted(found.items())

