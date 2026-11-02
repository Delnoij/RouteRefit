# RouteRefit

**0.5.15 Bèta — Windows 11, 64-bits.**

GitHub-beheerder: [@Delnoij](https://github.com/Delnoij).

RouteRefit is een gratis, lokaal programma van **Marco Delnoij (EOSfoto)** voor
het controleren, herstellen en bewerken van routes. Je beoordeelt elk voorstel
voordat het je bewerkbare route vervangt. Deze versie is een bèta; zie
[bekende beperkingen](KNOWN-ISSUES.md).

## Downloaden en starten

De Windows-download hoort bij **Releases** op GitHub. Kies daar
`RouteRefit-0.5.15-beta-Setup.exe`. De broncode is bedoeld voor ontwikkelaars.

1. Start de installer, lees de licentie en privacyuitleg en kies de programmamap.
2. Open RouteRefit via het Startmenu. Python installeren is niet nodig.
3. Kies **Route importeren…**, open een route en kies **Automatisch uitlijnen**
   of **Handmatig uitlijnen**. Controleer het resultaat vóór **Voorstel overnemen**.
4. Via **Help → Handleiding** open je de handleiding in de gekozen taal.

Een draagbare versie is ook beschikbaar: pak de volledige Windows-ZIP uit,
start `RouteRefit-0.5.15-beta.exe` en laat `_internal` ernaast staan.
De Windows-build is niet digitaal ondertekend; Windows kan waarschuwen of
uitvoering blokkeren. Zie [VERTROUWEN.md](VERTROUWEN.md).

## Bestaande routes en kaarten behouden

RouteRefit bewaart gebruikersgegevens bij het programma. De installer gebruikt
standaard `%LOCALAPPDATA%\RouteRefit` voor de huidige gebruiker en behoudt deze
map bij volgende updates. De programmanaam blijft `RouteRefit.exe`. Een tweede
uitgepakte kopie heeft daarom een eigen gegevensmap. Dat kan verklaren waarom een
kopie opnieuw wegen wil downloaden terwijl een andere kopie die al heeft.

Bij overstappen van een draagbare versie kun je in de installer de bestaande
RouteRefit-map kiezen. De installer verplaatst niets tussen mappen en bevat
geen gebruikersgegevens. Maak vóór een update een reservekopie en sluit RouteRefit na het opslaan van je
werk. Bewaar de volledige mappen `Mijn GPX` en `Kaarten` en, indien aanwezig,
`voorkeuren.json`. Alleen bij een overstap naar een andere map neem je die mee; laat de oude kopie
staan totdat je routes, bewerkingen en instellingen in de nieuwe versie hebt
gecontroleerd. Bij ingeschakeld downloaden na sluiten: schakel die optie vóór
het kopiëren uit en zet haar desgewenst in de nieuwe versie weer aan.
Gebruikersgegevens horen nooit in een openbare download of broncoderepository.

Verwijderen kan via **Windows Instellingen → Apps**. Je persoonlijke bestanden
blijven staan. Alleen de achtergrondtaak en optionele websitekoppeling die naar
deze installatie wijzen worden verwijderd. Na herinstallatie moet je gewenst
achtergrondwerk zelf opnieuw uit- en aanzetten. De installer verandert geen
GPX-bestandskoppeling en maakt geen automatische achtergrondtaak.

## Wat kan RouteRefit?

- GPX, TCX, FIT, KML, KMZ en GeoJSON importeren.
- Routes automatisch uitlijnen en daarna handmatig verder bewerken, met
  hoofdpunten, losse punten, waypoints, ongedaan maken en controle van routedelen.
- Hoogteprofiel, afstand en statistieken bekijken; een tijdschema berekenen.
- Activiteiten: Lopen, Fiets, MTB, Gravelfiets, Auto en Motor.
- Eerst beschikbare lokale wegen gebruiken. Ontbrekende wegen apart op de
  achtergrond ophalen, met een begrensde wachttijd en zonder automatische herhaalpoging.
- Optionele gebiedspakketten downloaden, ook meerdere gebieden over landsgrenzen.
  Zonder pakket werkt het programma ook, maar ontbrekende wegen ophalen kan
  aanzienlijk langer duren. De eerste voorbereiding van een groot pakket kost tijd.
- Wegenpakketten bijwerken; doorgaan na sluiten is een afzonderlijke, standaard
  uitgeschakelde opt-in via Windows.
- Navigatieroutes exporteren naar GPX, TCX-koers en KML. Knoppen voor Komoot,
  Garmin en Strava slaan een GPX op en openen de importpagina; je uploadt zelf.
  De aparte Strava-activiteitsexport ondersteunt berekende tijden. Berekende
  tijden blijven schattingen en bewijzen geen werkelijk afgelegde activiteit.

De zes handleidingen zijn staand A4 en beschikbaar in Nederlands, Engels,
Duits, Frans, Spaans en Europees Portugees. Kies de taal via **Taal**.
Alleen gecontroleerde, synthetische demonstratiegegevens zijn meegeleverd.

## Gratis en privacybewust

Routebewerking en routeberekening gebeuren lokaal. RouteRefit bevat geen
telemetrie en vereist geen RouteRefit-account of betaald routeringsabonnement.
Het programma uploadt je persoonlijke GPX-bestanden, tijden of foto's niet
automatisch. De kaart- en wegendiensten ontvangen bij online aanvragen wel het
gevraagde gebied en verbindingsgegevens, zoals je IP-adres. Lokale verwerking
betekent dus geen anoniem internetgebruik. Zie [PRIVACY.md](PRIVACY.md).

De optionele bestaande websitecatalogus verwijst naar marcodelnoij.nl en is
in deze uitgave leeg. Er zijn geen persoonlijke routes of gedownloade kaarten
opgenomen. Export naar een externe dienst blijft een handeling van de gebruiker.

## Bouwen en bijdragen

Gebruik Python 3.13.12 op Windows en de vastgelegde afhankelijkheden:

```text
python -m pip install --require-hashes -r requirements-windows.lock
python release_tools.py check
python -m unittest discover -s tests -v
python build_windows.py
python release_tools.py package
./tools/install_inno.ps1
python build_installer.py --compiler build/inno/ISCC.exe
```

De workflow in `.github/workflows/windows.yml` voert ook interfacecontroles uit
en bewaart de Windows- en broncode-ZIP als bouwresultaat voor beoordeling.
Ook de installer wordt gebouwd en getest op installeren, opnieuw installeren,
verwijderen en behoud van synthetische gebruikersgegevens.
De workflow publiceert niet automatisch een release. Voer unit- en
interfacecontroles na elkaar uit; zij gebruiken tijdelijke testbestanden.
Het bouwproces controleert ook de uiteindelijke ZIP-inhoud op privégegevens.
De handleidingbron en generator staan in `docs/manuals` en `tools/build_manuals.py`;
de actuele PDF's zijn al meegeleverd. Zie [TESTEN.md](TESTEN.md),
[CONTRIBUTING.md](CONTRIBUTING.md) en [DEPENDENCIES.md](DEPENDENCIES.md).

## Code signing policy

Deze uitgave is **niet ondertekend** en heeft nog geen SignPath-toelating.
[Code signing policy](CODE-SIGNING-POLICY.md) beschrijft onderhoud, review,
handmatige goedkeuring en privacy. Zie [RELEASING.md](RELEASING.md) voor het
controleerbare bouw- en publicatieproces. Gratis ondertekening wordt pas na
daadwerkelijke toelating als voorziening vermeld.

## Licentie en kaartgegevens

Copyright © 2026 EOSfoto. Project van Marco Delnoij.
De broncode is uitgebracht onder **GNU GPL v3, uitsluitend versie 3**
(`GPL-3.0-only`); de volledige tekst staat in [LICENSE](LICENSE).
Licenties van gebruikte onderdelen staan in `THIRD-PARTY-NOTICES`.

Kaartgegevens: **© [OpenStreetMap-bijdragers](https://www.openstreetmap.org/copyright)**,
beschikbaar onder de Open Database License (ODbL). De OSM-kaartgegevens vallen
onder hun eigen licentie. Namen en logo's van externe diensten behoren aan hun
respectieve eigenaren; RouteRefit is niet aan die diensten verbonden.
