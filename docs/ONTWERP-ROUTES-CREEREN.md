# Voorbereiding: zelf routes creëren

Status: ontwerp, nog geen aangeboden programmamogelijkheid. Eerst deze taal-,
handleiding- en voortgangsversie praktisch testen. Daarna de vervoermiddelen
uitbreiden en valideren. Routecreatie volgt als afzonderlijke volgende stap.

## Bediening

Een toekomstige knop **Nieuwe route** opent een leeg ontwerp. De gebruiker kiest
vervoermiddel en routevoorkeur, klikt begin, tussenpunten en einde op de kaart en
krijgt een berekend voorstel. Afstand, geschatte tijd en beschikbare stijging staan
vóór **Voorstel overnemen** in beeld. Klikpunten blijven versleepbaar; verwijderen
vervangt de hele verbinding tot de aangrenzende overblijvende klikpunten.
Ongedaan maken, annuleren, waypoints, foto's en GPX-export worden hergebruikt.

## Onderdelen die we kunnen hergebruiken

- De lokale wegenindex en ontbrekende gebiedsdekking uit `road_provider.py`.
- De per-profiel voorbereide netwerken en toegang/richting uit `prepared_roads.py`.
- Profielinstellingen los van het tijdschema; toekomstige voertuigen krijgen eigen
  geteste regels vóór zij voor plannen beschikbaar komen.
- Voorstelcontrole, afstands-/hoogtesamenvatting, kaart en bewerkingsgeschiedenis.
- GPX/rapport-export en de bestaande controles op schattingen en fotobijlagen.

## Vereiste scheiding in het gegevensmodel

Een opgenomen route behoudt een onveranderlijke bron. Een ontwerp krijgt de
expliciete herkomst `planned`, een lijst besturingspunten en een afzonderlijk
voorstel. Er wordt geen fictieve oorspronkelijke GPS-opname gemaakt. Gemeten
tijden, werkelijk afgelegde afstand en opgenomen pauzes blijven onbekend.
Een tijdschema is alleen een berekende schatting op basis van de gekozen snelheid
en een eventueel gekozen starttijd. In GPX en rapport blijft die herkomst zichtbaar.

De huidige uitlijner volgt een bestaande routevorm en beperkt afwijking daarvan.
Een planner moet verbindingen tussen nieuwe klikpunten zoeken. Die twee intenties
krijgen afzonderlijke zoekopdrachten boven hetzelfde lokale wegennet, zodat
nieuwe planning de huidige herstelkeuze niet ongemerkt wijzigt. De planner moet
ook melden wanneer lokale gebiedsdekking ontbreekt en die gericht uitbreiden.

## Vooraf te beslissen en te testen

1. Begin/einde op bereikbare wegen projecteren, met een controleerbaar voorstel.
2. Gebiedsdekking stapsgewijs vergroten bij een omweg buiten het eerste gebied;
   grenzen aan rekentijd en downloaden behouden.
3. Alle toegevoegde vervoermiddelen afzonderlijk testen op toegang, richting,
   afslagbeperkingen en parallelle paden.
4. Ontwerpen heropenen zonder ze als opgenomen activiteit aan te merken.
5. Verwijderen/verplaatsen van een klikpunt, expliciete voorstelovername,
   annuleren, ongedaan maken en geschatte tijden samen controleren.
6. Hoogtebronnen later afzonderlijk aansluiten. Zonder hoogtegegevens blijft de
   stijging onbekend; getallen worden niet verzonnen.

Er komen in deze uitgave geen lege planningsknoppen. Samenvoegen en splitsen van
afzonderlijke bestanden blijven aparte toekomstige uitbreidingen. Publicatie en
SignPath-aanvraag blijven uitgesteld tot de eigenaar daarvoor kiest.
