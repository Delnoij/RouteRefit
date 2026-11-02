# SPDX-License-Identifier: GPL-3.0-only
"""Draw a download boundary on a separate map; never modifies route geometry."""
import tkinter as tk
from tkinter import ttk
from osm_canvas import RouteMap
from gpx_core import Point
from custom_area import definition,polygon
from i18n import DisplayVar,tr

HELP='Sleep een rechthoek, of klik de hoekpunten van een veelhoek. Houd 1–2 km ruimte rond je routes. Gebruik Kaart verschuiven om te verplaatsen en het muiswiel om te zoomen.'
PRIVACY='SliceOSM ontvangt alleen deze gebiedsgrens en je IP-adres; je naam voor het gebied, GPX, tijden en bewerkingen blijven lokaal. De grens is via de downloadlink opvraagbaar. Gratis, zonder account. De dienst kan gebruiksgegevens registreren.'
UPDATES='Eigen gebieden vernieuw je handmatig met Downloaden / bijwerken. Daarbij wordt het kleine gebied opnieuw opgehaald. Er start geen automatische reeks aanvragen.'


class AreaMap(RouteMap):
    def __init__(self,master,cache,changed):
        self.points=[];self.draw_mode='rectangle';self.origin=None;self.changed=changed
        super().__init__(master,cache,lambda *a:None,lambda *a:None,lambda *a:None)

    def down(self,e):
        if self.draw_mode=='pan':return super().down(e)
        self.origin=self.point(e.x,e.y)
        if self.draw_mode=='rectangle':self.points=[]

    def motion(self,e):
        if self.draw_mode=='pan':return super().motion(e)
        if self.draw_mode=='rectangle' and self.origin:
            a,b=self.origin,self.point(e.x,e.y)
            self.points=[Point(a.lat,a.lon),Point(a.lat,b.lon),Point(b.lat,b.lon),Point(b.lat,a.lon)]
            self.overlays()

    def up(self,e):
        if self.draw_mode=='pan':return super().up(e)
        if self.draw_mode=='polygon' and self.origin:
            if len(self.points)<64:self.points.append(self.point(e.x,e.y))
        elif self.draw_mode=='rectangle':self.motion(e)
        self.origin=None;self.overlays();self.changed()

    def double(self,e):return 'break'

    def overlays(self):
        super().overlays()
        self.delete('area')
        xy=[v for p in self.points for v in self.pixel(p)]
        if len(self.points)>2:
            self.create_polygon(*xy,fill='#1682d4',stipple='gray25',outline='#0867b3',width=3,tags='area')
        elif len(self.points)>1:self.create_line(*xy,fill='#0867b3',width=3,tags='area')
        for p in self.points:
            x,y=self.pixel(p);self.create_oval(x-4,y-4,x+4,y+4,fill='white',outline='#0867b3',width=2,tags='area')
        self.tag_lower('area','overlay')


class AreaDialog:
    def __init__(self,manager):
        self.manager=manager;app=manager.app
        w=tk.Toplevel(manager.window);self.window=w;w.title(tr('Eigen gebied tekenen'))
        w.geometry(f'900x{min(720,w.winfo_screenheight()-100)}');w.minsize(700,560)
        body=ttk.Frame(w,padding=14);body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1);body.rowconfigure(3,weight=1)
        top=ttk.Frame(body);top.grid(row=0,column=0,sticky='ew')
        ttk.Label(top,text='Naam van het gebied:').pack(side='left')
        self.name=tk.StringVar(w,value=tr('Mijn grensstreek'))
        ttk.Entry(top,textvariable=self.name,width=32).pack(side='left',padx=8)
        ttk.Label(body,text=HELP,wraplength=850).grid(row=1,column=0,sticky='ew',pady=8)
        controls=ttk.Frame(body);controls.grid(row=2,column=0,sticky='ew',pady=(0,6))
        self.mode=tk.StringVar(w,value='rectangle')
        for label,value in [('Rechthoek','rectangle'),('Veelhoek','polygon'),('Kaart verschuiven','pan')]:
            ttk.Radiobutton(controls,text=label,value=value,variable=self.mode,command=self.set_mode).pack(side='left',padx=(0,10))
        ttk.Button(controls,text='−',width=3,command=lambda:self.map.zoom_by(-1)).pack(side='right')
        ttk.Button(controls,text='+',width=3,command=lambda:self.map.zoom_by(1)).pack(side='right')
        ttk.Button(controls,text='Wissen',command=self.clear).pack(side='right',padx=5)
        ttk.Button(controls,text='Laatste punt weg',command=self.undo).pack(side='right')
        self.map=AreaMap(body,app.canvas.store.folder,self.changed);self.map.grid(row=3,column=0,sticky='nsew')
        self.map.center=app.canvas.center;self.map.zoom=max(6,app.canvas.zoom-2)
        self.map.working=[list(s) for s in getattr(app,'edit_segments',[])]
        self.info=DisplayVar(w,value='Teken eerst het gewenste gebied.')
        ttk.Label(body,textvariable=self.info).grid(row=4,column=0,sticky='w',pady=5)
        ttk.Label(body,text=PRIVACY,wraplength=850,style='Muted.TLabel').grid(row=5,column=0,sticky='ew')
        ttk.Label(body,text=UPDATES,wraplength=850,style='Muted.TLabel').grid(row=6,column=0,sticky='ew',pady=5)
        actions=ttk.Frame(body);actions.grid(row=7,column=0,sticky='ew')
        self.download=ttk.Button(actions,text='Gebied downloaden via SliceOSM',command=self.submit,state='disabled')
        self.download.pack(side='left')
        ttk.Button(actions,text='Sluiten',command=w.destroy).pack(side='right')
        def wrap(event):
            for child in body.winfo_children():
                if isinstance(child,ttk.Label):child.configure(wraplength=max(300,event.width-10))
        body.bind('<Configure>',wrap)

    def set_mode(self):
        self.map.draw_mode=self.mode.get();self.map.origin=None
        self.map.configure(cursor='hand2' if self.mode.get()=='pan' else 'crosshair')

    def clear(self):self.map.points=[];self.map.overlays();self.changed()

    def undo(self):
        if self.map.points:self.map.points.pop()
        self.map.overlays();self.changed()

    def changed(self):
        try:
            ring,area=polygon([(p.lon,p.lat) for p in self.map.points])
            self.info.set(tr('Gekozen gebied:')+f' {area:.1f} km²');self.download.configure(state='normal')
        except ValueError as exc:self.info.set(str(exc));self.download.configure(state='disabled')

    def submit(self):
        if self.manager.running:self.info.set('Er loopt al een gebiedstaak.');return
        try:region=definition(self.name.get(),[(p.lon,p.lat) for p in self.map.points])
        except ValueError as exc:self.info.set(str(exc));return
        self.manager.add_custom(region);self.window.destroy();self.manager.start([region])
