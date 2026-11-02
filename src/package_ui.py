# SPDX-License-Identifier: GPL-3.0-only
"""Non-modal optional package manager. All Tk work stays on the main thread."""
from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from fluent_progress import FluentProgress
from i18n import DisplayVar,tr
from package_index import PackageCancelled
from region_packages import catalog,installed,preferences,set_weekly,due_packages,install_or_update,custom_regions,save_custom

INTRO='Gebiedspakketten zijn optioneel. Zonder pakket werkt RouteRefit ook, maar ontbrekende wegen ophalen kan het uitlijnen veel langer laten duren. Opgeslagen wegen worden altijd hergebruikt.'
PRIVACY='Gratis, zonder account. Geofabrik ontvangt je IP-adres en het gekozen gebied; je route wordt niet verstuurd. De eerste download en voorbereiding kunnen enkele minuten duren. Kies bij voorkeur een provincie (maximaal 500 MB download).'


class PackageUI:
    def __init__(self,app,folder):
        self.app,self.folder=app,folder
        self.window=None;self.running=False;self.cancel=threading.Event();self.events=queue.Queue()
        self.message=DisplayVar(app,value='Geen gebiedstaak actief.')
        self.percent=tk.DoubleVar(app,value=0)
        self.regions=catalog()+custom_regions(folder);self.next_check=time.monotonic()+30
        self.last_progress='';self.started=0
        self.selected_ids=set();self.refreshing=False
        self.external_job=None;self.external_progress=None;self.changing_background=False
        self.external_check=time.monotonic()+30
        from package_background import settings,pending,launch
        if settings(folder).get('enabled'):
            jobs=pending(folder)
            if jobs:
                self.external_job=jobs[0]['id'];self.running=True;self.started=time.monotonic()
            launch(folder)
        self.app.after(200,self.poll)

    def show(self):
        if self.window and self.window.winfo_exists():self.window.lift();return
        w=tk.Toplevel(self.app);self.window=w;w.title(tr('Gebiedspakketten'))
        w.transient(self.app);w.geometry('960x680');w.minsize(760,620)
        body=ttk.Frame(w,padding=18);body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1);body.rowconfigure(4,weight=1)
        ttk.Label(body,text='Sneller uitlijnen met opgeslagen gebieden',font=('Segoe UI',15,'bold')).grid(row=0,column=0,sticky='w')
        ttk.Label(body,text=INTRO,wraplength=790).grid(row=1,column=0,sticky='ew',pady=(8,6))
        ttk.Label(body,text=PRIVACY,wraplength=790,style='Muted.TLabel').grid(row=2,column=0,sticky='ew',pady=(0,10))
        search=ttk.Frame(body);search.grid(row=3,column=0,sticky='ew')
        ttk.Label(search,text='Zoek gebied:').pack(side='left')
        self.filter=tk.StringVar(w);entry=ttk.Entry(search,textvariable=self.filter);entry.pack(side='left',fill='x',expand=True,padx=8)
        self.only_installed=tk.BooleanVar(w,value=False)
        ttk.Checkbutton(search,text='Alleen gedownload',variable=self.only_installed,command=self.refresh).pack(side='left')
        frame=ttk.Frame(body);frame.grid(row=4,column=0,sticky='nsew',pady=10)
        self.tree=ttk.Treeview(frame,columns=('parent','date'),show='tree headings',selectmode='extended',height=10)
        self.tree.heading('#0',text=tr('Gebied'));self.tree.heading('parent',text=tr('Land / regio'));self.tree.heading('date',text=tr('Lokaal beschikbaar'))
        self.tree.column('#0',width=270);self.tree.column('parent',width=220);self.tree.column('date',width=180)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',lambda event:self.remember_selection())
        self.filter.trace_add('write',lambda *a:self.refresh())
        self.weekly=tk.BooleanVar(w,value=preferences(self.folder).get('weekly',True))
        choices=ttk.Frame(body);choices.grid(row=7,column=0,sticky='ew')
        ttk.Checkbutton(choices,text='Gedownloade gebieden wekelijks op de achtergrond bijwerken',variable=self.weekly,
                        command=lambda:set_weekly(self.folder,self.weekly.get())).pack(anchor='w')
        from package_background import settings
        self.background=tk.BooleanVar(w,value=settings(self.folder).get('enabled',False))
        self.background_check=ttk.Checkbutton(choices,text='Doorgaan als RouteRefit gesloten is (Windows-achtergrondtaak)',variable=self.background,
                                             command=self.toggle_background)
        self.background_check.pack(anchor='w')
        ttk.Label(body,text='Geofabrik: kleine automatische updates. Eigen gebieden: handmatig opnieuw ophalen. Je route of voorstel verandert niet vanzelf.',style='Muted.TLabel').grid(row=8,column=0,sticky='ew',pady=(2,8))
        buttons=ttk.Frame(body);buttons.grid(row=9,column=0,sticky='ew')
        self.actions=[]
        for label,command in [('Downloaden / bijwerken',lambda:self.selected()),('Opnieuw downloaden',lambda:self.selected(full=True))]:
            b=ttk.Button(buttons,text=label,command=command);b.pack(side='left',padx=(0,6));self.actions.append(b)
        self.stop=ttk.Button(buttons,text='Stoppen',command=self.stop_job);self.stop.pack(side='left')
        ttk.Button(buttons,text='Sluiten',command=w.destroy).pack(side='right')
        ttk.Label(body,textvariable=self.message,wraplength=790).grid(row=10,column=0,sticky='ew',pady=(10,4))
        self.bar=ttk.Progressbar(body,variable=self.percent,maximum=100);self.bar.grid(row=11,column=0,sticky='ew')
        self.spinner=FluentProgress(body,length=100);self.spinner.grid(row=12,column=0,sticky='ew',pady=(3,0))
        ttk.Label(body,text='Weggegevens: © OpenStreetMap-bijdragers (ODbL). Pakketten: Geofabrik / SliceOSM.',style='Muted.TLabel').grid(row=13,column=0,sticky='w',pady=(6,0))
        self.selection_status=DisplayVar(w)
        selection=ttk.Frame(body);selection.grid(row=5,column=0,sticky='ew',pady=(4,0))
        ttk.Label(selection,textvariable=self.selection_status).pack(side='left')
        draw=ttk.Button(selection,text='Eigen gebied tekenen…',command=self.draw_area)
        draw.pack(side='left',padx=12);self.actions.append(draw)
        ttk.Button(selection,text='Selectie wissen',command=self.clear_selection).pack(side='right')
        ttk.Label(body,text='Ctrl/Shift: meerdere gebieden kiezen. Je selectie blijft bewaard tijdens zoeken.',style='Muted.TLabel').grid(row=6,column=0,sticky='w',pady=(0,8))
        def wrap(event):
            for child in body.winfo_children():
                if isinstance(child,ttk.Label):child.configure(wraplength=max(300,event.width-40))
        body.bind('<Configure>',wrap)
        self.refresh();self.controls();entry.focus_set()

    def draw_area(self):
        from area_ui import AreaDialog
        self.area_dialog=AreaDialog(self)

    def toggle_background(self):
        from package_background import settings,configure
        enabled=self.background.get();before=settings(self.folder).get('enabled',False)
        if self.changing_background or enabled and self.running:
            self.background.set(before);self.message.set('Wacht tot de huidige gebiedstaak klaar is om achtergrondwerk in te schakelen.');return
        self.changing_background=True;self.background_check.configure(state='disabled')
        self.message.set('Windows-achtergrondoptie wijzigen…')
        def worker():
            try:configure(self.folder,enabled);self.events.put(('background',None))
            except Exception as exc:self.events.put(('background',str(exc) if isinstance(exc,ValueError) else 'Windows kon de achtergrondoptie niet wijzigen.'))
        threading.Thread(target=worker,daemon=True,name='background-preference').start()

    def add_custom(self,region):
        save_custom(self.folder,region);self.regions.append(region)
        self.tree.selection_remove(*self.tree.selection())
        self.selected_ids={region['id']};self.filter.set('');self.only_installed.set(False);self.refresh()

    def refresh(self):
        if not self.window or not self.window.winfo_exists():return
        self.remember_selection();self.refreshing=True
        self.tree.delete(*self.tree.get_children())
        current={p['id']:p for p in installed(self.folder)};term=self.filter.get().strip().casefold()
        rows=sorted(self.regions,key=lambda r:(r['id'] not in current,r['parent']!='Netherlands',r['parent'],r['name']))
        for r in rows:
            if self.only_installed.get() and r['id'] not in current:continue
            if term not in (r['name']+' '+r['parent']).casefold():continue
            item=current.get(r['id']);date=datetime.fromtimestamp(item['stamp']/1e9).strftime('%d-%m-%Y') if item else tr('Nog niet gedownload')
            if item and r.get('provider')=='sliceosm' and time.time()-item.get('checked',0)>=7*86400:
                date+=' · '+tr('Bijwerken aanbevolen')
            self.tree.insert('','end',iid=r['id'],text=r['name'],values=(r['parent'],date))
        chosen=[ident for ident in self.selected_ids if self.tree.exists(ident)]
        if chosen:self.tree.selection_set(chosen)
        self.refreshing=False;self.remember_selection()

    def remember_selection(self):
        if self.refreshing:return
        visible=set(self.tree.get_children())
        self.selected_ids.difference_update(visible)
        self.selected_ids.update(self.tree.selection())
        if hasattr(self,'selection_status'):
            self.selection_status.set(tr('Gebieden in downloadlijst:')+f' {len(self.selected_ids)}')

    def clear_selection(self):
        self.selected_ids.clear();self.tree.selection_remove(*self.tree.selection());self.remember_selection()

    def controls(self):
        if not self.window or not self.window.winfo_exists():return
        for b in self.actions:b.configure(state='disabled' if self.running else 'normal')
        self.stop.configure(state='normal' if self.running else 'disabled')
        if self.running:self.spinner.start()
        else:self.spinner.stop()

    def selected(self,full=False):
        self.remember_selection()
        if not self.selected_ids:self.message.set('Kies eerst een gebied.');return
        regions=[r for r in self.regions if r['id'] in self.selected_ids]
        self.start(regions,full)

    def start(self,regions,full=False):
        if self.running:return
        self.running=True;self.cancel=threading.Event();cancel=self.cancel
        self.started=time.monotonic();self.last_progress='';self.percent.set(0);self.message.set('Gebiedstaak starten…');self.controls()
        from package_background import settings,enqueue,launch
        if settings(self.folder).get('enabled'):
            try:
                self.external_job=enqueue(self.folder,regions,full);self.external_progress=None;self.external_check=time.monotonic()+30;launch(self.folder)
            except Exception as exc:
                self.events.put(('error',str(exc) if isinstance(exc,ValueError) else 'Achtergrondtaak kon niet starten.'))
            return
        def worker():
            try:
                results=[]
                for region in regions:
                    if cancel.is_set():raise PackageCancelled()
                    def report(label,done,total):self.events.put(('progress',(region['name'],label,done,total)))
                    results.append(install_or_update(self.folder,region,cancel.is_set,report,full))
                self.events.put(('done',results))
            except PackageCancelled:self.events.put(('error','Gebiedstaak gestopt. Het bestaande pakket blijft behouden.'))
            except Exception as exc:
                message=str(exc) if isinstance(exc,ValueError) and not isinstance(exc,UnicodeError) else 'Gebiedstaak niet voltooid. Het bestaande pakket blijft behouden. Probeer later opnieuw.'
                if cancel.is_set():message='Gebiedstaak gestopt. Het bestaande pakket blijft behouden.'
                self.events.put(('error',message))
        threading.Thread(target=worker,daemon=True,name='region-package').start()

    def stop_job(self):
        if self.external_job:
            from package_background import stop
            stop(self.folder,self.external_job)
        self.cancel.set();self.message.set('Stoppen… Het bestaande pakket blijft behouden.')

    def poll(self):
        if self.external_job:
            from package_background import status
            if time.monotonic()>self.external_check:
                from package_background import mark_abandoned
                mark_abandoned(self.folder,self.external_job);self.external_check=time.monotonic()+5
            item=status(self.folder,self.external_job)
            if item.get('state') in ('done','error'):
                self.events.put((item['state'],item.get('results',[]) if item['state']=='done' else item.get('message','')))
                self.external_job=None
            elif item.get('progress') and item['progress']!=self.external_progress:
                self.external_progress=item['progress'];self.events.put(('progress',item['progress']))
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='background':
                    from package_background import settings
                    self.changing_background=False
                    if self.window and self.window.winfo_exists():
                        self.background.set(settings(self.folder).get('enabled',False));self.background_check.configure(state='normal')
                    self.message.set(value or ('Achtergrondwerk ingeschakeld. Downloads gaan door na sluiten; Windows moet actief zijn.' if settings(self.folder).get('enabled') else 'Achtergrondwerk uitgeschakeld. De automatische Windows-taak is verwijderd.'))
                elif kind=='progress' and not self.cancel.is_set():
                    name,label,done,total=value
                    if total:
                        self.percent.set(min(100,done/total*100))
                        detail=f' {done/1_000_000:.1f} / {total/1_000_000:.1f} MB' if label=='Gebied downloaden…' else ''
                    else:self.percent.set(0);detail=f' {done:,}' if done and label!='Gebied bij leverancier voorbereiden…' else ''
                    phase=3 if label in ('Wegenindex controleren…','Zoekindex opbouwen…') else 2 if label=='Wegen lokaal voorbereiden…' else 1
                    self.last_progress=name+f' · {phase}/3 · '+tr(label)+detail
                    self.message.set(self.last_progress+f' · {int(time.monotonic()-self.started)} s')
                elif kind in ('done','error'):
                    self.running=False
                    if kind=='error':self.message.set(value)
                    else:
                        unchanged=all(r['result']=='unchanged' for r in value)
                        self.message.set('De gebieden zijn al actueel.' if unchanged else 'Gebied gereed. Kies Automatisch uitlijnen om de opgeslagen wegen te gebruiken.')
                        self.percent.set(100)
                    self.refresh();self.controls()
        except queue.Empty:pass
        if self.running and self.last_progress and not self.cancel.is_set():
            self.message.set(self.last_progress+f' · {int(time.monotonic()-self.started)} s')
        if not self.running and time.monotonic()>=self.next_check:
            self.next_check=time.monotonic()+3600
            if not self.app.busy and getattr(self.app,'alignment_token',None) is None:
                due=due_packages(self.folder)
                if due:self.start(due)
        self.app.after(200,self.poll)

    def close(self):
        if not self.external_job:self.cancel.set()
