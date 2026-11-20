# Mail Forwarder

> **Experimental.** The app is new. It works in tests, but has seen little real-world use yet.

Mail Forwarder gives you e-mail addresses on your **own domain** (or a free DuckDNS name) and passes
everything that arrives there on to a **real inbox** such as Gmail, Outlook/Hotmail or WEB.DE.
There are no mailboxes to run and no storage to manage: a message is received, forwarded and
forgotten. That is why it needs so little memory.

Typical use: `info@your-domain.com` goes to you, `max@your-domain.com` goes to your uncle's Gmail,
`anna@your-domain.com` goes to a Hotmail account.

Everything is set up in the app page (**Open Web UI**). It explains each step, checks your
settings and shows what is missing. This page explains the ideas behind it.

## Contents

* [How mail travels](#how-mail-travels)
* [What you need](#what-you-need)
* [Quick start](#quick-start)
* [Free domains such as DuckDNS](#free-domains-such-as-duckdns)
* [Why a sending service](#why-a-sending-service)
* [Router and OPNsense](#router-and-opnsense)
* [Options](#options)
* [Security and privacy](#security-and-privacy)
* [Troubleshooting](#troubleshooting)
* [Limits](#limits)

## How mail travels

```
sender ──► DNS: "where does your-domain.com receive mail?" (MX record)
       ──► your public IP, port 25 ──► router (port forward) ──► Home Assistant ──► this app
this app ──► sending service (port 587) ──► inbox of the person (Gmail, Outlook, WEB.DE ...)
```

Three things have to be right, and the app page checks each of them:

1. **DNS** tells the world that this app receives the mail of your domain.
2. **The router** lets connections to port 25 through to Home Assistant.
3. **A sending service** hands the forwarded mail to the inbox in a way that big providers trust.

## What you need

| Need | Why |
| --- | --- |
| A domain (for example at Cloudflare) **or** a free DuckDNS name | The part after the `@` |
| A public IPv4 address that is really yours | Mail has to reach you from outside. Connections behind CGNAT or DS-Lite cannot receive mail, the **Router & network** page shows how to tell |
| A router that can forward port 25 | OPNsense, FRITZ!Box and others are explained in the app |
| A free account at a sending service, or your own Gmail or WEB.DE account | Delivers the forwarded mail |

## Quick start

1. **Start the app** and open the app page.
2. **Domains:** add your domain. The page shows the exact DNS records to create, with copy buttons. For a Cloudflare domain these are an `A` record (`mail`, **DNS only**, grey cloud) and an `MX` record pointing to it.
3. **Mailboxes:** add a person: a name, the real inbox, and one or more addresses.
4. **Sending:** pick a sending service and follow its short checklist.
5. **Router & network:** forward port 25 to Home Assistant.
6. **Overview:** press **Send test mail**. When all three steps turn green, you are done.

The first message of a new sender often lands in the spam folder. Mark it as "not spam" once.

## Free domains such as DuckDNS

Yes, they work for **receiving**. A DuckDNS name only has an address (`A`) record and no MX record,
but mail servers fall back to the address of the name when no MX record exists. So
`name@family.duckdns.org` arrives just as well. The app can keep the DuckDNS name pointed at your
current IP address (enter the DuckDNS token on the **Domains** page).

One person can have addresses on several domains at once, for example `max@your-domain.com` and
`max@family.duckdns.org`, all going to the same inbox.

Limits of free names: you cannot add DKIM or other DNS records to a DuckDNS name, so authenticated
sending services (Brevo, SMTP2GO, Mailjet) are not an option for that domain. Choose Gmail or WEB.DE
as the sending service in that case, or use a sender address on a domain of your own.

## Why a sending service

Gmail, Outlook and WEB.DE distrust mail that comes straight from a home internet connection: it has
no reverse DNS name, the address range is on "residential" lists, and many providers block outgoing
port 25 anyway. A sending service delivers from a trusted address and works on port 587.

By default the app also rewrites the `From` header of forwarded mail to **"Original Name (original@address)"**
on your sender address and sets `Reply-To` to the original sender. A forwarded message cannot honestly
claim to come from the original sender, and strict providers would sort it away. Replying still
reaches the original sender. You can switch this off on the **Sending** page.

**Direct delivery** (without a service) exists for experts. It needs open outgoing port 25 and
usually fails at Outlook/Hotmail and Gmail.

## Router and OPNsense

The **Router & network** page contains click-by-click instructions for OPNsense (alias, destination NAT rule,
log view for debugging), for the FRITZ!Box and for other routers. The short version:

* Forward **TCP 25** of your WAN address to the IP of Home Assistant, port 25.
* Do not use Cloudflare's orange cloud (proxy) for the mail server name: proxies do not forward mail.
* Remove other MX records of the domain, for example those of Cloudflare Email Routing.
* If OPNsense (plugin `os-ddclient`) or your router already updates your DNS record, leave the token fields of this app empty. Two updaters for the same record work against each other.
* **Country blocks (GeoIP):** Gmail, Outlook and many sending services send from data centers abroad, mostly in the USA. A rule that only allows Germany stops their mail. Keep the block for everything else and add a pass rule for port 25 above it. The **Router & network** page shows the steps for OPNsense.

If port 25 is already used on your Home Assistant, change the host port in the app's **Network**
tab (for example 2525) and forward to that port instead. The app page shows the right number.

> **Do you even need this app?** If your domain is on Cloudflare and you only need a few addresses,
> Cloudflare's free *Email Routing* forwards mail without any home server, port or router setting.
> This app is for you when you want DuckDNS names, several domains, full control, or no dependency
> on that service.

## Options

| Option | Description |
| --- | --- |
| `log_level` | `info` for everyday use, `debug` for troubleshooting |

Everything else is configured in the app page and stored in the app's data folder, so it is part of
your Home Assistant backups. The app page speaks English and German; it follows the language of your
browser and can be switched in the footer.

## Security and privacy

* The app only accepts mail for the addresses you added. Everything else is refused during the
  SMTP conversation, so it never sends bounce messages to forged senders, and it is not an open relay.
* Connections are encrypted when the other server supports it (a self-signed certificate is created).
* Messages are stored on disk only until they are delivered. Failed ones are kept for 14 days so you
  can retry them, then deleted.
* Secrets (sending service password, DuckDNS and Cloudflare tokens) are stored in the app data and are never sent
  back to the browser.
* The web interface is reachable through Home Assistant ingress only.
* Port 25 is exposed to the internet when you forward it. Scanners will find it. Keep the app updated.
* The app makes these outgoing requests: DNS lookups through `cloudflare-dns.com` and `dns.google`,
  your public IP through `api.ipify.org` (with fallbacks), and the services you switch on (sending
  service, DuckDNS, Cloudflare). Nothing is sent anywhere else.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Test mail never arrives (step 2 stays grey) | DNS checks on the Overview, port forward in the router, the live firewall log, and whether your provider blocks incoming port 25 or shares your IP (CGNAT) |
| "Needs your attention" in Activity | A setting is wrong, usually the login or sender address of the sending service. The message stays queued and goes out after you fix it |
| Mail arrives in spam | Normal for the first message of a sender. Authenticate your domain at the sending service, and use an address of that domain as sender |
| Mail is refused as "No such user" | The address is not added under **Mailboxes**, or the person is switched off |
| Test mail does not arrive and you block countries | The country block stops mail from abroad. Make port 25 an exception, see *Router and OPNsense* |
| Works for some senders only | Another MX record on the domain still points elsewhere |

Switch `log_level` to `debug` and read the app log for more detail.

## Limits

* IPv4 only. Remove `AAAA` records of the mail server name, or forward IPv6 port 25 as well.
* Messages up to 25 MB.
* One inbox per person. Several people cannot share one address.
* No spam or virus filtering of incoming mail. The receiving inbox does that.
* Bounces of undeliverable forwarded mail are not sent back to the original sender. They appear in
  **Activity**.

## Deutsch

Kurzfassung der Dokumentation. Die App-Seite selbst (**Web-UI öffnen**) ist zweisprachig und folgt der Sprache deines Browsers.

**Was die App macht:** Sie gibt dir Adressen auf deiner eigenen Domain (oder einem kostenlosen DuckDNS-Namen) und leitet alles an ein echtes Postfach weiter, zum Beispiel Gmail, Outlook/Hotmail oder WEB.DE. Es gibt keine Postfächer und keinen Speicherbedarf.

**Der Weg einer Mail:** Absender, dann MX-Eintrag deiner Domain, dann deine öffentliche IP auf Port 25, dann Router (Portweiterleitung), dann Home Assistant, dann diese App, dann Versanddienst (Port 587), dann das echte Postfach.

**Einrichtung in fünf Schritten:**

1. **Domains:** Domain hinzufügen und die angezeigten DNS-Einträge anlegen (A-Eintrag `mail`, bei Cloudflare *nur DNS*, und MX-Eintrag).
2. **Postfächer:** Personen mit dem echten Postfach und einer oder mehreren Adressen anlegen.
3. **Versand:** Versanddienst wählen. Gmail oder WEB.DE ist der schnellste Start, Brevo ist die sauberste Lösung mit eigener Domain.
4. **Router & Netzwerk:** Port 25 an Home Assistant weiterleiten. Für OPNsense, FRITZ!Box und andere Router gibt es Schritt-für-Schritt-Anleitungen.
5. **Übersicht:** „Testmail senden“ drücken. Wenn alle drei Stufen grün werden, ist alles eingerichtet.

**Wichtig:**

* Mit einer kostenlosen DuckDNS-Domain klappt der Empfang. Zum Senden nimm Gmail oder WEB.DE, weil du bei DuckDNS keine weiteren DNS-Einträge anlegen kannst.
* Aktualisiert dein Router oder OPNsense (Plugin `os-ddclient`) deinen DNS-Eintrag schon, trage hier **keinen** DuckDNS- oder Cloudflare-Token ein.
* Blockierst du Länder (GeoIP, zum Beispiel „nur Deutschland“), wird auch Mail aus dem Ausland geblockt, und Gmail und Outlook senden meist aus den USA. Lass die Sperre für alles andere bestehen und lege eine Pass-Regel für Port 25 darüber an, die Seite *Router & Netzwerk* zeigt die Schritte für OPNsense.
* Bei DS-Lite oder CGNAT sowie bei gesperrtem Port 25 kommt keine Mail an. Die Seite *Router & Netzwerk* erklärt, wie du das prüfst.
* Liegt deine Domain bei Cloudflare und du brauchst nur wenige Adressen, leitet Cloudflare *Email Routing* kostenlos ohne Heimserver weiter.

## Questions

Open an issue in the [GitHub repository](https://github.com/seb5594/Home-Assistant-Mail-Forwarder-App/issues).
