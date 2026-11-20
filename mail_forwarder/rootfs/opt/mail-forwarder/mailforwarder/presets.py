"""Sending services that can carry the forwarded mail.

Only the technical settings live here. The explanations (summary, checklist, field labels) are
part of the web interface translations, keyed by the ``id`` of the preset.

Why a service at all? Your home IP address is on every big provider's "residential" list, so
Gmail or Outlook would reject or hide mail that leaves directly from your home. A sending service
("relay") delivers the mail from a trusted address instead. The free tiers are plenty for
private use.
"""

PRESETS = [
    {"id": "brevo", "name": "Brevo", "recommended": True, "needs_own_domain": True,
     "host": "smtp-relay.brevo.com", "port": 587, "security": "starttls", "website": "https://www.brevo.com/"},
    {"id": "smtp2go", "name": "SMTP2GO", "recommended": False, "needs_own_domain": True,
     "host": "mail.smtp2go.com", "port": 587, "security": "starttls", "website": "https://www.smtp2go.com/"},
    {"id": "mailjet", "name": "Mailjet", "recommended": False, "needs_own_domain": True,
     "host": "in-v3.mailjet.com", "port": 587, "security": "starttls", "website": "https://www.mailjet.com/"},
    {"id": "gmail", "name": "Gmail", "recommended": False, "needs_own_domain": False,
     "host": "smtp.gmail.com", "port": 587, "security": "starttls",
     "website": "https://myaccount.google.com/apppasswords"},
    {"id": "webde", "name": "WEB.DE", "recommended": False, "needs_own_domain": False,
     "host": "smtp.web.de", "port": 587, "security": "starttls", "website": "https://web.de/"},
    {"id": "custom", "name": "", "recommended": False, "needs_own_domain": False,
     "host": "", "port": 587, "security": "starttls", "website": ""},
]
