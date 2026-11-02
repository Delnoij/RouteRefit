# SPDX-License-Identifier: GPL-3.0-only
"""Local export timing form and terrain-weighted average-speed model."""
import math
from datetime import datetime, timezone
from gpx_core import distance, modeled_times, duration
from profile_settings import DEFAULT_PRESET, TIME_PRESETS


def prepare_activity(segments, transport, average, start):
    limits = {'Lopen': (0.5, 12), 'Fiets': (3, 60), 'MTB': (3, 40),
              'Gravelfiets': (3,60), 'Auto': (1,160), 'Motor': (1,160)}
    low, high = limits[transport]
    if not math.isfinite(average) or not low <= average <= high:
        raise ValueError(f'{low}–{high} km/u')
    if start.tzinfo is None:
        raise ValueError('Start time requires a time zone')
    metres = sum(distance(a,b) for s in segments for a,b in zip(s,s[1:]))
    seconds = metres / (average / 3.6)
    profile = TIME_PRESETS[transport][DEFAULT_PRESET[transport]]
    adjusted = modeled_times(segments, profile, average, start.astimezone(timezone.utc), seconds)
    return adjusted, {'activity':transport,'transport': transport, 'average_kmh': average, 'distance_km': metres/1000,
                      'duration_seconds': seconds, 'start': start.isoformat(),
                      'method': 'terrain-weighted modeled times normalized to requested average',
                      'estimated': True}


LABELS = {
 'nl': ('Activiteit instellen', 'Datum (JJJJ-MM-DD)', 'Starttijd (UU:MM, lokale Windows-tijd)', 'Activiteit', 'Gemiddelde snelheid (km/u)', 'Tijden zijn schattingen op basis van activiteit en beschikbare hoogtes. Voor lopen en fietsen zijn volledige hoogtes vereist. Verkeer, snelheidslimieten, wind en pauzes worden niet gemodelleerd.', 'Deze berekende tijden gebruiken?', 'maandag dinsdag woensdag donderdag vrijdag zaterdag zondag'),
 'en': ('Activity settings', 'Date (YYYY-MM-DD)', 'Start (HH:MM, local Windows time)', 'Activity', 'Average speed (km/h)', 'Times are estimates based on activity and available elevations. Walking and cycling require complete elevations. Traffic, speed limits, wind and stops are not modeled.', 'Use these modeled times?', 'Monday Tuesday Wednesday Thursday Friday Saturday Sunday'),
 'de': ('Aktivität einstellen', 'Datum (JJJJ-MM-TT)', 'Start (HH:MM, lokale Windows-Zeit)', 'Aktivität', 'Durchschnitt (km/h)', 'Zeiten sind Schätzungen anhand der Aktivität und vorhandener Höhen. Gehen und Radfahren benötigen vollständige Höhen. Verkehr, Tempolimits, Wind und Pausen werden nicht modelliert.', 'Diese berechneten Zeiten verwenden?', 'Montag Dienstag Mittwoch Donnerstag Freitag Samstag Sonntag'),
 'fr': ('Paramètres de l’activité', 'Date (AAAA-MM-JJ)', 'Départ (HH:MM, heure locale Windows)', 'Activité', 'Vitesse moyenne (km/h)', 'Les horaires sont estimés selon l’activité et les altitudes disponibles. Marche et vélo exigent des altitudes complètes. Circulation, limites de vitesse, vent et pauses ne sont pas modélisés.', 'Utiliser ces heures calculées ?', 'lundi mardi mercredi jeudi vendredi samedi dimanche'),
 'es': ('Configurar actividad', 'Fecha (AAAA-MM-DD)', 'Inicio (HH:MM, hora local de Windows)', 'Actividad', 'Velocidad media (km/h)', 'Los tiempos se estiman según la actividad y las altitudes disponibles. Caminar y pedalear requieren altitudes completas. No se modelan tráfico, límites de velocidad, viento ni pausas.', '¿Usar estos tiempos calculados?', 'lunes martes miércoles jueves viernes sábado domingo'),
 'pt': ('Configurar atividade', 'Data (AAAA-MM-DD)', 'Início (HH:MM, hora local do Windows)', 'Atividade', 'Velocidade média (km/h)', 'Os tempos são estimados pela atividade e altitudes disponíveis. Caminhada e ciclismo exigem altitudes completas. Trânsito, limites de velocidade, vento e pausas não são modelados.', 'Usar estes tempos calculados?', 'segunda-feira terça-feira quarta-feira quinta-feira sexta-feira sábado domingo'),
}


def timing_form(app, segments, callback):
    import tkinter as tk
    from tkinter import ttk, messagebox
    import i18n
    from date_time_picker import CalendarPicker, TimePicker
    labels = LABELS[i18n.language]
    win = tk.Toplevel(app);win.title(labels[0]);win.transient(app)
    frame = ttk.Frame(win, padding=18);frame.pack(fill='both', expand=True)
    first = segments[0][0].time
    local = first.astimezone() if first else datetime.now().astimezone()
    date = tk.StringVar(value=local.strftime('%Y-%m-%d'))
    clock = tk.StringVar(value=local.strftime('%H:%M'))
    transport = tk.StringVar(value=app.transport.get())
    average = tk.StringVar(value=app.flat.get())
    day = tk.StringVar()
    for label, variable in zip(labels[1:5], (date,clock,transport,average)):
        ttk.Label(frame,text=label).pack(anchor='w',pady=(8,2))
        if variable is transport:
            # Display translations while preserving stable transport keys.
            names = {i18n.tr(k):k for k in DEFAULT_PRESET}
            transport.set(i18n.tr(transport.get()))
            ttk.Combobox(frame,textvariable=transport,values=list(names),state='readonly').pack(fill='x')
        elif variable is date:
            CalendarPicker(frame,date,i18n.language).pack(fill='x')
        elif variable is clock:
            TimePicker(frame,clock).pack(anchor='w')
        else:
            ttk.Entry(frame,textvariable=variable).pack(fill='x')
        if variable is date:
            ttk.Label(frame,textvariable=day).pack(anchor='w')
    def weekday(*args):
        try:day.set(labels[7].split()[datetime.strptime(date.get(),'%Y-%m-%d').weekday()])
        except ValueError:day.set('—')
    date.trace_add('write',weekday);weekday()
    ttk.Label(frame,text=labels[5],wraplength=500).pack(fill='x',pady=12)
    def calculate():
        if app.busy:return
        try:
            start = datetime.strptime(date.get()+' '+clock.get(),'%Y-%m-%d %H:%M').astimezone()
            speed = float(average.get().replace(',','.'))
            mode = names[transport.get()]
        except (ValueError,KeyError) as exc:
            messagebox.showerror(labels[0],str(exc),parent=win);return
        def done(result):
            adjusted, report = result
            text = f"{labels[7].split()[start.weekday()]} {start:%Y-%m-%d %H:%M %z}\n{report['distance_km']:.2f} km · {speed:g} km/h · {duration(report['duration_seconds'])}\n\n{labels[6]}"
            if messagebox.askyesno(labels[0],text,parent=app):
                if win.winfo_exists():win.destroy()
                callback(adjusted, report)
        app.job(lambda:prepare_activity(segments,mode,speed,start),done,labels[0])
    ttk.Button(frame,text=labels[6],command=calculate).pack(fill='x',pady=8)
    return win
