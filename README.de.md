# Mail Forwarder

[🇬🇧 English](README.md) · **🇩🇪 Deutsch**

> **Experimentell.** Die App ist neu und wurde in der Praxis noch wenig getestet.

Mail Forwarder gibt dir und deiner Familie E-Mail-Adressen auf **deiner eigenen Domain** und leitet alles an das Postfach weiter, das ohnehin genutzt wird (Gmail, Outlook/Hotmail, WEB.DE, ...). Es gibt keine Postfächer und keinen Speicherbedarf: Eine Nachricht wird angenommen, weitergereicht und wieder vergessen.

* Die App-Seite ist zweisprachig (Deutsch/Englisch) und folgt der Sprache deines Browsers.
* Pro Person ein echtes Postfach und beliebig viele Adressen, auch auf mehreren Domains.
* Kostenlose DuckDNS-Namen funktionieren zum Empfangen, die App hält sie auf deiner aktuellen IP-Adresse.
* Eine geführte Seite in Home Assistant erklärt DNS-Einträge, Versanddienst und Router (OPNsense, FRITZ!Box), prüft alles und zeigt, welcher Port oder Eintrag fehlt.
* Die Testmail beweist den ganzen Weg: raus über den Versanddienst, über das Internet wieder herein und weiter ins Postfach.
* Unbekannte Adressen werden schon im SMTP-Gespräch abgelehnt: kein offenes Relay, keine Rückläufer an gefälschte Absender.

Die vollständige Beschreibung steht auf Englisch in der [Dokumentation](mail_forwarder/DOCS.md). Die App-Seite selbst führt dich Schritt für Schritt durch die Einrichtung.

**Voraussetzungen:** eine öffentliche IPv4-Adresse (kein CGNAT/DS-Lite), ein Router mit Portweiterleitung für Port 25, eine eigene Domain oder ein DuckDNS-Name und ein kostenloser Versanddienst (oder ein Gmail- bzw. WEB.DE-Konto).
