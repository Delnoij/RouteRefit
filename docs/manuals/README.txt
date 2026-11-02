Huidige handleidingen: guidebook.json (33 hoofdstukken per taal) en guide_meta.json.
Echte, visueel gecontroleerde schermafdrukken: screens/0.5.5/{nl,en,de,fr,es,pt}/*.jpg.
Alle beelden gebruiken uitsluitend de synthetische demonstratieroute uit examples/handleiding.
De demonstratiekaart is zichtbaar; deze is geen meegeleverde bruikbare wegenindex.

Opnieuw maken: python tools/build_manuals.py, met ReportLab, Pillow en Windows Segoe UI.
Auteursgereedschappen zijn niet nodig voor het Windows-programma.
De PDF's komen in Handleidingen. Render alle pagina's en controleer inhoud en beeld.
Update daarna alleen de goedgekeurde documentchecksums in release-data-manifest.json.
Nooit beelden uit een persoonlijke, gebruikte installatie goedkeuren zonder inhoudscontrole.

