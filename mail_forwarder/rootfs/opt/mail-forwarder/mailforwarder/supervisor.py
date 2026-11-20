"""What the Home Assistant Supervisor can tell this app about itself (port mapping, host address)."""
import json
import os
import threading
import time
import urllib.request
from typing import Optional

from . import settings

_CACHE_SECONDS = 20
_cache: dict = {}
_lock = threading.Lock()


def _get(path: str) -> Optional[dict]:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    request = urllib.request.Request(f"{settings.SUPERVISOR_URL}{path}",
                                     headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return json.loads(response.read(1_000_000)).get("data")
    except (OSError, ValueError):
        return None


def _cached(path: str) -> Optional[dict]:
    with _lock:
        hit = _cache.get(path)
        if hit and time.time() - hit[0] < _CACHE_SECONDS:
            return hit[1]
    data = _get(path)
    with _lock:
        _cache[path] = (time.time(), data)
    return data


def published_port(container_port: int) -> tuple:
    """(known, host_port). ``host_port`` is None when the port is not published to the network."""
    info = _cached("/addons/self/info")
    if info is None:
        return False, None
    network = info.get("network") or {}
    return True, network.get(f"{container_port}/tcp")


def host_addresses() -> list:
    """IPv4 addresses of the Home Assistant host, when the Supervisor lets this app read them."""
    info = _cached("/network/info")
    found = []
    for interface in (info or {}).get("interfaces", []):
        if not interface.get("primary"):
            continue
        for address in (interface.get("ipv4") or {}).get("address", []):
            found.append(address.split("/")[0])
    return found
