"""Parsing and validating e-mail addresses and host names."""
import re
from typing import Optional

_LOCAL_PART = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}$")
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_ANGLE_ADDRESS = re.compile(r"<([^<>]*)>")


def is_valid_hostname(name: str) -> bool:
    """A fully qualified host name with at least two labels, e.g. ``mail.example.com``."""
    name = name.strip().lower().rstrip(".")
    if not name or len(name) > 253 or "." not in name:
        return False
    return all(_LABEL.match(label) for label in name.split("."))


def is_valid_local_part(local: str) -> bool:
    local = local.strip().lower()
    return bool(_LOCAL_PART.match(local)) and not local.startswith(".") and not local.endswith(".") \
        and ".." not in local


def normalize_address(text: str) -> Optional[str]:
    """Returns ``local@domain`` in lower case, or None if the text is not a usable address."""
    text = (text or "").strip().lower()
    local, separator, domain = text.rpartition("@")
    if not separator or not is_valid_local_part(local) or not is_valid_hostname(domain):
        return None
    return f"{local}@{domain}"


def split_address(address: str) -> tuple:
    local, _, domain = address.rpartition("@")
    return local, domain


def domain_of(address: str) -> str:
    return split_address(address)[1]


def extract_path(text: str) -> str:
    """The address inside ``<...>`` of an SMTP command; an empty string is the null sender."""
    found = _ANGLE_ADDRESS.search(text)
    candidate = found.group(1) if found else text
    candidate = candidate.strip()
    if candidate.startswith("@") and ":" in candidate:  # obsolete source route <@a,@b:user@host>
        candidate = candidate.split(":", 1)[1]
    return candidate.strip().lower()
