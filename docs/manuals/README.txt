Current manuals: guidebook.json (33 chapters per language) and guide_meta.json.
Real, visually reviewed screenshots: screens/0.5.5/{nl,en,de,fr,es,pt}/*.jpg.
All screenshots use only the synthetic demonstration in examples/handleiding.
The visible demonstration map is not a bundled usable road index.

Regenerate with python tools/build_manuals.py using ReportLab, Pillow and Windows
Segoe UI. Authoring tools are not required to run the Windows application.
PDFs are written to Handleidingen. Render every page and check content and layout.
Then update only the reviewed document hashes in release-data-manifest.json.
Never approve images from a used personal installation without content review.
