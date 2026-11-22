"""Opens the host's TCP port on the home router and finds the public address (standard library only).

Tries UPnP IGD (SSDP discovery, then the WANIPConnection or WANPPPConnection SOAP calls),
then NAT-PMP (RFC 6886), then PCP (RFC 6887). When none answers, or the router's own outside
address is not a public one (a second router or the provider's shared address, CGNAT), the
public address comes from one HTTPS "what is my IP" request that sends nothing but the
request line.
"""
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address
import os
import re
import secrets
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from xml.etree import ElementTree

SSDP = ("239.255.255.250", 1900)
NATPMP_PORT = 5351
DESCRIPTION = "Everybody's Golf server"
LEASE_SECONDS = 7200
PUBLIC_IP_URLS = ("https://api.ipify.org", "https://checkip.amazonaws.com")
WAN_SERVICES = (
    "urn:schemas-upnp-org:service:WANIPConnection:2",
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
)


@dataclass
class Mapping:
    method: str            # "upnp", "nat-pmp", "pcp" or "" (none)
    external_ip: str = ""  # the router's outside address, when it said
    note: str = ""         # one plain sentence for the player
    control: str = ""      # UPnP control URL (for removal)
    service: str = ""      # UPnP service type
    nonce: bytes = b""     # PCP mapping nonce
    lifetime: int = 0


def is_public(address: str) -> bool:
    try:
        return IPv4Address(address).is_global
    except ValueError:
        return False


# ---- gateway and local address --------------------------------------------------------------------

def default_gateway() -> str | None:
    """The IPv4 default gateway (lowest metric), or None."""
    try:
        if os.name == "nt":
            out = subprocess.run(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            best = None
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
                    try:
                        IPv4Address(parts[2])
                        metric = int(parts[-1])
                    except ValueError:
                        continue
                    if best is None or metric < best[0]:
                        best = (metric, parts[2])
            return best[1] if best else None
        with open("/proc/net/route", encoding="ascii") as routes:
            for line in routes.readlines()[1:]:
                parts = line.split()
                if parts[1] == "00000000" and int(parts[3], 16) & 2:
                    return str(IPv4Address(struct.unpack("<I", bytes.fromhex(parts[2]))[0]))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def local_address(toward: str) -> str | None:
    """This PC's address on the route to `toward` (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((toward, 9))
            return s.getsockname()[0]
    except OSError:
        return None


# ---- UPnP IGD ---------------------------------------------------------------------------------------

def ssdp_locations(local_ip: str | None, wait: float = 2.5) -> list[str]:
    """Description URLs of the Internet gateway devices that answer an SSDP search."""
    found: list[str] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(0.25)
        try:
            if local_ip:
                s.bind((local_ip, 0))
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            for target in ("urn:schemas-upnp-org:device:InternetGatewayDevice:1",
                           "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
                           "urn:schemas-upnp-org:service:WANIPConnection:1"):
                query = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
                         f"MX: 2\r\nST: {target}\r\n\r\n").encode("ascii")
                s.sendto(query, SSDP)
        except OSError:
            return found
        end = time.monotonic() + wait
        while time.monotonic() < end:
            try:
                data, _ = s.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            match = re.search(rb"(?im)^location:\s*(\S+)", data)
            if match:
                url = match[1].decode("ascii", "replace")
                if url.startswith("http://") and url not in found:
                    found.append(url)
    return found


def upnp_service(location: str, timeout: float = 3) -> tuple[str, str] | None:
    """(control URL, service type) of the WAN connection service in a device description."""
    with urllib.request.urlopen(location, timeout=timeout) as reply:
        root = ElementTree.fromstring(reply.read(256 * 1024))
    base = next((e.text for e in root.iter() if e.tag.endswith("URLBase") and e.text), location)
    services = {}
    for service in root.iter():
        if not service.tag.endswith("}service") and service.tag != "service":
            continue
        fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in service}
        if fields.get("serviceType") in WAN_SERVICES and fields.get("controlURL"):
            services[fields["serviceType"]] = urllib.parse.urljoin(base, fields["controlURL"])
    for kind in WAN_SERVICES:
        if kind in services:
            return services[kind], kind
    return None


def soap(control: str, service: str, action: str, arguments: dict[str, str], timeout: float = 4) -> dict[str, str]:
    """One SOAP call; the reply's fields, or an OSError carrying the UPnP error code."""
    body = "".join(f"<{k}>{v}</{k}>" for k, v in arguments.items())
    envelope = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>').encode("utf-8")
    request = urllib.request.Request(control, data=envelope, method="POST", headers={
        "Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{service}#{action}"'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            text = reply.read(64 * 1024)
    except urllib.error.HTTPError as error:
        with error:
            detail = error.read(64 * 1024)
        code = re.search(rb"<errorCode>(\d+)</errorCode>", detail)
        raise OSError(f"UPnP error {code[1].decode() if code else error.code}") from None
    root = ElementTree.fromstring(text)
    return {e.tag.rsplit("}", 1)[-1]: (e.text or "") for e in root.iter() if len(e) == 0}


def upnp_map(port: int, local_ip: str, locations: list[str]) -> Mapping | None:
    for location in locations:
        try:
            found = upnp_service(location)
        except (OSError, ElementTree.ParseError, ValueError):
            continue
        if not found:
            continue
        control, service = found
        args = {"NewRemoteHost": "", "NewExternalPort": str(port), "NewProtocol": "TCP",
                "NewInternalPort": str(port), "NewInternalClient": local_ip, "NewEnabled": "1",
                "NewPortMappingDescription": DESCRIPTION, "NewLeaseDuration": str(LEASE_SECONDS)}
        lifetime = LEASE_SECONDS
        try:
            soap(control, service, "AddPortMapping", args)
        except (OSError, ElementTree.ParseError):
            # Some routers take permanent leases only (error 725).
            args["NewLeaseDuration"] = "0"
            lifetime = 0
            try:
                soap(control, service, "AddPortMapping", args)
            except (OSError, ElementTree.ParseError):
                continue
        external = ""
        try:
            external = soap(control, service, "GetExternalIPAddress", {}).get("NewExternalIPAddress", "")
        except (OSError, ElementTree.ParseError):
            pass
        return Mapping("upnp", external, control=control, service=service, lifetime=lifetime)
    return None


def upnp_unmap(mapping: Mapping, port: int):
    try:
        soap(mapping.control, mapping.service, "DeletePortMapping",
             {"NewRemoteHost": "", "NewExternalPort": str(port), "NewProtocol": "TCP"})
    except (OSError, ElementTree.ParseError):
        pass


# ---- NAT-PMP and PCP ------------------------------------------------------------------------------

def udp_ask(gateway: str, request: bytes, check, tries: int = 3, port: int | None = None):
    """Send `request` with RFC 6886 retry timing; the first reply that `check` accepts, or None."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        wait = 0.25
        for _ in range(tries):
            try:
                s.sendto(request, (gateway, port or NATPMP_PORT))
            except OSError:
                return None
            end = time.monotonic() + wait
            while time.monotonic() < end:
                s.settimeout(max(0.01, end - time.monotonic()))
                try:
                    data, sender = s.recvfrom(1100)
                except socket.timeout:
                    break
                except OSError:
                    return None
                if sender[0] == gateway:
                    value = check(data)
                    if value is not None:
                        return value
            wait *= 2
    return None


def natpmp_map(gateway: str, port: int, lifetime: int = LEASE_SECONDS) -> Mapping | None:
    def address_reply(data):
        if len(data) >= 12 and data[:2] == b"\x00\x80" and struct.unpack_from(">H", data, 2)[0] == 0:
            return socket.inet_ntoa(data[8:12])
        return None

    def map_reply(data):
        if len(data) >= 16 and data[:2] == b"\x00\x82":
            result, _, internal, external, granted = struct.unpack_from(">HIHHI", data, 2)
            if internal == port:
                return result, external, granted
        return None

    answer = udp_ask(gateway, struct.pack(">BBHHHI", 0, 2, 0, port, port, lifetime), map_reply)
    if answer is None or answer[0] != 0:
        return None
    result, external_port, granted = answer
    if external_port != port and lifetime:
        natpmp_map(gateway, port, 0)  # Friends would need the other port; give it back.
        return None
    external = udp_ask(gateway, b"\x00\x00", address_reply) or ""
    return Mapping("nat-pmp", external, lifetime=granted)


def pcp_request(local_ip: str, port: int, lifetime: int, nonce: bytes) -> bytes:
    client = b"\0" * 10 + b"\xff\xff" + socket.inet_aton(local_ip)
    header = struct.pack(">BBHI", 2, 1, 0, lifetime) + client
    body = nonce + struct.pack(">B3xHH", 6, port, port) + b"\0" * 10 + b"\xff\xff" + b"\0" * 4
    return header + body


def pcp_map(gateway: str, local_ip: str, port: int, lifetime: int = LEASE_SECONDS,
            nonce: bytes | None = None) -> Mapping | None:
    nonce = nonce or secrets.token_bytes(12)

    def reply(data):
        if len(data) >= 60 and data[0] == 2 and data[1] == 0x81 and data[24:36] == nonce:
            granted = struct.unpack_from(">I", data, 4)[0]
            external_port = struct.unpack_from(">H", data, 42)[0]
            return data[3], granted, external_port, socket.inet_ntoa(data[56:60])
        return None

    answer = udp_ask(gateway, pcp_request(local_ip, port, lifetime, nonce), reply)
    if answer is None or answer[0] != 0:
        return None
    _, granted, external_port, external = answer
    if external_port != port and lifetime:
        pcp_map(gateway, local_ip, port, 0, nonce)
        return None
    return Mapping("pcp", external, nonce=nonce, lifetime=granted)


# ---- public address -------------------------------------------------------------------------------

def public_ip_from_web(timeout: float = 4) -> str:
    for url in PUBLIC_IP_URLS:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "golf-server"})
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                text = reply.read(64).decode("ascii", "replace").strip()
            if is_public(text):
                return text
        except (OSError, ValueError):
            continue
    return ""


# ---- the whole job --------------------------------------------------------------------------------

class PortOpener:
    """Opens `port` in the background, keeps the lease renewed and removes it on close()."""

    def __init__(self, port: int, *, web_lookup: bool = True, gateway: str | None = None):
        self.port = port
        self.web_lookup = web_lookup
        self.gateway = gateway
        self.mapping = Mapping("")
        self.public_ip = ""
        self.done = threading.Event()
        self.stopping = threading.Event()
        self.local_ip: str | None = None
        self.thread = threading.Thread(target=self.run, name="portmap", daemon=True)

    def start(self, on_done=None):
        self.on_done = on_done
        self.thread.start()

    def open_once(self) -> Mapping:
        gateway = self.gateway or default_gateway()
        self.local_ip = local_address(gateway) if gateway else local_address("192.0.2.1")
        if not gateway or not self.local_ip:
            return Mapping("", note="This PC has no route to a router, so no port was opened.")
        mapping = upnp_map(self.port, self.local_ip, ssdp_locations(self.local_ip))
        mapping = mapping or natpmp_map(gateway, self.port) or pcp_map(gateway, self.local_ip, self.port)
        if mapping is None:
            return Mapping("", note=f"The router did not open the port: forward TCP port {self.port} "
                                    f"to {self.local_ip} in its settings, or use a VPN such as Tailscale.")
        mapping.note = f"The router forwards TCP port {self.port} to this PC ({mapping.method.upper()})."
        if mapping.external_ip and not is_public(mapping.external_ip):
            mapping.note = (f"The router opened the port, but its outside address ({mapping.external_ip}) is not "
                            "public: there is another router or a provider-shared address in the way. "
                            "Use a VPN such as Tailscale, or open the port on the outer router too.")
        return mapping

    def run(self):
        self.mapping = self.open_once()
        if is_public(self.mapping.external_ip):
            self.public_ip = self.mapping.external_ip
        elif self.web_lookup:
            self.public_ip = public_ip_from_web()
        self.done.set()
        if self.on_done:
            self.on_done(self)
        # Renew halfway through the lease.
        while self.mapping.method and self.mapping.lifetime and not self.stopping.wait(self.mapping.lifetime / 2):
            renewed = self.open_once()
            if renewed.method:
                self.mapping = renewed

    def close(self):
        self.stopping.set()
        mapping = self.mapping
        if mapping.method == "upnp":
            upnp_unmap(mapping, self.port)
        elif mapping.method == "nat-pmp" and self.gateway_for_close():
            natpmp_map(self.gateway_for_close(), self.port, 0)
        elif mapping.method == "pcp" and self.gateway_for_close() and self.local_ip:
            pcp_map(self.gateway_for_close(), self.local_ip, self.port, 0, mapping.nonce)

    def gateway_for_close(self) -> str | None:
        return self.gateway or default_gateway()
