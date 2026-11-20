<!-- header:begin (generated from project metadata) -->
<h1 align="center">
  <img src="https://raw.githubusercontent.com/seb5594/Home-Assistant-Mail-Forwarder-App/dev/mail_forwarder/logo.png" alt="Mail Forwarder" width="360" height="90">
  <br>
  Mail Forwarder
</h1>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fseb5594%2FHome-Assistant-Apps"><img src="https://img.shields.io/static/v1?label=Home%20Assistant&amp;message=Add%20app%20repository&amp;color=18BCF2&amp;logo=homeassistant&amp;logoColor=white&amp;style=for-the-badge" alt="Home Assistant" height="28"></a><br>
  <a href="https://github.com/seb5594/Home-Assistant-Mail-Forwarder-App/releases/tag/2026.11.20"><img src="https://img.shields.io/static/v1?label=app%20version&amp;message=2026.11.20&amp;color=1877A5&amp;style=for-the-badge" alt="app version" height="28"></a>
  <img src="https://img.shields.io/static/v1?label=image%20pulls&amp;message=4&amp;color=1877A5&amp;style=for-the-badge" alt="image pulls" height="28"><br>
  <img src="https://img.shields.io/static/v1?label=stage&amp;message=experimental&amp;color=2F855A&amp;style=flat" alt="stage" height="20">
  <img src="https://img.shields.io/static/v1?label=ingress&amp;message=enabled&amp;color=7C3AED&amp;style=flat" alt="ingress" height="20">
  <img src="https://img.shields.io/static/v1?label=arch%20%26%20size&amp;message=amd64%2041.2%20%C2%B7%20aarch64%2041.2%20MiB&amp;color=157F71&amp;style=flat" alt="arch &amp; size" height="20"><br>
  <a href="https://github.com/seb5594/Home-Assistant-Mail-Forwarder-App/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/seb5594/Home-Assistant-Mail-Forwarder-App/ci.yml?branch=dev&amp;label=checks&amp;style=flat" alt="checks" height="20"></a>
  <img src="https://img.shields.io/static/v1?label=runtime%20tests&amp;message=14%20passed&amp;color=2F855A&amp;style=flat" alt="runtime tests" height="20">
  <a href="https://github.com/seb5594/Home-Assistant-Apps/issues"><img src="https://img.shields.io/github/issues/seb5594/Home-Assistant-Mail-Forwarder-App?label=issues&amp;style=flat" alt="issues" height="20"></a><br>
  <a href="https://paypal.me/seb5594"><img src="https://img.shields.io/static/v1?label=Support&amp;message=PayPal&amp;color=0070BA&amp;logo=paypal&amp;logoColor=white&amp;style=for-the-badge" alt="PayPal" height="24"></a>
  <a href="https://buymeacoffee.com/seb5594"><img src="https://img.shields.io/static/v1?label=Support%20%F0%9F%8D%BA&amp;message=Buy%20me%20a%20c%CC%B6o%CC%B6f%CC%B6f%CC%B6e%CC%B6e%CC%B6%20Beer&amp;color=FFDD00&amp;style=for-the-badge" alt="Buy me a beer" height="24"></a><br>
  <a href="https://github.com/seb5594/Home-Assistant-Apps#license"><img src="https://img.shields.io/github/license/seb5594/Home-Assistant-Mail-Forwarder-App?label=license&amp;style=flat" alt="license" height="20"></a>
</p>
<!-- header:end -->

**🇬🇧 English** · [🇩🇪 Deutsch](README.de.md)

> **Experimental.** The app is new and has seen little real-world use yet.

Give your family and friends e-mail addresses on **your own domain** and forward everything to the
inbox they already use (Gmail, Outlook/Hotmail, WEB.DE, ...), without running a mail server that
stores mail.

* **Forward only.** Mail is received, passed on and forgotten. No mailboxes, no storage, tiny memory footprint (one small Python process, standard library only).
* **One inbox per person, many addresses.** `max@your-domain.com` and `max@family.duckdns.org` can both go to the same Gmail.
* **Free domains work.** DuckDNS names receive mail just like a domain you bought, and the app keeps them pointed at your IP.
* **Made for beginners.** A guided page inside Home Assistant explains DNS records, sending services and your router (including OPNsense and FRITZ!Box), checks everything and tells you which port or record is missing.
* **Proves itself.** A test mail goes out through your sending service, comes back in through the internet and is forwarded: if it arrives, everything is right.
* **No open relay, no backscatter.** Unknown addresses are refused during the SMTP conversation.

## How it works

```
sender ──► MX record ──► your public IP:25 ──► router ──► Home Assistant ──► Mail Forwarder
Mail Forwarder ──► sending service (port 587) ──► the real inbox
```

Why a sending service and not direct delivery? Gmail and Outlook distrust mail from home
connections. The app delivers through a trusted service and rewrites the `From` header to
`Original Name (original@address)` with a `Reply-To` to the original sender, so strict providers
keep the forwarded copy out of the spam folder. Details are in the [documentation](mail_forwarder/DOCS.md).

## Installation

1. Add this repository to Home Assistant: **Settings, Apps, App store, ⋮, Repositories**, or use the button above.
2. Install **Mail Forwarder** and start it.
3. Open the app page (**Open Web UI**) and follow the checklist.

You need a public IPv4 address that reaches your home (no CGNAT / DS-Lite), a router that can forward
port 25, and either your own domain or a free DuckDNS name. The setup is explained in the app.

## Documentation

* [Documentation](mail_forwarder/DOCS.md): concepts, setup, security, troubleshooting
* [Changelog](mail_forwarder/CHANGELOG.md)

## Development

The application is plain Python (standard library only) under `mail_forwarder/rootfs/opt/mail-forwarder`,
with a framework-free web interface next to it. The tests start the whole app against a fake sending service:

```bash
python .github/tests/run_tests.py
```

<!-- support:begin (generated, shared text) -->
## Say thanks

All my projects are built in my spare time, just for the fun of it. Still, they take a lot of time and care, and many of the smart home gadgets I buy end up here because I want to make them cloud-free and smart-home ready. Every bit of support means a lot to me.

If my work helped you or turned out to be useful, show your appreciation with a hot drink for my next sleepless night.

[![PayPal](https://img.shields.io/static/v1?label=Support&message=PayPal&color=0070BA&logo=paypal&logoColor=white&style=for-the-badge)](https://paypal.me/seb5594) [![Buy me a beer](https://img.shields.io/static/v1?label=Support%20%F0%9F%8D%BA&message=Buy%20me%20a%20c%CC%B6o%CC%B6f%CC%B6f%CC%B6e%CC%B6e%CC%B6%20Beer&color=FFDD00&style=for-the-badge)](https://buymeacoffee.com/seb5594)
<!-- support:end -->

<!-- license:begin (generated from the license file) -->
## License

[![license](https://img.shields.io/static/v1?label=license&message=MIT&color=5B6770&style=flat)](LICENSE)

Published under the [MIT License](LICENSE).
<!-- license:end -->
