# RouteRefit: stand van zaken bij 0.5.15 Bèta

Nieuw: Exporteer naar > Bestand… biedt GPX, TCX en KML. TCX is een koers
met bestaande of zelf ingestelde routetijden. GPX/KML bevatten geen tijden.
Export blijft lokaal; bestaande bestanden worden nooit overschreven.

## Beschikbaar

- Lokale Windows-editor met zes talen, OSM-kaart, grote kaart,
  hoogteprofiel/statistieken en handmatige import/mapcontrole.
- Automatisch en handmatig uitlijnen, hoofdpunten verplaatsen/verwijderen,
  plaatselijke herstelvoorstellen, rechtermuisknopbediening en ongedaan maken.
- Voorstellen eerst beoordelen; na overnemen direct handmatig verderwerken.
- Routedelen verbinden, start/eind verplaatsen, pauzes en tijdschema aanpassen,
  waypoints met naam, omschrijving en foto; GPX met controlerapport bewaren.
- Activiteiten: Lopen, Fiets, MTB, Gravelfiets, Auto en Motor. Toegang, richting
  en ondersteunde OSM-afslagrelaties zijn afzonderlijke controles.
- Lokale wegenindex, alleen ontbrekende gebieden ophalen, begrensde downloads,
  lokaal voorstel vóór de afzonderlijke achtergrondaanvraag.
- Meerdere optionele regio's en eigen getekende gebieden, compacte verwerking,
  regionale wijzigingsupdates en achtergrondwerk na expliciete Windows-opt-in.
- Verwerking houdt rekening met andere Windows-belasting. Geen beloofde
  constante rekentijd of volledige benutting van alle processorkernen.
- GPX-export voor Komoot, Garmin, Strava en Wikiloc; drie compacte logoknoppen
  openen officiële importpagina's. Upload bevestigt de gebruiker bij de dienst.
- Activiteitsexport met berekende tijden, datumkalender en tijdkiezer.
- Zes uitgebreide handleidingen; GPL-3.0-only en OSM-vermelding in Over RouteRefit.

## Nog open of gedeeltelijk

1. Routevoorkeuren **kortste** en **snelste**, naast het bestaande **meest logisch**.
2. Alternatieven met **minste stijging**, **mooiste** en **rustigste** route.
3. Geschikte en toegestane heatmapgegevens onderzoeken; geen gerealiseerde
   Garmin- of Strava-heatmapkoppeling of toezegging over beschikbaarheid.
4. **Nieuwe route** vanaf een lege kaart met klikpunten. Het ontwerp staat in
   docs/ONTWERP-ROUTES-CREEREN.md; er is nog geen actieve routeplanner.
5. Afzonderlijke bestanden **samenvoegen** en **splitsen** naar aparte bestanden.
   Routedelen binnen de geopende route verbinden is al beschikbaar.
6. Europese landelijke standaardregels en conditionele toegang vollediger
   verwerken. De huidige generieke OSM-regels zijn geen volledige landenregelset.
7. Eigen getekende gebieden automatisch en met kleine verschillen vernieuwen.
   Deze gebruiken nu handmatige volledige vernieuwing; regiopakketten ondersteunen
   al periodieke wijzigingsupdates.
8. Rechtstreekse accountuploads zijn niet gerealiseerd. De bestaande knoppen
   maken een GPX en openen de dienst; toestelcompatibiliteit en overname van
   berekende tijden door diensten moeten verder in de praktijk worden getest.
9. Websitekoppeling: handmatig exporteren/importeren bestaat; een geïntegreerde
   automatische upload met controledatum en bijgewerkte statistieken ontbreekt.
10. Verder meten en finetunen van routekwaliteit en snelheid. GraphHopper is een
    vergelijkingspunt, geen verplichte betaalde dienst of bewezen kwaliteitsclaim.

Een automatisch lokaal herstelconcept is eerder voorgesteld, maar niet gebouwd.
Handmatig een concept bewaren en bewerkingen heropenen zijn wel beschikbaar.
Instelbare MTB-terreinmoeilijkheid was eveneens een voorstel; er is nog geen
aparte bediening voor een terreinmoeilijkheidsniveau.

## Gewijzigde of uitgestelde keuzes

- **Speedpedelec vervalt** op uitdrukkelijk verzoek; niet meer als komende functie
  presenteren. Het eerdere uitsluitend Nederlandse profiel is achterhaald.
- Publicatie op GitHub en een SignPath-aanvraag blijven uitgesteld tot eigen
  praktijktests en een afzonderlijk besluit van de eigenaar.
- Publieke pakketten blijven vrij van persoonlijke routes, kaarten en instellingen.
- Oudere installaties behouden tijdens praktijktests; opschonen is een aparte actie.
- Versie 1.0 volgt pas na voldoende praktijktests.
