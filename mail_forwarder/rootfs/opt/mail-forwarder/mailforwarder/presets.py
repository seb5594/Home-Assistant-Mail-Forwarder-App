"""Sending services that can carry the forwarded mail, with a beginner-friendly checklist each.

Your home IP address is on every big provider's "residential" list, so Gmail or Outlook would
reject or hide mail that leaves directly from your home. A sending service ("relay") delivers the
mail from a trusted address instead. The free tiers are plenty for private use.
"""

PRESETS = [
    {
        "id": "brevo", "name": "Brevo", "recommended": True, "needs_own_domain": True,
        "host": "smtp-relay.brevo.com", "port": 587, "security": "starttls",
        "website": "https://www.brevo.com/",
        "summary": "Free plan, made for sending. The clean choice when you own a domain.",
        "username_label": "SMTP login", "password_label": "SMTP key",
        "steps": [
            "Create a free account at brevo.com.",
            "Open 'SMTP & API' in the account menu and create an SMTP key. Copy the SMTP login and the key into "
            "the fields below. The key is not your account password.",
            "Open 'Senders, domains & dedicated IPs', then 'Domains', and add your own domain. Brevo shows a few "
            "DNS records: create them in your DNS (at Cloudflare: DNS, then Records) and press verify.",
            "Use an address of that domain as 'Sender address' below, for example forwarder@your-domain. "
            "It does not have to exist as a mailbox.",
        ],
    },
    {
        "id": "smtp2go", "name": "SMTP2GO", "recommended": False, "needs_own_domain": True,
        "host": "mail.smtp2go.com", "port": 587, "security": "starttls",
        "website": "https://www.smtp2go.com/",
        "summary": "Free plan with a small monthly allowance, enough for family mail. Needs your own domain.",
        "username_label": "SMTP username", "password_label": "SMTP password",
        "steps": [
            "Create a free account at smtp2go.com.",
            "Open 'Settings', then 'SMTP Users', and add an SMTP user. Copy username and password below.",
            "Open 'Settings', then 'Sender Domains', add your domain and create the DNS records it shows.",
            "Use an address of that domain as 'Sender address' below, for example forwarder@your-domain.",
        ],
    },
    {
        "id": "mailjet", "name": "Mailjet", "recommended": False, "needs_own_domain": True,
        "host": "in-v3.mailjet.com", "port": 587, "security": "starttls",
        "website": "https://www.mailjet.com/",
        "summary": "Free plan with a daily limit. Needs your own domain.",
        "username_label": "API key", "password_label": "Secret key",
        "steps": [
            "Create a free account at mailjet.com.",
            "Open the account settings, then 'SMTP and SEND API settings'. The API key is the login, "
            "the secret key is the password.",
            "Add your domain under 'Senders & domains' and create the DNS records it shows.",
            "Use an address of that domain as 'Sender address' below, for example forwarder@your-domain.",
        ],
    },
    {
        "id": "gmail", "name": "Gmail", "recommended": False, "needs_own_domain": False,
        "host": "smtp.gmail.com", "port": 587, "security": "starttls",
        "website": "https://myaccount.google.com/apppasswords",
        "summary": "Quickest start, no domain needed. Uses your own Gmail account, so every forwarded "
                   "message also shows up in its 'Sent' folder.",
        "username_label": "Gmail address", "password_label": "App password",
        "steps": [
            "Turn on 2-Step Verification for the Google account.",
            "Create an app password at myaccount.google.com/apppasswords and name it 'Mail Forwarder'.",
            "Use the full Gmail address as login and as 'Sender address'. Gmail replaces any other sender.",
        ],
    },
    {
        "id": "webde", "name": "WEB.DE", "recommended": False, "needs_own_domain": False,
        "host": "smtp.web.de", "port": 587, "security": "starttls",
        "website": "https://web.de/",
        "summary": "Quick start without a domain. Uses your own WEB.DE account.",
        "username_label": "WEB.DE address", "password_label": "Password or app password",
        "steps": [
            "Log in at web.de, open the settings and allow POP3/IMAP/SMTP access.",
            "If two-factor login is on, create an app password ('Anwendungspasswort') for this app.",
            "Use the full WEB.DE address as login and as 'Sender address'.",
        ],
    },
    {
        "id": "custom", "name": "Other service", "recommended": False, "needs_own_domain": False,
        "host": "", "port": 587, "security": "starttls",
        "website": "",
        "summary": "Any SMTP server that accepts a login, for example from your web hosting.",
        "username_label": "Login", "password_label": "Password",
        "steps": [
            "Ask your provider for the SMTP server name, port and login.",
            "Port 587 with STARTTLS is the usual choice, port 465 uses 'SSL/TLS'.",
            "Use a sender address that the provider allows for your login.",
        ],
    },
]
