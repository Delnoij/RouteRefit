# Bekende beperkingen van 0.5.15 Bèta

- Het eerste voorstel kan gedeeltelijk zijn. Volledig uitlijnen vergt voldoende
  lokale weggegevens. Nieuwe downloads veranderen een voorstel niet vanzelf.
- De gemeten tijdwinst geldt voor het eerste gedeeltelijke voorstel bij een trage
  dienst; dit is geen garantie voor iedere route of een volledige uitlijning.
- De aparte achtergrondaanvraag na lokaal uitlijnen is begrensd op 60 seconden
  totaal en 45 seconden per verzoek. Andere downloadpaden behouden 30 seconden
  totaal en 20 seconden per verzoek. Lokale indexopbouw en
  rekenen vallen buiten deze grens. Een uitzonderlijk vastgelopen systeemaanroep
  kan intern nog afronden; maximaal één netwerkwerker blijft daarvoor bestaan.
- Een mislukte aanvraag wordt niet automatisch herhaald of opgesplitst. Probeer
  later zelf opnieuw om ontbrekende gebieden op te halen. Een verplichte pauze
  van de wegendienst wordt binnen dezelfde programmasessie gerespecteerd.
- Een gedeeltelijk voorstel betekent geen volledige uitlijning: ontbrekende
  stukken blijven onopgelost. Zonder bruikbare kaartdekking wordt de route behouden.
- De openbare wegendienst blijft extern en kan uitvallen. Volledige gratis online
  beschikbaarheid en onmiddellijke voltooiing voor iedere route zijn niet gegarandeerd.

- De Windows-build is niet ondertekend. SmartScreen of Smart App Control kan waarschuwen of uitvoering blokkeren. De uitgeversidentiteit is niet geverifieerd.
- Niet ieder apparaatbestand is getest. De importtests gebruiken gecontroleerde testbestanden; fouten in uitzonderlijke varianten kunnen nog voorkomen.
- Uitvoer is GPX, TCX-koers of KML; geen FIT-export. KML vereist minstens twee punten per routedeel. TCX vereist bruikbare routetijden of een berekening via datum/snelheid; lopen en fietsen vereist daarvoor volledige hoogtes. TCX/KML zijn nog niet op echte navigatietoestellen getest. Bij conversie worden sensorkanalen, kaartstijlen en apparaatspecifieke velden niet overgenomen. Bronbestand apart bewaard.
- Een los meetpunt binnen een verder bruikbare route blijft behouden; een bestand met alleen losse punten is geen bewerkbare route. Waypoint-only-bestanden zijn niet als route te openen.
- KMZ ondersteunt één KML. Externe links, afbeeldingen, overlays en Polygon-geometrie worden niet als route geïmporteerd. GeoJSON accepteert lijnen en punten, geen polygonen.
- Hoogtemeters zijn ongefilterde GPX-hoogtes; ruis beïnvloedt stijging en daling. Ontbrekende hoogtes geven gedeeltelijke totalen. Gemiddelde snelheid bevat pauzes.
- Het starttijdveld is UTC. Berekende tijden zijn schattingen. Bij ongelijke tijdzones normaliseert GPX tijdstempels naar UTC.
- Uitlijnen controleert niet alle OSM-afslagrelaties en voorwaardelijke toegang. Een kaartcontrole is geen terreincontrole.
- Achtergrondkaarten en het downloaden/vernieuwen van weggegevens vereisen netwerktoegang. Bij storingen is geen volledige offlinekaart beschikbaar tenzij die al is gecachet.
- Technische foutdetails van Windows, XML- of FIT-bibliotheken kunnen in hun oorspronkelijke taal verschijnen. Gebruikersinhoud wordt niet vertaald.
- De bestaande website-integratie verwijst naar marcodelnoij.nl. De publieke uitgave bevat een lege catalogus; importeer desgewenst een eigen catalogus.
- Windows 11 is het geteste platform. Linux, macOS, grote letterinstellingen en alle schermschalen zijn nog niet volledig getest.

- De wegdownload is begrensd op 200 geplande basisvakken en maximaal 400 netwerkverzoeken bij onderverdeling. Niet elke route van 200 km is ruimtelijk gelijk; er is geen garantie dat elke lengte of regio binnen dat budget past. Het GPX-bestand blijft wel beschikbaar.
- De SignPath-workflow is voorbereid maar nog niet verbonden of door GitHub uitgevoerd.

Automatic changed-road recovery: if obsolete intermediate anchors prevent a valid connection, the app tries a local window of at most 1,500 metres and relaxes interior anchors. Endpoints retain the configured search radius. Connections use current OSM access/direction/topology. Both directions of geometric deviation are checked (maximum 150 metres), and length must remain between 50% and 180% of the old section. Manual sections and segment boundaries are protected. The final combined result is checked again; rejected sections remain review issues. Accepted adaptations are listed in Checks and can be undone. These bounds can still reject major road changes, and a proposal requires visual review.

Travel direction is a candidate preference, not lane-level navigation. OSM road centrelines do not establish the cyclist’s exact lateral position. Explicit direction restrictions and bicycle exceptions are retained. Loop recovery protects recorded circuits, but changed junctions still need review. Turn relations and conditional access are not fully implemented.

Cycling quality uses available OSM surface/width/smoothness/tracktype tags; missing tags cannot prove a path is usable. Mountainbike has a separate rough-surface preference. Driveways and parking aisles are discouraged, not generally forbidden, so a real destination remains reachable. User-reviewed local way choices belong to the particular route proposal and do not establish general routing correctness.

Reconstructed gaps: the proposed roads may differ from the actual journey. Via points guide the proposal. Connection times include any unrecorded pause; active riding time cannot be recovered from missing GPS samples. A connection is bounded to 50 km through at most 50 via points; long detours may need additional via points and road data.

De lokale index bouwt eenmaal op uit bestaande OSM-bestanden. Zonder eerdere download of volledige begrensde regio-import blijven ontbrekende gebieden internet vragen. Grote regiobestanden kunnen een merkbare eerste indexopbouw vragen; de limiet is 128 MB per XML-bestand. Deze handmatige regio-import gebruikt OSM XML; het aparte scherm Gebiedspakketten ondersteunt ook PBF. De datum is de OSM-momentopname of anders de bestandsdatum. Cachegebruik garandeert geen actuele toegangsregels.
# Gebiedspakketten (0.5.11)

De eerste download en voorbereiding kunnen meerdere minuten duren en gebruiken
extra schijfruimte. Kies kleine regio's; maximaal 500 MB download per pakket.
Pakketten zijn optioneel. Zonder pakket blijven opgeslagen wegen bruikbaar;
ontbrekende wegen ophalen kan veel langer duren. Grensroutes kunnen meerdere
gebiedspakketten nodig hebben. Ontbrekende dekking blijft zichtbaar als een
gedeeltelijk voorstel. De achtergrondkaart wordt apart opgehaald.
Zonder expliciete achtergrondoptie werken wekelijkse updates alleen zolang het programma geopend is. Met die opt-in kan Windows het werk na sluiten voortzetten; zie de beperkingen hieronder. Bij gewijzigde
grenzen, meer dan 90 dagelijkse updates achterstand of te grote wijzigingen is
expliciet opnieuw downloaden nodig. Er is geen gegarandeerde externe beschikbaarheid.



0.5.12 area packages: first preparation still depends on area size, disk and CPU
load. Only newly prepared packages use compact storage; existing packages remain
usable and are not silently rebuilt. Select Download again to rebuild explicitly.
Custom areas use full small extracts and manual refresh; no compatible regional
incremental feed is assumed. SliceOSM is a volunteer service and can be slow or
unavailable. Data coverage is conservative near polygons; keep a margin around routes.
Background opt-in needs Windows Task Scheduler; managed Windows policies may refuse
registration. The app reports failure and keeps the option off. Sleep, sign-out,
shutdown and unavailable connectivity prevent work; interrupted jobs need manual
review. Standard OSM map images are not bulk-downloaded with road packages.

0.5.14: activiteiten gebruiken generieke expliciete OSM-toegang en rijrichting
in heel Europa; geen complete database met impliciete nationale regels,
voertuigafmetingen, milieuzones, actuele afsluitingen of maximumsnelheden.
Standaard no/only-afslagrelaties met één via-knooppunt of een reeks via-wegen
worden verwerkt. Niet alle exotische of gecombineerde conditionele relaties
zijn ondersteund. Herkende voorwaardelijke afslagverboden gelden altijd,
zonder tijdvenster te evalueren. Kaart- en terreincontrole blijven nodig.
Motorprofielen vermijden onduidelijke motorische toegang op veld- en voetpaden;
dat kan een legale verbinding afwijzen. Geen routeadvies voor speedpedelecs.
Motorische tijdschattingen modelleren geen verkeer of snelheidslimieten.

Navigatieknoppen uploaden niet via een API: zij slaan een GPX op en openen de
officiële importpagina. Aanmelden, bestand kiezen en import bevestigen gebeuren
bij de dienst. Externe diensten kunnen kosten, voorwaarden en limieten hanteren;
Strava routeplanning kan een abonnement vereisen. Compatibiliteit met alle
toestellen is niet getest. De ontvangende dienst kan opnieuw berekenen.
Afslaginstructies en offline navigatie worden door de dienst/toestel verzorgd.
Voor auto en motor zijn sportdiensten niet algemeen geschikt; gebruik een
GPX-geschikte autonavigator. Er is geen echte accountupload uitgevoerd in tests.
