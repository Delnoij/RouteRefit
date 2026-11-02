# SPDX-License-Identifier: GPL-3.0-only
"""Missing-road downloads enrich the cache, never an open proposal or editable route."""
import queue
import threading
from tkinter import ttk
from i18n import DisplayVar,tr
from fluent_progress import FluentProgress

LOADING='Ontbrekende wegen ophalen op de achtergrond. Je kunt het lokale voorstel al bekijken.'
READY='Nieuwe wegen beschikbaar. Kies Voorstel aanvullen om opnieuw te rekenen.'
PARTLY_READY='Enkele wegen toegevoegd; download gestopt. Kies Voorstel aanvullen om die te gebruiken.'
FAILED='Wegdownload gestopt. Het lokale voorstel blijft behouden. Probeer later zelf opnieuw.'
STOPPED='Wegdownload gestopt. Je route en opgeslagen wegen zijn behouden.'
CHANGED='Route of instellingen gewijzigd; de achtergrondaanvraag is gestopt.'
NO_LOCAL='Nog geen bruikbare opgeslagen wegen. Je route blijft behouden; ontbrekende wegen worden opgehaald.'
NO_LOCAL_IDLE='Nog geen bruikbare opgeslagen wegen. Je route blijft behouden; probeer later zelf opnieuw.'


def failure_detail(error):
    """Explain the cause without exposing request URLs, coordinates or file paths."""
    reason=getattr(error,'reason',None)
    if reason=='slow':
        return tr('De wegendienst antwoordde niet binnen {seconds} seconden.').format(seconds=round(error.seconds or 45))
    if reason=='budget':
        return tr('De maximale downloadtijd van {seconds} seconden is bereikt.').format(seconds=round(error.seconds or 60))
    return {
        'cooldown':'De wegendienst vraagt een pauze; er wordt niet automatisch opnieuw geprobeerd.',
        'rate':'De wegendienst beperkt tijdelijk het aantal aanvragen.',
        'busy':'De wegendienst is tijdelijk niet beschikbaar.',
        'connection':'Verbinding met de wegendienst is niet gelukt.',
        'active':'Een eerdere netwerkverbinding wordt nog afgesloten.',
        'incomplete':'De wegendienst leverde onvolledige weggegevens.',
        'limit':'De aanvraag overschrijdt de grens voor weggegevens.',
    }.get(reason,'Weggegevens konden niet worden opgehaald of lokaal verwerkt.')


class LocalFirstRoads:
    def add_enrichment_controls(self,parent,window=None,key=None):
        if not hasattr(self,'enrichment_message'):
            self.enrichment_message=DisplayVar(value='')
            self.enrichment_controls=[]
        frame=ttk.Frame(parent,padding=(0,4))
        ttk.Label(frame,textvariable=self.enrichment_message,wraplength=880).pack(fill='x')
        row=ttk.Frame(frame);row.pack(fill='x')
        fill=ttk.Button(row,text='Voorstel aanvullen',command=lambda:self.supplement_proposal(window,key))
        fill.pack(side='left')
        stop=ttk.Button(row,text='Download stoppen',command=self.cancel_road_enrichment)
        stop.pack(side='left',padx=6)
        spinner=FluentProgress(row,length=85);spinner.pack(side='left',padx=6)
        self.enrichment_controls.append((frame,fill,stop,spinner))
        self.refresh_enrichment_controls()
        return frame

    def refresh_enrichment_controls(self):
        job=getattr(self,'enrichment_job',None)
        running=bool(job and job['running'])
        ready=bool(job and job['ready'])
        live=[]
        for frame,fill,stop,spinner in getattr(self,'enrichment_controls',[]):
            if not frame.winfo_exists():continue
            fill.configure(state='normal' if ready else 'disabled')
            stop.configure(state='normal' if running else 'disabled')
            if running:spinner.start()
            else:spinner.stop()
            live.append((frame,fill,stop,spinner))
        self.enrichment_controls=live
        if hasattr(self,'enrichment_bar'):
            if self.enrichment_message.get():
                self.enrichment_bar.pack(fill='x',pady=(0,6),before=self.enrichment_before)
            else:self.enrichment_bar.pack_forget()

    def cancel_road_enrichment(self,clear=False,message=STOPPED):
        job=getattr(self,'enrichment_job',None)
        if job:
            job['cancel'].set();job['running']=False;job['ready']=False
        self.enrichment_job=None
        if hasattr(self,'enrichment_message'):
            self.enrichment_message.set('' if clear else message)
            if not clear and hasattr(self,'status') and self.status.get()==NO_LOCAL:self.status.set(message)
            self.refresh_enrichment_controls()

    def enrichment_current(self,job):
        return self.enrichment_job is job and not job['cancel'].is_set() and job['key']==self.alignment_key()

    def start_road_enrichment(self,source,download):
        existing=getattr(self,'enrichment_job',None)
        if existing and existing['running'] and self.enrichment_current(existing):return
        self.cancel_road_enrichment(clear=True)
        job={'key':self.alignment_key(),'cancel':threading.Event(),'running':True,'ready':False,'completed':0}
        self.enrichment_job=job
        self.enrichment_message.set(LOADING)
        self.refresh_enrichment_controls()
        results=queue.Queue()

        def emit(message):results.put(('progress',message))
        def work():
            try:
                from road_download import DownloadBudget
                download(source,emit,job['cancel'],DownloadBudget.background(emit))
                results.put(('done',None))
            except Exception as exc:results.put(('error',exc))

        def poll():
            if self.enrichment_job is not job:return
            if not self.enrichment_current(job):
                self.cancel_road_enrichment(message=CHANGED);return
            try:
                while True:
                    kind,value=results.get_nowait()
                    if kind=='progress':
                        # Only completed missing tiles count as usable progress.
                        if value.startswith('Wegen laden: '):
                            job['completed']=int(value.split(': ',1)[1].split('/',1)[0])
                        if value.startswith('Wegen ophalen: '):
                            self.enrichment_message.set(LOADING+'\n'+value)
                    else:
                        job['running']=False
                        job['ready']=kind=='done' or job['completed']>0
                        self.enrichment_message.set(READY if kind=='done' else
                            (PARTLY_READY if job['ready'] else FAILED)+'\n'+failure_detail(value))
                        if self.status.get()==NO_LOCAL:self.status.set(self.enrichment_message.get())
                        self.refresh_enrichment_controls()
                        # Keep guarding the ready button against route/profile changes.
                        break
            except queue.Empty:pass
            self.after(150,poll)

        threading.Thread(target=work,daemon=True,name='RouteRefit-wegen-aanvullen').start()
        self.after(150,poll)

    def supplement_proposal(self,window=None,key=None):
        job=getattr(self,'enrichment_job',None)
        if not job or not job['ready']:return
        if not self.enrichment_current(job) or key is not None and key!=self.alignment_key():
            self.cancel_road_enrichment(message=CHANGED);return
        if window is not None:window.destroy()
        # This explicit action only recomputes from local data, never starts a retry.
        self.automatic_alignment_action(download_missing=False)

    def retain_enrichment_after_accept(self,previous_key):
        job=getattr(self,'enrichment_job',None)
        if job and job['key']==previous_key and not job['cancel'].is_set():
            job['key']=self.alignment_key()
