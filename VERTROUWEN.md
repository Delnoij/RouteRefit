# Vertrouwen en Windows-ondertekening

Deze beta is niet digitaal ondertekend. Een SHA-256-controlegetal controleert of een bestand overeenkomt met het gepubliceerde bestand; het verifieert geen uitgeversidentiteit.

Voor een geverifieerde uitgeversnaam is ondertekening met een vertrouwd codeondertekeningscertificaat nodig. SmartScreen beoordeelt ook bestands- en uitgeversreputatie. Een nieuwe, correct ondertekende app kan aanvankelijk nog waarschuwingen tonen. Een zelfgemaakt certificaat lost dit voor openbare verspreiding niet op.

Voor latere verspreiding: onderzoek een regulier certificaat, SignPath Foundation bij een kwalificerend opensourceproject, of Microsoft Store-distributie als MSIX. Microsoft Artifact Signing vereist identiteitsvalidatie; individuele ontwikkelaars zijn volgens de geraadpleegde voorwaarden beperkt tot VS/Canada, organisaties in de EU kunnen wel in aanmerking komen. Er is hier geen certificaat aangeschaft, account aangevraagd of handtekening geplaatst.

Leg publiek uit wat de app doet, welke internetverbindingen zij gebruikt, welke tests zijn uitgevoerd en welke beperkingen bekend zijn. Publiceer broncode, release-informatie en controlegetallen via een vaste eigen GitHub-release. GPL-3.0-only is gekozen en meegeleverd. Houd persoonlijke GPX-bestanden en kaartcache buiten het pakket.

Geraadpleegd op 30 oktober 2026:

- https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation
- https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options
- https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart

Wijzig Windows-beveiligingsinstellingen niet om het programma te laten draaien. Een bètalabel, testuitslag of antiviruscontrole vervangt geen digitale ondertekening of beoordeling van de herkomst.
