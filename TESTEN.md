## Aanvulling 0.5.9: eerst lokaal

Open een route en kies Automatisch uitlijnen. Bij gedeeltelijke opgeslagen wegen
verschijnt eerst een gemarkeerd gedeeltelijk voorstel. De wegdownload heeft een
eigen status en knop Download stoppen. Zodra nieuwe wegen beschikbaar zijn,
wordt Voorstel aanvullen actief. Er verschijnt nooit vanzelf een vervangend voorstel.
Pas Voorstel overnemen verandert de route; Ongedaan moet die wijziging herstellen.
Annuleren of Download stoppen onderbreekt de achtergrondaanvraag. Een andere route,
instelling of afsluiten stopt de oude aanvraag. Bij storing mag geen nieuwe
aftelling beginnen. Zonder lokale wegen blijft de editor bruikbaar; klik na een
succesvolle download op Voorstel aanvullen. Zie CHANGELOG.md voor de versiegeschiedenis.

# Testen vóór openbare publicatie

Gebruik kopieën van bestanden en houd de oorspronkelijke bestanden apart. Deze beta is bedoeld om praktijkproblemen zichtbaar te maken.

1. Pak de Windows-versie in een nieuwe, schrijfbare map uit. Controleer het versienummer 0.5.15 Bèta. Controleer dat er geen persoonlijke routes of kaartcache in het downloadpakket zitten.
2. Importeer een GPX van elk apparaat dat je wilt ondersteunen; vergelijk naam, segmenten, punten, hoogtes, tijden en waypoints met de bron.
3. Controleer een map met geldige, ongeldige en dubbele bestanden. Test met en zonder submappen. Open vervolgens zelf één bestand.
4. Controleer hoogteprofiel en statistieken. Test ontbrekende hoogtes, een vlakke route, losse segmenten, ontbrekende tijden en een berekend voorstel.
5. Kies elke taal. Controleer de menu’s, activiteit, tijdprofiel, meldingen, fotoformulier en opslaan. De activiteit moet na vertaling dezelfde instelling gebruiken.
6. Test KML, KMZ, FIT, TCX en GeoJSON uit echte apparaten/apps. Let erop dat sensorkanalen niet in GPX worden overgenomen. Vergelijk tijdzones, hoogtes, losse segmenten en course points.
7. Test routepunten, hoofdpunten, start/eind, waypoints met foto, herstelvoorstel accepteren én annuleren, ongedaan maken, pauzes en apart opslaan. Controleer het geëxporteerde bestand opnieuw in een tweede programma.
8. Test OSM downloaden/vernieuwen en werken zonder internet. Controleer dat een mislukte vernieuwing eerder bruikbare gegevens behoudt.
9. Test afsluiten en taal wisselen met niet-opgeslagen werk. Controleer dat de keuze om te blijven werken wordt gerespecteerd.
10. Test op een tweede Windows 11-pc zonder Python, en op verschillende schermschalen. Deze tweede-pc-test is nog niet uitgevoerd in deze sessie.

Meld bij problemen: versie, Windows-versie, taal, bestandsformaat, stappen, verwacht resultaat en werkelijk resultaat. Voeg alleen een klein geanonimiseerd voorbeeld toe als het probleem daarmee te reproduceren is; publiceer geen persoonlijke locatiegegevens.

De automatische testuitslag staat in VALIDATIE.txt. Geslaagde tests zijn geen garantie dat iedere route of ieder apparaatbestand goed werkt.

De bovenstaande stappen vormen de praktijktest. Een test op een tweede Windows 11-pc zonder Python blijft nodig vóór een stabiele uitgave.

Ontwikkelcontrole voor verbinden: `python tests/ui_segment_join.py` controleert in zes talen tussenpunten toevoegen/verplaatsen, voorstel opnieuw berekenen, GPX/rapport opslaan, ongedaan maken en heropenen.

Ontwikkelcontrole voor de lokale wegenindex: `python tests/ui_road_index.py` controleert herstart/hergebruik, uitlijnen zonder netwerk, voorstel annuleren/overnemen en ongedaan maken in zes talen.

`python tests/ui_alignment_progress.py` controleert zichtbare voortgang, verstreken tijd, stoppen en negeren van een te laat werkresultaat in zes talen.
