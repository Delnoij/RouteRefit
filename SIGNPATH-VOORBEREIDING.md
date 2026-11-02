# Optionele gratis ondertekening — nog geen aanvraag

De Windows-build van RouteRefit 0.5.15 Bèta is niet digitaal ondertekend.
Een controlegetal bewijst bestandsintegriteit, geen geverifieerde uitgever.

SignPath Foundation biedt gratis ondertekening aan toegelaten opensourceprojecten.
Een actieve, gedocumenteerde openbare uitgave en naleving van hun voorwaarden
zijn vereist. Toelating van dit nieuwe project is niet gegarandeerd.

Voorgestelde volgorde:

1. Publiceer de gecontroleerde broncode onder GPL-3.0-only en laat de GitHub-workflow
   de tests en Windows-build uitvoeren. De openbare repository is
   [Delnoij/RouteRefit](https://github.com/Delnoij/RouteRefit).
2. Controleer het exacte bouwresultaat en geef een duidelijke bèta-uitgave vrij.
3. Vraag toelating aan met de echte repository, bouwrun, release, onderhoudsrollen
   en privacybeleid. Gebruik uitsluitend echte gebruikscijfers en testresultaten.
4. Configureer pas na toelating de koppeling en handmatige goedkeuring van elke
   ondertekening. Bewaar geheimen in de accountinstellingen, nooit in broncode.
5. Controleer de handtekening, tijdstempel en herkomst vóór publicatie. Maak nieuwe
   controlegetallen voor de ondertekende downloads.

De huidige workflow bouwt ongetekende bestanden; een werkende SignPath-koppeling
is nog niet ingericht. CODE-SIGNING-POLICY.md beschrijft de verantwoordelijkheden.

## Concrete stand van zaken voor de eerste aanvraag

Lokaal voorbereid en controleerbaar:
- GPL-3.0-only, afhankelijkheden en afzonderlijke licentievermeldingen.
- Volledige bron met tests, vastgelegde pakketten en gecontroleerde Inno-bouwer.
- Lege routecatalogus; alleen vooraf beoordeelde demonstratiegegevens.
- Windows-installer met privacyuitleg, optionele handelingen en verwijderfunctie.
- Installercontrole: eerste installatie, weigeren bij een geopend bestand,
  opnieuw installeren, gegevens behouden, verwijderen en taken van andere kopieën behouden.
- Code signing policy is gelinkt vanaf README en RELEASE-NOTES.

Nog feitelijk vast te stellen vóór een aanvraag:
- De echte openbare repository en downloadpagina, met een geslaagde GitHub-run
  die precies de aangeboden installer oplevert. Lokale bestanden bewijzen dit niet.
- MFA op GitHub en later SignPath; daadwerkelijke branchbescherming en bevoegdheden.
- Een aparte Windows 11-pc-test en aantoonbare gebruikservaring of onafhankelijke
  review. Het project heeft nog geen aangetoonde openbare reputatie.
- Beoordeling van netwerktoestemming: zichtbare kaartbeelden kunnen automatisch
  online worden opgehaald. Er is nog geen algemene offline-schakelaar in de app.
  De installatie toont dit gedrag, maar het voldoen aan een eventuele eis voor
  uitschakelbare netwerkfuncties moet met SignPath worden vastgesteld of verbeterd.
- Acceptatie door SignPath, metadatarestricties voor eigen bestanden en een
  werkende volgorde voor ondertekenen van app, verwijderprogramma en installer.

Publiceer geen acceptatielogo of sponsorvermelding vooraf. Voeg de door SignPath
gevraagde credit pas na daadwerkelijke toelating toe. Geen gebruikersaantallen,
reviews, MFA-status of CI-resultaten invullen die niet zijn geverifieerd.

Officiële bronnen, gecontroleerd op 2 november 2026:
- https://signpath.org/
- https://signpath.org/terms.html

Dit is een mogelijke vervolgstap, geen ingediende aanvraag of toezegging van gratis
ondertekening. Een digitale handtekening garandeert ook geen afwezigheid van fouten.
