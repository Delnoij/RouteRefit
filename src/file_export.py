# SPDX-License-Identifier: GPL-3.0-only
"""Local navigation files; never uploads or changes the editable route."""
from datetime import timezone
from pathlib import Path
from xml.etree import ElementTree as ET
import json
import math

from gpx_core import distance
from service_export import navigation_gpx

FORMATS = ('GPX', 'TCX', 'KML')
TCX_NS = 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'
KML_NS = 'http://www.opengis.net/kml/2.2'


def usable_times(segments):
    previous = None
    count = 0
    for segment in segments:
        for point in segment:
            if point.time is None or point.time.tzinfo is None or point.time.utcoffset() is None:
                return False
            current = point.time.astimezone(timezone.utc)
            if previous and (current < previous.time or
                             (current == previous.time and distance(previous, point) > 0.05)):
                return False
            previous = point
            count += 1
    return count >= 2


def navigation_file(segments, file_format):
    """TCX Courses use supplied times; GPX/KML deliberately omit them."""
    if file_format not in FORMATS:
        raise ValueError('Onbekend exportformaat.')
    rows = [list(s) for s in segments if s]
    if sum(map(len, rows)) < 2:
        raise ValueError('Een route heeft minstens twee punten nodig.')
    for segment in rows:
        for p in segment:
            if not (math.isfinite(p.lat) and math.isfinite(p.lon)
                    and -90 <= p.lat <= 90 and -180 <= p.lon <= 180):
                raise ValueError('Ongeldige routecoördinaten.')
    if file_format == 'GPX':
        return navigation_gpx(rows)
    if file_format == 'TCX':
        if not usable_times(rows):
            raise ValueError('TCX vereist oplopende tijden. Stel eerst datum en snelheid in.')
        root = ET.Element('TrainingCenterDatabase', xmlns=TCX_NS)
        course = ET.SubElement(ET.SubElement(root, 'Courses'), 'Course')
        ET.SubElement(course, 'Name').text = 'RouteRefit'
        metres = 0.0
        for segment in rows:
            track = ET.SubElement(course, 'Track')
            previous = None
            for p in segment:
                if previous is not None:
                    metres += distance(previous, p)
                node = ET.SubElement(track, 'Trackpoint')
                ET.SubElement(node, 'Time').text = p.time.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
                pos = ET.SubElement(node, 'Position')
                ET.SubElement(pos, 'LatitudeDegrees').text = str(p.lat)
                # Garmin's longitude range excludes +180; -180 is the same meridian.
                ET.SubElement(pos, 'LongitudeDegrees').text = str(-180.0 if p.lon == 180 else p.lon)
                if p.ele is not None and math.isfinite(p.ele):
                    ET.SubElement(node, 'AltitudeMeters').text = str(p.ele)
                ET.SubElement(node, 'DistanceMeters').text = f'{metres:.3f}'
                previous = p
        ET.SubElement(course, 'Notes').text = 'Navigation course from RouteRefit. Times are a route schedule, not proof of a recorded activity.'
    else:
        if any(len(s) < 2 for s in rows):
            raise ValueError('KML vereist minstens twee punten per routedeel. Kies GPX of TCX voor losse punten.')
        root = ET.Element('kml', xmlns=KML_NS)
        document = ET.SubElement(root, 'Document')
        ET.SubElement(document, 'name').text = 'RouteRefit'
        for index, segment in enumerate(rows, 1):
            placemark = ET.SubElement(document, 'Placemark')
            ET.SubElement(placemark, 'name').text = f'RouteRefit {index}'
            line = ET.SubElement(placemark, 'LineString')
            # Ground-following display avoids floating route lines. Available
            # elevations remain in the coordinates for import into other tools.
            ET.SubElement(line, 'tessellate').text = '1'
            ET.SubElement(line, 'altitudeMode').text = 'clampToGround'
            ET.SubElement(line, 'coordinates').text = ' '.join(
                f'{p.lon},{p.lat}' + (f',{p.ele}' if p.ele is not None and math.isfinite(p.ele) else '')
                for p in segment)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def write_file_export(filename, segments, activity, file_format, timing_report=None):
    path = Path(filename)
    if file_format not in FORMATS or path.suffix.lower() != '.' + file_format.lower():
        raise ValueError('De bestandsextensie moet overeenkomen met het gekozen formaat.')
    # Include the extension so route.gpx, route.tcx and route.kml can coexist.
    report = path.with_name(path.name + '.export.json')
    if path.exists() or report.exists():
        raise FileExistsError('Kies een nieuwe bestandsnaam. Bestaande bestanden worden nooit overschreven.')
    raw = navigation_file(segments, file_format)
    info = dict(format=file_format, purpose='navigation course' if file_format == 'TCX' else 'navigation route',
                activity=activity, times='route schedule' if file_format == 'TCX' else 'omitted',
                uploaded=False, segments=sum(bool(s) for s in segments))
    if timing_report:
        info['timing'] = timing_report
    created = []
    try:
        for target, data in ((path, raw), (report, json.dumps(info, ensure_ascii=False, indent=2).encode('utf-8'))):
            with target.open('xb') as stream:
                created.append(target)
                stream.write(data)
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return path


def show_file_export(app):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from i18n import tr
    from export_timing import timing_form
    if app.busy or not app.require_track():
        return
    if app.candidate is not None and not app.approved.get():
        messagebox.showinfo('RouteRefit', tr('Neem het routevoorstel eerst over voordat je het voor navigatie exporteert.'), parent=app)
        return
    # Snapshot values (including times), not mutable Point objects from the editor.
    from gpx_core import Point
    segments = [[Point(p.lat, p.lon, p.ele, p.time) for p in s]
                for s in (app.candidate if app.candidate is not None else app.edit_segments) if s]
    key = app.settings_key()
    activity = app.transport.get()
    window = tk.Toplevel(app)
    window.title(tr('Routebestand exporteren…')); window.transient(app)
    frame = ttk.Frame(window, padding=18); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text=tr('Kies een bestandsformaat'), font=('Segoe UI', 13, 'bold')).pack(anchor='w')
    selected = tk.StringVar(value='GPX')
    retime = tk.BooleanVar(value=False)
    for kind, label in zip(FORMATS, ('GPX — route voor navigatie', 'TCX — koers met routetijden', 'KML — route voor kaartprogramma’s')):
        ttk.Radiobutton(frame, text=tr(label), variable=selected, value=kind).pack(anchor='w', pady=5)
    ttk.Label(frame, text=tr('TCX gebruikt de bestaande routetijden. Ontbreken bruikbare tijden, dan opent de kalender met tijd- en snelheidskeuze. GPX en KML bevatten geen tijden.'), wraplength=540).pack(anchor='w', pady=10)
    time_button = ttk.Checkbutton(frame, text=tr('Datum en snelheid voor TCX instellen'), variable=retime, state='disabled')
    time_button.pack(anchor='w')
    selected.trace_add('write', lambda *args: time_button.configure(state='normal' if selected.get() == 'TCX' else 'disabled'))
    ttk.Label(frame, text=tr('Alleen routepunten en beschikbare hoogtes worden geëxporteerd; TCX bevat ook routetijden. Geen foto’s, waypoints of persoonlijke metadata. Locaties blijven zichtbaar. Alles wordt lokaal opgeslagen.'), wraplength=540).pack(anchor='w', pady=10)
    if len(segments) > 1:
        ttk.Label(frame, text=tr('Losse routedelen blijven gescheiden in het bestand. Controleer na import of je navigatieprogramma ze ook gescheiden houdt.'), wraplength=540).pack(anchor='w', pady=6)
    state = tk.StringVar()
    ttk.Label(frame, textvariable=state, wraplength=540).pack(anchor='w', pady=6)
    output_path = tk.StringVar()
    ttk.Entry(frame, textvariable=output_path, state='readonly', width=70).pack(fill='x')

    def current():
        if not window.winfo_exists() or app.busy:
            return False
        if key != app.settings_key():
            messagebox.showinfo('RouteRefit', tr('Route of instellingen gewijzigd; open het exportvenster opnieuw.'), parent=window)
            return False
        return True

    def store(rows, kind, timing=None):
        if not current():
            return
        window.grab_set()
        suffix = '.' + kind.lower()
        filename = filedialog.asksaveasfilename(parent=window, defaultextension=suffix,
                    initialfile='RouteRefit-route' + suffix, filetypes=[(kind, '*' + suffix)])
        if not filename or not current():
            return
        def done(path):
            if window.winfo_exists():
                output_path.set(str(path))
                state.set(tr('Bestand opgeslagen. Importeer het als route of koers in een geschikt programma.'))
        app.job(lambda: write_file_export(filename, rows, timing.get('activity', activity) if timing else activity, kind, timing),
                done, tr('Routebestand opslaan…'))

    def save():
        if not current():
            return
        kind = selected.get()
        if kind == 'TCX' and (retime.get() or not usable_times(segments)):
            window.grab_release()
            timing_window = timing_form(app, segments, lambda rows, timing: store(rows, kind, timing))
            timing_window.transient(window)
            timing_window.grab_set()
            def restore_grab(event):
                if event.widget is timing_window and window.winfo_exists():
                    window.grab_set()
            timing_window.bind('<Destroy>', restore_grab, add='+')
        else:
            store(segments, kind)
    ttk.Button(frame, text=tr('Bestand opslaan…'), style='Accent.TButton', command=save).pack(fill='x', pady=(12, 4))
    ttk.Button(frame, text=tr('Sluiten'), command=window.destroy).pack(fill='x', pady=4)
    window.grab_set()
    return window
