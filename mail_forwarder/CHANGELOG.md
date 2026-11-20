# Changelog

## 2026.11.20.2

* 🌍 New box on the Router & network page for people who block countries (GeoIP): mail from Gmail, Outlook and sending services comes from abroad, so port 25 needs an exception. Includes the OPNsense steps for a pass rule above the country block.
* The test mail tips, the health check for incoming connections, the Help page and the documentation mention country blocks as a reason why mail does not arrive.

## 2026.11.20.1

* 🌍 The app page is now available in English and German. The language follows the browser and can be switched in the footer.
* 🛡️ Corrected the OPNsense guide for the current version: **Firewall ‣ NAT ‣ Destination NAT** with alias, "Redirect Target IP/Port", "Log" and the "Firewall rule: Pass" option. The options "NAT reflection" and "Filter rule association" that were named before do not exist there.
* 🔔 The Domains page now starts with a hint for OPNsense and router users: do not enter a DuckDNS or Cloudflare token when the router already updates DNS.
* 🧹 Saved DuckDNS and Cloudflare tokens can be forgotten with one button.
* 💡 New Help page with a short setup guide, a glossary, questions and answers and troubleshooting.
* 🧭 More detailed guides, friendlier wording and emojis throughout the app page.
* Footer: author name links to the GitHub profile, credit on two lines, 🍺 added to the support button.
* Messages from the app (health checks, errors, activity) are now translated as well.

## 2026.11.20

* ✨ First experimental version.
* Receives mail for your own domains and for free DuckDNS domains, and forwards it to one real inbox per person.
* Guided setup in the app page: DNS records, sending service, router (OPNsense, FRITZ!Box), health checks and a test mail button.
* Keeps DuckDNS names and the Cloudflare A record of your mail server up to date.
