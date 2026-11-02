# SPDX-License-Identifier: GPL-3.0-only
"""Local navigation export. Never contacts a service or carries recording metadata."""
import math
import xml.etree.ElementTree as ET

SERVICES = {
    'Strava': 'https://support.strava.com/en-us/articles/15402061-how-do-i-create-a-route-from-a-gpx-file',
    'Garmin Connect': 'https://support.garmin.com/en-US/?faq=wKuZXCaZRP4mWPX5aRz5h5',
    'Komoot': 'https://support.komoot.com/hc/en-us/articles/10207999797530-Find-routes-and-inspiration-on-komoot',
    'Wikiloc': 'https://help.wikiloc.com/article/18-upload-trail-web',
}


def navigation_gpx(segments, include_times=False):
    root = ET.Element('gpx', version='1.1', creator='RouteRefit',
                      xmlns='http://www.topografix.com/GPX/1/1')
    track = ET.SubElement(root, 'trk')
    ET.SubElement(track, 'name').text = 'RouteRefit route'
    count = 0
    previous_time = None
    previous_point = None
    for segment in segments:
        if not segment:
            continue
        output = ET.SubElement(track, 'trkseg')
        for point in segment:
            if not (math.isfinite(point.lat) and math.isfinite(point.lon)
                    and -90 <= point.lat <= 90 and -180 <= point.lon <= 180):
                raise ValueError('Invalid route coordinates')
            node = ET.SubElement(output, 'trkpt', lat=str(point.lat), lon=str(point.lon))
            if point.ele is not None and math.isfinite(point.ele):
                ET.SubElement(node, 'ele').text = str(point.ele)
            if include_times:
                from datetime import timezone
                if point.time is None or point.time.tzinfo is None:
                    raise ValueError('Activity export requires UTC times on every point')
                current = point.time.astimezone(timezone.utc)
                from gpx_core import distance
                if previous_time is not None and (current < previous_time or (current == previous_time and distance(previous_point, point) > 0.05)):
                    raise ValueError('Activity timestamps must increase; check the time settings')
                ET.SubElement(node, 'time').text = current.isoformat().replace('+00:00', 'Z')
                previous_time = current
                previous_point = point
            count += 1
    if count < 2:
        raise ValueError('A route needs at least two points')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


# Kept together so the sharing flow is available in every application language.
TEXT = {
 'nl': ('Exporteren naar…', 'Lokaal GPX-bestand voor handmatige import. Zonder foto’s, waypoints of persoonlijke metadata; locaties blijven zichtbaar. Strava-activiteit bevat de aangepaste tijden. Navigatieroutes bevatten geen tijden. Bij een voorstel is eerst jouw beoordeling nodig.', '1. GPX lokaal opslaan', '2. Importuitleg openen', 'GPX opgeslagen. Importeer dit bestand als route, niet als opgenomen activiteit. Controleer bij de dienst wie je route kan zien.'),
 'en': ('Export to…', 'Local GPX file for manual import. No photos, waypoints or personal metadata; locations remain visible. Strava activities include adjusted times. Navigation routes omit times. Proposals require your review first.', '1. Save GPX locally', '2. Open import help', 'GPX saved. Import this file as a route, not a recorded activity. Check who can see your route in the service.'),
 'de': ('Exportieren nach…', 'Lokale GPX-Datei zum manuellen Import. Ohne Fotos, Wegpunkte oder persönliche Metadaten; Orte bleiben sichtbar. Strava-Aktivitäten enthalten angepasste Zeiten, Navigationsrouten keine Zeiten. Vorschläge erfordern Ihre Prüfung.', '1. GPX lokal speichern', '2. Importhilfe öffnen', 'GPX gespeichert. Als Route importieren, nicht als aufgezeichnete Aktivität. Prüfen Sie beim Dienst die Sichtbarkeit Ihrer Route.'),
 'fr': ('Exporter vers…', 'Fichier GPX local pour import manuel. Sans photos, points d’intérêt ni métadonnées personnelles ; les lieux restent visibles. Les activités Strava incluent les heures ajustées, les itinéraires les omettent. Vérifiez toute proposition avant l’export.', '1. Enregistrer le GPX localement', '2. Ouvrir l’aide à l’import', 'GPX enregistré. Importez ce fichier comme itinéraire, pas comme activité enregistrée. Vérifiez la visibilité de votre itinéraire sur le service.'),
 'es': ('Exportar a…', 'Archivo GPX local para importación manual. Sin fotos, puntos de interés ni metadatos personales; los lugares siguen visibles. Las actividades Strava incluyen tiempos ajustados; las rutas los omiten. Revisa las propuestas antes de exportar.', '1. Guardar GPX localmente', '2. Abrir ayuda de importación', 'GPX guardado. Importa el archivo como ruta, no como actividad grabada. Comprueba quién puede ver tu ruta en el servicio.'),
 'pt': ('Exportar para…', 'Ficheiro GPX local para importação manual. Sem fotos, pontos de interesse ou metadados pessoais; os locais continuam visíveis. Atividades Strava incluem tempos ajustados; rotas não incluem tempos. Reveja as propostas antes de exportar.', '1. Guardar GPX localmente', '2. Abrir ajuda de importação', 'GPX guardado. Importe o ficheiro como rota, não como atividade gravada. Verifique quem pode ver a rota no serviço.'),
}


def show_export(app):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from pathlib import Path
    import webbrowser
    import i18n
    from gpx_core import Track, write_new
    if app.busy or not app.require_track():
        return
    labels = TEXT[i18n.language]
    window = tk.Toplevel(app)
    window.title(labels[0])
    window.transient(app)
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    service = tk.StringVar(value='Strava')
    icons = []
    for name, filename in zip(SERVICES, ('strava', 'garmin', 'komoot', 'wikiloc')):
        icon = tk.PhotoImage(master=window, file=str(Path(__file__).parent/'assets'/(filename+'.png')))
        icons.append(icon)
        ttk.Radiobutton(frame, text=name, image=icon, compound='left', variable=service, value=name).pack(fill='x', pady=3)
    window._service_icons = icons
    ttk.Label(frame, text=labels[1], wraplength=520).pack(fill='x', pady=16)

    activity_text = {
        'nl': 'Strava-activiteit met aangepaste tijden (anders: navigatieroute zonder tijden)',
        'en': 'Strava activity with adjusted times (otherwise: navigation route without times)',
        'de': 'Strava-Aktivität mit angepassten Zeiten (sonst: Navigationsroute ohne Zeiten)',
        'fr': 'Activité Strava avec heures ajustées (sinon : itinéraire sans heures)',
        'es': 'Actividad Strava con tiempos ajustados (si no: ruta sin tiempos)',
        'pt': 'Atividade Strava com tempos ajustados (caso contrário: rota sem tempos)',
    }
    activity = tk.BooleanVar(value=True)
    ttk.Checkbutton(frame, text=activity_text[i18n.language], variable=activity).pack(fill='x', pady=4)

    def save():
        if app.busy:
            return
        include_times = service.get() == 'Strava' and activity.get()
        if app.candidate is not None and not app.approved.get():
            messagebox.showinfo('RouteRefit', i18n.tr('Controleer de lijnen, tijden en meldingen en vink de controle aan.'), parent=window)
            return
        segments = [list(s) for s in (app.candidate or app.edit_segments)]
        if include_times:
            from export_timing import timing_form
            timing_form(app, segments, lambda adjusted, report: store(adjusted, True, report))
        else:
            store(segments, False, {})

    def store(segments, include_times, timing_report):
        if app.busy:return
        filename = filedialog.asksaveasfilename(parent=app, defaultextension='.gpx',
                         initialfile='RouteRefit-activity.gpx' if include_times else 'RouteRefit-route.gpx', filetypes=[('GPX', '*.gpx')])
        if not filename:return
        def work():
            raw = navigation_gpx(segments, include_times)
            Track(raw)
            import json
            path = Path(filename)
            report = path.with_suffix('.export.json')
            if path.exists() or report.exists():
                raise FileExistsError(i18n.tr('Kies een nieuwe bestandsnaam. Bestaande bestanden worden nooit overschreven.'))
            write_new(path, raw)
            write_new(report, json.dumps({'format': 'Strava activity' if include_times else 'navigation route',
                      'times': 'modeled adjusted times' if include_times else 'omitted',
                      'timing_settings': timing_report, 'uploaded': False}, indent=2).encode('utf-8'))
            return filename
        def done(path):
            messagebox.showinfo(labels[0], (activity_text[i18n.language] if include_times else labels[4]) + '\n\n' + path, parent=app)
        app.job(work, done, labels[2])
    ttk.Button(frame, text=labels[2], command=save).pack(fill='x', pady=4)
    ttk.Button(frame, text=labels[3], command=lambda: webbrowser.open('https://www.strava.com/upload/select' if service.get() == 'Strava' and activity.get() else SERVICES[service.get()])).pack(fill='x', pady=4)
