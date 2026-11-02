# SPDX-License-Identifier: GPL-3.0-only
"""Review computed geometry before committing it to the editable route."""
import tkinter as tk
from tkinter import ttk
from i18n import tr
from proposal_summary import proposal_summary, summary_rows


def same_route(left, right):
    return len(left) == len(right) and all(
        len(a) == len(b) and all((p.lat,p.lon,p.ele,p.time)==(q.lat,q.lon,q.ele,q.time) for p,q in zip(a,b))
        for a,b in zip(left,right))


class ProposalReviewUI:
    def review_route_proposal(self, proposed, apply, key=None, key_fn=None, notes=(), on_cancel=None, enrichment=False):
        from werkbank import MAPS
        from osm_canvas import RouteMap
        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None
        window = tk.Toplevel(self)
        window.title('Routevoorstel controleren')
        window.geometry('1000x660')
        window.minsize(800, 520)
        window.transient(self)
        try:
            speed = float(self.flat.get().replace(',', '.'))
        except ValueError:
            speed = None
        summary = proposal_summary(self.track.segments, self.edit_segments, proposed, speed)
        top = ttk.Frame(window, padding=12)
        top.pack(fill='x')
        ttk.Label(top, text='De bewerkbare route verandert pas na Voorstel overnemen.', wraplength=900).pack(anchor='w')
        metrics = ttk.Frame(top)
        metrics.pack(fill='x', pady=8)
        for index, (label, value) in enumerate(summary_rows(summary)):
            ttk.Label(metrics, text=label).grid(row=index, column=0, sticky='w', padx=(0,24))
            ttk.Label(metrics, text=value).grid(row=index, column=1, sticky='w')
        ttk.Label(top, text=summary['time_basis'], style='Muted.TLabel').pack(anchor='w')
        ttk.Label(top, text='Hoogtes en tijden van gereconstrueerde stukken blijven schattingen.', wraplength=900).pack(anchor='w')
        ttk.Label(top, text='Oranje: origineel · Blauw: bewerkbaar · Groen: voorstel', style='Muted.TLabel').pack(anchor='w', pady=(6,0))
        buttons = ttk.Frame(window, padding=10)
        buttons.pack(side='bottom', fill='x')

        def accept():
            if self.busy or key_fn and key != key_fn():
                self.status.set('Route of instellingen gewijzigd; bereken het voorstel opnieuw.')
                window.destroy()
                return
            window.destroy()
            apply()

        def cancel():
            window.destroy()
            if on_cancel and (key_fn is None or key == key_fn()):
                on_cancel()

        ttk.Button(buttons, text='Voorstel overnemen', style='Accent.TButton', command=accept).pack(side='right')
        ttk.Button(buttons, text='Annuleren', command=cancel).pack(side='right', padx=6)
        window.protocol('WM_DELETE_WINDOW', cancel)
        if enrichment:
            self.add_enrichment_controls(window,window,key).pack(side='bottom',fill='x',padx=12)
        if notes:
            ttk.Label(window, text='\n'.join(tr(n) for n in notes[:2]), wraplength=900).pack(side='bottom', fill='x', padx=12)
        preview = RouteMap(window, MAPS/'Tegels', lambda *a:None,lambda *a:None,lambda *a:None)
        preview.pack(fill='both',expand=True,padx=12,pady=6)
        preview.set_mode('view')
        preview.set_layers(self.track.segments, self.edit_segments, proposed)
        window.after_idle(lambda: preview.fit(self.edit_segments+proposed) if window.winfo_exists() else None)
        window.grab_set()
        return window
