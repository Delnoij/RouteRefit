# SPDX-License-Identifier: GPL-3.0-only
"""Prepare a navigation GPX and hand off to the service's own browser import."""
from pathlib import Path
import json
from service_export import navigation_gpx
from gpx_core import Track,write_new

SERVICES={
    'Komoot':('komoot','https://www.komoot.com/upload',
              'Importeer als geplande route en kies het oorspronkelijke verloop behouden. Sla de route op voor navigatie.'),
    'Garmin':('garmin','https://connect.garmin.com/modern/courses',
              'Kies Importeren bij Koersen. Selecteer de GPX, sla de koers op en stuur deze naar je geschikte Garmin-toestel.'),
    'Strava':('strava','https://www.strava.com/maps/create',
              'Gebruik de uploadknop in de routeplanner, selecteer de GPX en sla de route op. Strava kan hiervoor een abonnement vereisen.'),
}

def write_navigation_export(filename,segments,activity,service):
    if service not in SERVICES:raise ValueError('Onbekende dienst.')
    path=Path(filename);report=path.with_suffix('.export.json')
    if path.exists() or report.exists():
        raise FileExistsError('Kies een nieuwe bestandsnaam. Bestaande bestanden worden nooit overschreven.')
    raw=navigation_gpx(segments)
    verified=Track(raw)
    assert all(p.time is None for s in verified.segments for p in s)
    write_new(path,raw)
    try:
        write_new(report,json.dumps(dict(format='navigation route',activity=activity,service=service,
                    times='omitted',uploaded=False,segments=len(segments)),ensure_ascii=False,indent=2).encode('utf-8'))
    except Exception:
        path.unlink()
        raise
    return path

def show_navigation_upload(app,service):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    import webbrowser
    from i18n import tr
    if app.busy or not app.require_track():return
    if app.candidate is not None and not app.approved.get():
        messagebox.showinfo('RouteRefit',tr('Neem het routevoorstel eerst over voordat je het voor navigatie exporteert.'),parent=app)
        return
    filename,url,instruction=SERVICES[service]
    window=tk.Toplevel(app);window.title(tr('Route naar')+' '+service);window.transient(app)
    frame=ttk.Frame(window,padding=18);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text=tr('Navigeren met deze route'),font=('Segoe UI',13,'bold')).pack(anchor='w')
    ttk.Label(frame,text=tr('Sla de GPX op en kies dit bestand daarna op de uploadpagina. De GPX bevat je routecoördinaten. Je logt in bij de dienst zelf; RouteRefit bewaart geen wachtwoorden en uploadt niets op de achtergrond.'),wraplength=560).pack(anchor='w',pady=10)
    ttk.Label(frame,text=tr(instruction),wraplength=560).pack(anchor='w',pady=6)
    if app.transport.get() in ('Auto','Motor'):
        ttk.Label(frame,text=tr('Voor auto en motor heb je een GPX-geschikte autonavigator nodig. Deze sportdiensten ondersteunen niet iedere activiteit of ieder toestel.'),wraplength=560).pack(anchor='w',pady=6)
    segments=[list(s) for s in (app.candidate or app.edit_segments)]
    key=app.settings_key();activity=app.transport.get()
    if len(segments)>1:
        ttk.Label(frame,text=tr('Deze route heeft losse delen. Verbind de opnamegaten eerst als je één doorlopende navigatieroute wilt.'),wraplength=560).pack(anchor='w',pady=6)
    state=tk.StringVar(value=tr('Navigatie-GPX: route en hoogtes, zonder activiteitstijden, foto’s of persoonlijke metadata.'))
    ttk.Label(frame,textvariable=state,wraplength=560).pack(anchor='w',pady=10)
    path_value=tk.StringVar();entry=ttk.Entry(frame,textvariable=path_value,state='readonly',width=75)
    entry.pack(fill='x')
    ready={'path':None}
    def open_page():
        if not ready['path']:return
        if not webbrowser.open(url):
            state.set(tr('De GPX is opgeslagen. Open de uploadpagina opnieuw met de knop hieronder.'))
        else:state.set(tr('Uploadpagina geopend. Selecteer daar het opgeslagen GPX-bestand; kies een route of koers voor navigatie.'))
    def copy_path():
        if ready['path']:
            app.clipboard_clear();app.clipboard_append(str(ready['path']))
    def save():
        if app.busy:return
        if key!=app.settings_key():
            messagebox.showinfo('RouteRefit',tr('Route of instellingen gewijzigd; open het uploadvenster opnieuw.'),parent=window)
            return
        selected=filedialog.asksaveasfilename(parent=window,defaultextension='.gpx',initialfile=f'RouteRefit-{service}-route.gpx',filetypes=[('GPX','*.gpx')])
        if not selected:return
        def done(path):
            if not window.winfo_exists():return
            ready['path']=path;path_value.set(str(path));open_button.config(state='normal');copy_button.config(state='normal')
            open_page()
        app.job(lambda:write_navigation_export(selected,segments,activity,service),done,tr('Navigatie-GPX opslaan…'))
    ttk.Button(frame,text=tr('GPX opslaan en uploadpagina openen'),style='Accent.TButton',command=save).pack(fill='x',pady=(12,4))
    open_button=ttk.Button(frame,text=tr('Uploadpagina opnieuw openen'),command=open_page,state='disabled');open_button.pack(fill='x',pady=4)
    copy_button=ttk.Button(frame,text=tr('Bestandspad kopiëren'),command=copy_path,state='disabled');copy_button.pack(fill='x',pady=4)
    window.grab_set()
    return window
