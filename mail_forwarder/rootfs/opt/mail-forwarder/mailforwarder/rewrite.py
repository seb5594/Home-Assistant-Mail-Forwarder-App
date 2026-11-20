"""Prepares a received message for forwarding.

The body and every header that is not touched stay byte for byte as they arrived, so existing
signatures of the original sender keep their chance of surviving. Only these things change:

* trace headers are added (``X-Forwarded-By``, ``X-Original-To``),
* the ``Return-Path`` of the receiving hop is dropped,
* optionally the ``From`` header is rewritten (see ``rewrite_sender``).

Why rewrite ``From``? Big providers check that a message really comes from the domain in its
``From`` header. A forwarded message does not, because it leaves through *your* mail service.
Strict senders (banks, shops, Gmail itself) would see the forwarded copy rejected or sorted into
spam. With the rewrite the message comes from an address you control, the original sender moves
into the display name and into ``Reply-To``, so answering still reaches them.
"""
import re
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.utils import parseaddr
from typing import NamedTuple, Optional

CRLF = b"\r\n"
FORWARDED_BY = "Mail Forwarder (Home Assistant)"
_DISPLAY_NAME_LIMIT = 120


class HeaderBlock(NamedTuple):
    name: str  # lower case
    raw: bytes  # the header as written, folded continuation lines included, without final CRLF


def split_message(raw: bytes) -> tuple:
    """(header bytes without the blank line, body bytes)."""
    if raw.startswith(CRLF):
        return b"", raw[len(CRLF):]
    index = raw.find(CRLF + CRLF)
    if index < 0:
        return raw.rstrip(CRLF), b""
    return raw[:index], raw[index + 4:]


def parse_headers(header_bytes: bytes) -> list:
    blocks: list = []
    for line in header_bytes.split(CRLF):
        if line[:1] in (b" ", b"\t") and blocks:
            blocks[-1] = HeaderBlock(blocks[-1].name, blocks[-1].raw + CRLF + line)
        elif b":" in line:
            blocks.append(HeaderBlock(line.split(b":", 1)[0].strip().lower().decode("ascii", "replace"), line))
    return blocks


def count_headers(raw: bytes, name: str) -> int:
    return sum(1 for block in parse_headers(split_message(raw)[0]) if block.name == name.lower())


def header_value(raw: bytes, name: str) -> Optional[str]:
    """The decoded value of the first header with that name."""
    for block in parse_headers(split_message(raw)[0]):
        if block.name == name.lower():
            parsed = BytesHeaderParser(policy=policy.default).parsebytes(block.raw + CRLF + CRLF)
            return str(parsed[name])
    return None


def _encode_header(name: str, value) -> bytes:
    """Encodes one header the RFC way (non-ASCII names, folding, quoting)."""
    message = EmailMessage(policy=policy.SMTP)
    message[name] = value
    return message.as_bytes().split(CRLF + CRLF, 1)[0]


def _original_sender(raw_headers: bytes) -> tuple:
    """(display name, address) of the first From header; empty strings if there is none."""
    for block in parse_headers(raw_headers):
        if block.name == "from":
            parsed = BytesHeaderParser(policy=policy.default).parsebytes(block.raw + CRLF + CRLF)
            try:
                address = parsed["From"].addresses[0]
                return address.display_name, address.addr_spec
            except (IndexError, AttributeError, TypeError, ValueError):
                name, address = parseaddr(str(parsed["From"]))
                return name, address
    return "", ""


def sender_label(display_name: str, address: str) -> str:
    """The display name of the rewritten From: ``Anna Example (anna@example.org)``."""
    display_name = re.sub(r"[\r\n\t]+", " ", display_name or "").strip().strip('"')
    if not address:
        label = display_name or "Unknown sender"
    elif not display_name or display_name.lower() == address.lower():
        label = address
    elif address.lower() in display_name.lower():
        label = display_name
    else:
        label = f"{display_name} ({address})"
    return label[:_DISPLAY_NAME_LIMIT]


class ForwardPlan(NamedTuple):
    alias: str  # the address the mail was sent to
    from_address: str  # address used in a rewritten From header
    rewrite_sender: bool


def build_forward_message(raw: bytes, plan: ForwardPlan) -> bytes:
    """The message exactly as it should leave for the real mailbox."""
    header_bytes, body = split_message(raw)
    blocks = parse_headers(header_bytes)

    new_headers = [
        _encode_header("X-Forwarded-By", FORWARDED_BY),
        _encode_header("X-Original-To", plan.alias),
    ]
    kept = [block for block in blocks if block.name != "return-path"]

    if plan.rewrite_sender:
        display_name, address = _original_sender(header_bytes)
        has_reply_to = any(block.name == "reply-to" for block in kept)
        kept = [_replace_from(block, plan, display_name, address) for block in kept]
        if address and not has_reply_to:
            new_headers.append(_encode_header("Reply-To", Address(display_name=display_name, addr_spec=address)))

    all_headers = new_headers + [block.raw for block in kept]
    return CRLF.join(all_headers) + CRLF + CRLF + body


def _replace_from(block: HeaderBlock, plan: ForwardPlan, display_name: str, address: str) -> HeaderBlock:
    if block.name != "from":
        return block
    local, _, domain = plan.from_address.rpartition("@")
    rewritten = _encode_header("From", Address(display_name=sender_label(display_name, address),
                                               username=local, domain=domain))
    original = block.raw.split(b":", 1)[1].strip().replace(CRLF, b"")
    # Keep the untouched original for anyone who wants to see it.
    return HeaderBlock("from", rewritten + CRLF + b"X-Original-From: " + original)
