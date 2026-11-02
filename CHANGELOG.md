## 0.5.15 Bèta - exportlabel en vindbare toegangsopties

De zes handleidingen zijn nu staand A4 (47 pagina’s, 33 hoofdstukken).
Hoofdstuk 33 beschrijft de lokale GPX-, TCX- en KML-export.

Nieuw: Exporteer naar > Bestand… biedt GPX, TCX en KML. TCX is een koers
met bestaande of zelf ingestelde routetijden. GPX/KML bevatten geen tijden.
Export blijft lokaal; bestaande bestanden worden nooit overschreven.

- Navigatie is Exporteer naar bij de drie logoknoppen. Kleinere logo's, tekst
  en knopmarges houden ruimte vrij voor toekomstige exportmogelijkheden.
- Bestaande privéwegenoptie staat hoger in Instellingen > Route, samen met
  Toegangsmeldingen. Nieuwe snelkoppeling vanaf Activiteit.
- Label verduidelijkt naar Sta privéwegen en -paden toe. Zelfde opgeslagen
  allow_private-instelling en hetzelfde rekenbeleid; geen nieuwe toestemming.
- Handleiding legt de twee bestaande toegangsfuncties en hun grenzen uit.

## 0.5.14 Bèta - activiteiten, sneller lokaal uitlijnen en navigatie-export

- Activiteit vervangt Vervoer: Lopen, Fiets, MTB, Gravelfiets, Auto en Motor.
  Speedpedelec is weggelaten. Oude route-instellingen blijven leesbaar.
- Eigen toegangshiërarchie, rijrichtingen en wegvoorkeuren voor auto/motor;
  gravel heeft eigen voorkeuren en vermijdt zware trails.
- Standaard OSM-afslagrelaties met via-knooppunt of via-wegen worden meegenomen,
  inclusief activiteituitzonderingen en aankomstrichting over hoofdpunten heen.
  Geen volledige landelijke of voorwaardelijke verkeersregelendatabase.
- Ruimtelijke selectie versnelt de controle van lokale kaartdekking. Zwaardere
  afslagcontrole wordt alleen uitgevoerd wanneer zo'n kruising bereikbaar is.
- Zichtbare logoknoppen voor Komoot, Garmin en Strava: lokaal navigatie-GPX
  opslaan, officiële importpagina openen, gebruiker kiest en uploadt zelf.
- Navigatie-export bewaart de gekozen geometrie en hoogtes, laat tijden weg,
  overschrijft geen bestanden en verandert de bewerkbare route niet.
- De bestaande Strava-activiteitsexport met aangepaste tijden blijft beschikbaar.
- Handleidingen en bediening in alle zes talen bijgewerkt.

## 0.5.13 Bèta - handmatig verder na overnemen

- Geaccepteerde uitlijnvoorstellen openen direct met alle hoofdpunten bewerkbaar.
- Zichtbare keuze Hoofdpunten naast Losse punten en Stuk kiezen.
- Geen impliciete volledige uitlijning bij Tijdschema berekenen: handmatige
  correcties blijven behouden en deze tijdactie werkt zonder wegdownload.
- Na een tijdvoorstel blijft de gekozen handmatige bewerkstand actief.
- GPX-controlerapport bewaart de bewerkstand voor later verderwerken.
- Bestaande probleemmarkeringen, ongedaan maken en onafhankelijke wegdownloads
  blijven beschikbaar; downloaden past nooit zelf de geaccepteerde lijn aan.
- Handleidingen en bediening in alle zes talen bijgewerkt.

## 0.5.12 Bèta - eigen gebieden, sneller verwerken en optionele Windows-achtergrondtaken

- Rechthoek of veelhoek tekenen, ook over landsgrenzen, met eigen lokale naam.
- SliceOSM als optionele bron voor kleine gebieden; expliciete privacyuitleg,
  begrensde wachttijd, één aanvraag en handmatig hervatten van hetzelfde verzoek.
- Compacte, exacte kaartpunten, native filters en parallelle PBF-verwerking.
  Alle punten, wegkenmerken en afslagrelaties blijven beschikbaar voor updates.
- Drie zichtbare fasen: downloaden, lokaal verwerken en controleren.
- Achtergrondwerk na sluiten is standaard uit. Alleen de expliciete opt-in maakt
  een Windows-taak bij aanmelden en dagelijks om 09:00. Uitvinken stopt werk en
  verwijdert die taak. Eigen gebieden worden handmatig vernieuwd.
- Lagere prioriteit en extra pauzes bij concurrerende processorbelasting;
  normale snelheid bij beschikbare capaciteit, met begrensd geheugengebruik.
- Zes handleidingen bijgewerkt, inclusief opt-in, privacy en updateverschillen.

## 0.5.10 Bèta - achtergrondantwoord niet te vroeg afbreken

- Aparte achtergrondaanvragen na het lokale voorstel: 45 seconden per verzoek,
  maximaal 60 seconden totaal. Serveruitvoering begrensd op 25 seconden.
- Lokale voorstellen blijven snel; directe downloadpaden behouden hun kortere limiet.
- Verstreken downloadtijd zichtbaar zonder herhaalde aftellingen of automatische poging.
- Oorzaak van fouten zichtbaar: te traag, wachttijd, dienst onbereikbaar, verbinding,
  onvolledige gegevens of lokale verwerking. Geen URL, routecoördinaten of pad in die uitleg.
- Stoppen, ongewijzigde voorstellen, expliciet aanvullen en gegevensbehoud blijven gelden.

## 0.5.9 Bèta - eerst lokaal uitlijnen

- Automatisch uitlijnen maakt eerst een voorstel met aantoonbaar bruikbare lokale wegen.
- Ontbrekende gebieden worden daarna apart opgehaald; het eerste voorstel wacht niet.
- Voorstel aanvullen rekent alleen op expliciete keuze opnieuw met de opgeslagen wegen.
- Achtergrondresultaten wijzigen geen route, instellingen of openstaand voorstel.
- Download stoppen, annuleren, route-/instellingwissel en afsluiten stoppen de oude aanvraag.
- Gedeeltelijke download kan via Voorstel aanvullen benut worden; geen automatische herhaling.
- Bij overnemen kan de download doorlopen. Ongedaan en brongegevens blijven behouden.

## 0.5.8 Bèta - wegdownload stopt na de eerste storing

- Oude automatische herhalingen en aftellingen verwijderd, ook bij Kaart ophalen,
  vernieuwen en verbinden. Geen nieuwe deelverzoeken na een overbelaste aanvraag.
- Maximaal 20 seconden per verzoek en 30 seconden per downloadfase op alle paden.
- Een handmatige nieuwe poging respecteert de pauze van de dienst, zonder wachten
  of automatisch hervatten. Complete opgeslagen kaartvakken blijven bruikbaar.
- Eerdere voortgangstekst kan een afgeronde kaartdownload niet opnieuw actief tonen.
- Geen wijziging aan routebestanden, instellingen, rekentijden of aanbieders.

## 0.5.7 Bèta - snelle berekening en begrensd wachten

- Routeafstanden en het primaire wegennet hergebruiken tijdens automatisch herstel;
  inhoudscontrole en begrensde geheugencaches behouden.
- Netwerkfase bij uitlijnen begrensd op 30 seconden, afzonderlijk verzoek op 20 seconden.
- Bij trage of onbereikbare wegendienst bruikbare opgeslagen gebieden uitlijnen;
  ontbrekende stukken behouden met zichtbare, onopgeloste meldingen.
- Alleen aantoonbaar volledig gedekte wegen gebruiken bij gedeeltelijke gegevens.
- Stoppen onderbreekt CPU-werk en netwerk-wachten. Late antwoorden raken routes niet.
- Geen nieuwe aanbieder, account, abonnement of route-upload.

## 0.5.6 Bèta - export, kalender en voortgang

- Moderne voortgangsindicator en windroos met vier windrichtingen.
- Lokale GPX-export voor Strava, Garmin, Komoot en Wikiloc met dienstlogo's.
- Kalender, tijdkiezer en tijdverdeling naar hoogte en vervoermiddel.
- Berekende tijden blijven herkenbaar als schattingen; geen automatische upload.

## 0.5.5 Bèta - zes talen, uitgebreide uitleg en zichtbare voortgang

- Spaans en Europees Portugees toegevoegd aan alle programmavensters en meldingen.
- Zes handleidingen met elk 27 hoofdstukken, genummerde stappen en elf echte schermafdrukken.
- Zichtbare stap, bewegende indicator, verstreken tijd en stopknop tijdens uitlijnen;
  echte aftelling alleen bij wachten op de wegendienst.
- Lagere geheugenvraag voor kaartaanvragen; te zware aanvragen begrensd opdelen.
  Bestaande wachttijden, limieten en reeds opgeslagen complete kaartvakken respecteren.
- Duidelijke melding bij onbereikbare/bezette wegendienst: route blijft behouden,
  later opnieuw proberen haalt ontbrekende gebieden op.
- Eigen controlerapporten worden bij mapcontrole niet als ongeldige GeoJSON behandeld.
- Ontwerp voor toekomstige routecreatie; eerst testen en meer vervoermiddelen valideren.
- Bestaande lokale wegkeuze en alle huidige functies behouden. Geen nieuwe voertuigen,
  heatmaps of betaalde diensten toegevoegd.

## 0.5.4 Bèta - lokale wegenindex (1 november 2026)

- Blijvende ruimtelijke index voor gedownloade OSM-wegen; hergebruik na herstart en bij gewijzigde routes.
- Alleen ontbrekende gebieden downloaden. Geen extra voorbereidingsstap voor de gebruiker.
- Direct het benodigde wegennet lezen zonder complete regiobestanden opnieuw te ontleden.
- Begrensde OSM-regio-imports privé bewaren en voor latere routes hergebruiken; onbegrensde imports blijven bruikbaar zonder onterechte gebiedsdekking.
- Actualiseren verwerkt gewijzigde toegang en verdwenen wegen; oude overlappende vakken overschrijven geen nieuwere gegevens.
- Bestaande wegkeuze, toegang, richting, voorstel/overnemen en ongedaan maken behouden.
- Lege publieke uitgave bewaakt met controles op broncode, Windows-map, ZIP-inhoud en goedgekeurde demonstratiebestanden.
- De lokale index en kaartgegevens blijven uitsluitend in de privétestinstallatie.

## 0.5.3 Bèta - sneller uitlijnen

- Wegennet en toegangs-/richtingskosten per profiel hergebruiken, met controle op gewijzigde kaartinhoud.
- Eén uitlijnberekening in plaats van deelvoorbeelden gevolgd door een volledige tweede berekening.
- Ongewijzigde padzoekresultaten hergebruiken; gewijzigde netwerkdelen, projecties en afstandsgrenzen blijven gecontroleerd.
- Begrensde caches in het geheugen; geen nieuwe externe dienst of gewijzigde wegvoorkeuren.
- Vergelijking met de bevroren 0.5.2-motor: dezelfde uitkomsten bij 80 varianten en de TCX-/FIT-praktijkroutes.
- 249 automatische tests en zes interfacecontroles in vier talen.

## Eenvoudig uitlijnen in 0.5.2 Bèta

- Route openen zonder voorafgaande wegdownload; twee directe uitlijnknoppen.
- Plaatselijke weggegevens automatisch ophalen; bestaande vakken hergebruiken en aangrenzende vakken bundelen.
- Hoofdpunt verwijderen vervangt de oude tussenpunten tussen de overblijvende hoofdpunten.
- Meer rechtermuisknopacties en stoppen/wisselen tijdens een berekening.
- Berekende geometrie en geschatte tijden blijven een voorstel tot overnemen.
- 237 automatische tests en zes interfacecontroles in vier talen.

# RouteRefit 0.5.2 Bèta - 31 oktober 2026

- Vervoermiddel, routevoorkeur en tijdschema apart bediend, opgeslagen en hersteld.
- Bestaande rapporten worden gemigreerd; eigen snelheid, starttijd en gewenste duur blijven behouden.
- Tempo wijzigt geen wegkeuze of toegangsbeoordeling. Een vervoermiddelwijziging vraagt wel nieuwe controle.
- Automatische uitlijning, losse herberekening, hoofdpuntherstel en start/eindaansluitingen vragen overname van een voorstel.
- Gecombineerde berekening toont één route-/tijdvoorstel zonder de bewerkbare lijn vooraf te wijzigen.
- Voorstellen tonen afstand, tijdschema/reistijd, stijging, hoogtevolledigheid en verschil met origineel/bewerking.
- Tijdschattingen blijven na overname herkenbaar in het rapport; ongedaan maken herstelt ook deze status.
- 226 automatische tests en vier desktopcontroles in vier talen.
- Geen nieuwe routeringsdienst, routegewichten, vervoermiddelen, heatmaps of volledige afslagrelatie-ondersteuning.

# RouteRefit 0.5.1 Bèta - toegangstest, 31 oktober 2026

- Ontbrekende fiets-/voetgangerstoestemming of cycleway=separate is geen automatisch verbod op gewone wegen en paden.
- Toegangshiërarchie bicycle > vehicle > access en foot > access; dezelfde beoordeling bij wegknopen.
- Wegvoorkeuren, kwaliteitsgewichten, rijrichting en fysieke barrières behouden.
- Toegangsmeldingen… onderzoekt en accepteert uitsluitend aantoonbare toegangsproblemen, na waarschuwing. De bestaande lijn, hoogtes en tijden blijven behouden.
- Keuze staat apart in het controlerapport; annuleren, ongedaan maken en heropenen getest. Wijzigingen aan lijn, activiteit, uitlijninstellingen of kaart vragen nieuwe beoordeling.
- 218 automatische tests en drie desktopcontroles in elk van vier talen.
- Geen nieuwe vervoermiddelen, heatmaps of alternatieve routeringsdienst; die volgen later.

# RouteRefit 0.5.0 Bèta - 31 oktober 2026

- Voortgezet vanuit de aangeleverde GPX-werkbank 0.7.1 beta, zonder herbouw van de route-engine.
- Nieuwe naam en centrale versie in interface, Windows-eigenschappen, exports, bouw- en releasebestanden.
- Routes eerst; website-routeoverzicht achteraan. Kaartbediening gegroepeerd, met direct bereikbare verbindingen, berekening, statistieken en GPX-export.
- Werkbalken verdelen zich bij ruimtegebrek over meer regels. Extra acties onder Meer; bestaande menu's en sneltoetsen behouden.
- Vertaling van tabbladen hersteld en afgekapt statistiekuitleg aangepast.
- Vier PDF-handleidingen met echte schermafdrukken van de Nederlandse, Engelse, Duitse en Franse interface.
- 207 regressietests en aanvullende desktopcontroles in vier talen opnieuw uitgevoerd.
- Alleen lokale, ongetekende testuitgave. Niets gepubliceerd; geen SignPath-aanvraag. Versie 1.0 wordt later de eerste stabiele uitgave.

## Historie vóór de naamswijziging

# Changelog

## 0.7.1 beta — 30 oktober 2026

- Nieuwe versienummering voor de Windows-beta; 1.0 wordt de stabiele uitgave.
- Routedelen verbinden met kaartvoorbeeld en verplaatsbare, verwijderbare en te ordenen tussenpunten. Overnemen en ongedaan maken; GPX-export ondersteunt samengevoegde routedelen.
- Aansluitende TCX-rondegrenzen worden vóór uitlijning verbonden; identieke meetpunten blijven behouden. Echte opnamegaten worden niet stilzwijgend als opgenomen lijn voorgesteld.
- FIT herkent de opgegeven fietsactiviteit; stilstaande timerstops sluiten aan. Losse meetpunten binnen een verder bruikbare route blijven behouden.
- Reconstructies staan in GPX en controlerapport, met geschatte tijden/hoogtes. Het originele bestand blijft bewaard.
- Lokale routeringsgraaf voor verbindingen; ongebruikte oude routeringsimplementatie verwijderd; ongebruikte AVIF-codec niet meegeleverd. Ondersteunde fotoformaten behouden.
- Nieuwe interface en meldingen in Nederlands, Engels, Duits en Frans.
- 207 automatische tests; desktopcontroles voor import, vergelijken, tussenpunten, opslaan, heropenen en ongedaan maken in vier talen.
- Windows-versie blijft ongetekend. Geen GitHub-publicatie of SignPath-aanvraag.

Onderstaande vermeldingen documenteren eerdere interne testnummers.

## 0.9.5 beta — 30 oktober 2026

- De fietsuitlijner onthoudt bij een hoofdpunt ook de aankomstrichting. Een nieuw ontstane scherpe omkeerbeweging krijgt extra kosten; een bewust opgenomen U-bocht blijft mogelijk.
- Rijbaanrotondes houden hun impliciete eenrichtingsverkeer. Afzonderlijke tweerichtingsfietspaden erven die rijbaanregel niet.
- Vijf aanvullende regressietests voor kruisingen, aankomstrichting, lopen, opgenomen U-bochten en rotondes/fietspaden.
- Het privévoorstel is uitsluitend bij drie gemelde rotondes hersteld. Alle routepunten buiten die drie vensters zijn gecontroleerd gelijk aan 0.9.4. Vergelijken kan nu expliciet de vorige versie als referentie tonen.
- Nog geen digitale ondertekening, SignPath-aanvraag of publicatie.

## 0.9.4 beta — 30 oktober 2026

- Fietsvoorkeuren wegen bekende ondergrond, breedte, smoothness en tracktype mee. Het label fietspad alleen maakt een smal of slecht pad niet de beste keuze.
- Opritten en parkeerwegen krijgen hogere kosten en minder voorkeur als uitlijnanker. Ze blijven bereikbaar wanneer de gebruiker er een echt aansluitpunt/bestemming kiest.
- Fietstoegang op knooppunten, afstappen-tags en niet als fietsdoorgang gemarkeerde klaphekjes/stiles worden strenger behandeld. Poorten en fietsbarrières krijgen een nadeel in de wegkeuze.
- Mountainbike heeft een eigen afweging voor ruwe paden. De route-identiteit bevat nu ook deze profielkeuze, zodat een oud berekeningsresultaat niet bij de verkeerde stijl wordt toegepast.
- Acht nieuwe regressietests. Een privéroute is daarnaast gericht op elf gemelde locaties gecontroleerd. Deze plaatselijke keuzes zijn onderdeel van dat specifieke voorstel; de algemene uitlijner is daarmee geen volledige verkeerskundige routeplanner geworden.
- Alle eerdere functies behouden. Geen ondertekening, SignPath-aanvraag of publicatie.

## 0.9.3 beta — 30 oktober 2026

- De reisrichting van de opname telt mee bij het kiezen tussen parallelle fietspaden. OSM-richting en expliciete fietsuitzonderingen blijven verplicht; richtingvoorkeur geeft geen toegang waar die ontbreekt.
- Nieuwe korte lussen door verouderde tussenpunten worden herkend en plaatselijk opnieuw geprobeerd. Opgenomen rondjes, heen-en-terugstukken, handmatige uitzonderingen en losse routedelen blijven beschermd. Onopgeloste gevallen blijven zichtbaar voor beoordeling.
- Blauwe pijlen op de bewerkte lijn tonen de rijrichting vanaf zoomniveau 15.
- Privé-praktijktest: aangepast voorstel via de kern van Schinveld; het extra rondje van circa 117 meter bij de Odasingel is verdwenen. Dit is geen bewijs van actuele bebording of volledige verwerking van afslagrelaties.
- Zes nieuwe regressietests voor reisrichting, fietsuitzonderingen en lussen. Publicatie en ondertekening blijven uitgesteld tot beoordeling door EOSfoto.

## 0.9.2 beta — 30 oktober 2026

- Fietsprofielen geven geschikte fietspaden voorrang boven hoofdwegen, met behoud van toegang, rijrichting, zoekafstand en echte OSM-aansluitpunten. Bruggen en tunnels worden niet verbonden op alleen kruisende coördinaten. Een gedeeld OSM-knooppunt blijft wel een aansluiting bij een brughelling.
- Activiteitstype in GPX herkend, waaronder e_bike_fitness. Onbekende of gemengde activiteit vraagt eerst een profielkeuze; automatisch uitlijnen staat dan uit. Bestaande profielvoorkeuren blijven leidend.
- Wegdownload via de alleen-lezen Overpass-dienst. Wachttijd bij HTTP 429/502/503/504/509 wordt gerespecteerd, met aftellen en begrensde herhaling. Voltooide kaartvakken blijven beschikbaar voor een volgende poging, ook uit naastgelegen 0.9.0/0.9.1-testmappen.
- Onvolledige Overpass-antwoorden worden geweigerd. Een mislukte vernieuwing behoudt bestaande weggegevens. GPX, hoogteprofiel en handmatige bewerking blijven beschikbaar.
- Aanvullende controles voor parallelle fietspaden, toegang, rijrichting, niveaukruisingen en downloadbeperkingen. Nog geen ondertekening of publicatie.

## 0.9.1 beta — 30 oktober 2026

- OSM-weggegevens volgen een strook langs de route; maximaal 200 basisvakken. Dit vervangt de te krappe rechthoekgrens van 36 vakken.
- Voortgang tijdens het ophalen. GPX en statistieken blijven beschikbaar als optionele weggegevens ontbreken; geen blokkerende importfout daarvoor.
- XML van een geïmporteerd bestand wordt één keer gevalideerd en hergebruikt. Handmatige import leest het bestand op de achtergrond.
- Analyse van het hoogteprofiel staat in een aparte module, met hergebruik bij vensterwijzigingen. Weergave bewaart pieken en dalen; aanwijzer gebruikt de originele punten.
- Dubbele KML-inhoud wordt ook bij verschillende bestandsnamen herkend.
- Broncode opgemaakt, versie-informatie gecentraliseerd, GPL-3.0-only toegevoegd.
- Hash-vergrendelde Windows-afhankelijkheden, vaste Actions-revisies, review-buildworkflow en SignPath-voorbereiding. Nog geen ondertekening of publicatie.

## 0.9.0 beta — 30 oktober 2026

Eerste lokale Windows-testversie op basis van GPX-werkbank 1.8: menu’s, grote kaart, handmatige import, mapcontrole, hoogteprofiel, statistieken, vier talen en aanvullende importformaten.

Merge en split maken nog geen deel uit van deze beta's.

Automatic changed-road recovery: if obsolete intermediate anchors prevent a valid connection, the app tries a local window of at most 1,500 metres and relaxes interior anchors. Endpoints retain the configured search radius. Connections use current OSM access/direction/topology. Both directions of geometric deviation are checked (maximum 150 metres), and length must remain between 50% and 180% of the old section. Manual sections and segment boundaries are protected. The final combined result is checked again; rejected sections remain review issues. Accepted adaptations are listed in Checks and can be undone. These bounds can still reject major road changes, and a proposal requires visual review.
# 0.5.11 Bèta

- Optionele gratis Geofabrik-gebiedspakketten; meerdere gebieden en landen in één
  downloadlijst, met gecombineerde lokale dekking bij grensroutes.
- Streaming voorbereiding, lokale ruimtelijke wegenindex en wekelijkse kleine
  updates. Een fout of annulering behoudt het bestaande pakket en alle routes.
- Nieuwe hoofdstukken over pakketten en updates in zes PDF-handleidingen.
- Help / Over RouteRefit: Marco Delnoij, GPL-3.0-only (2026) en OSM/ODbL-vermelding.

