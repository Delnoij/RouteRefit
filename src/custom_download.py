# SPDX-License-Identifier: GPL-3.0-only
"""Bounded, resumable SliceOSM jobs, only after an explicit download action."""
from datetime import datetime
import json
import re
import time
import urllib.request
from urllib.parse import urlsplit
import uuid
from package_index import check,ingest
from package_lock import FileLock
from custom_area import polygon
from app_version import VERSION

HOST='https://slice.openstreetmap.us'
MAX_WAIT=600


def safe_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc!='slice.openstreetmap.us' or p.query or p.fragment:
        raise ValueError('Onbekende leverancier van gebiedsgegevens.')
    if not re.fullmatch(r'/(?:api/(?:[0-9a-f-]{36})?|files/[0-9a-f-]{36}\.osm\.pbf)',p.path):
        raise ValueError('Ongeldig downloadadres.')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,safe_url(newurl))


class Client:
    def open(self,url,data=None):
        req=urllib.request.Request(safe_url(url),data=data,headers={
            'User-Agent':f'RouteRefit/{VERSION} (optional small area)',
            'Content-Type':'application/json','Accept':'application/json'})
        # No browser cookies, account, telemetry or additional provider.
        return urllib.request.build_opener(Redirect).open(req,timeout=20)

    def status(self,job=''):
        with self.open(HOST+'/api/'+job) as response:raw=response.read(65537)
        if len(raw)>65536:raise ValueError('Ongeldig antwoord van de gebiedsdienst.')
        return json.loads(raw)

    def submit(self,ring):
        data=json.dumps(dict(Name='none',RegionType='geojson',RegionData=dict(type='Polygon',coordinates=[ring]))).encode()
        with self.open(HOST+'/api/',data) as response:raw=response.read(1025).decode().strip().strip('"')
        return str(uuid.UUID(raw))

    def download(self,job,dest,cancelled,progress):
        from region_packages import MAX_PACKAGE
        import shutil
        started=time.monotonic();done=0;last=0
        with self.open(HOST+'/files/'+str(uuid.UUID(job))+'.osm.pbf') as response:
            total=int(response.headers.get('Content-Length','0'))
            if total>MAX_PACKAGE:raise ValueError('Dit pakket is te groot. Kies een kleiner gebied.')
            if shutil.disk_usage(dest.parent).free<max(total*8,500_000_000):
                raise ValueError('Onvoldoende vrije schijfruimte voor het gebied en de voorbereiding.')
            with dest.open('wb') as stream:
                while True:
                    check(cancelled)
                    if time.monotonic()-started>1800:raise TimeoutError('Gebiedsdownload duurt te lang.')
                    raw=response.read1(262144)
                    if not raw:break
                    done+=len(raw)
                    if done>MAX_PACKAGE:raise ValueError('Dit pakket is te groot. Kies een kleiner gebied.')
                    stream.write(raw)
                    if time.monotonic()-last>.25:progress('Gebied downloaden…',done,total);last=time.monotonic()
        if not done or total and total!=done:raise ValueError('De download is onvolledig. Het bestaande pakket blijft behouden.')
        return done


def timestamp(text):
    value=datetime.fromisoformat(str(text).replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('Ongeldige updategegevens.')
    return int(value.timestamp()*1e9)


def install(folder,region,cancelled,progress,full=False,client=None,clock=time.monotonic,pause=time.sleep):
    import region_packages as rp
    client=client or Client()
    ring,area=polygon(region['polygon'][0][1])
    ident=region['id']
    if not re.fullmatch('eigen-[0-9a-f]{32}',ident):raise ValueError('Ongeldig gebied.')
    if not rp.JOB_LOCK.acquire(False):raise ValueError('Er loopt al een gebiedstaak.')
    stage=None;published=False
    try:
        with FileLock(rp.package_root(folder)/'job.lock'):
            directory=rp.package_root(folder)/ident;directory.mkdir(exist_ok=True)
            old=next((p for p in rp.installed(folder) if p['id']==ident),None)
            (directory/'DATA-LICENSE.txt').write_text('© OpenStreetMap contributors. ODbL 1.0.\nhttps://www.openstreetmap.org/copyright\nExtract: https://slice.openstreetmap.us/\n',encoding='utf-8')
            progress('Gebied controleren…',0,0);check(cancelled)
            status=client.status();stamp=timestamp(status['Timestamp']);check(cancelled)
            if old and not full and stamp<=old['stamp']:
                old['checked']=time.time();rp.atomic_json(directory/'active.json',old)
                return dict(old,result='unchanged',download_bytes=0)
            pending_file=directory/'pending.json'
            try:pending=json.loads(pending_file.read_text(encoding='utf-8'))
            except (OSError,ValueError):pending={}
            shape=json.loads(json.dumps(ring))
            if pending.get('ring')!=shape or time.time()-pending.get('created',0)>23*3600:
                pending={}
            if not pending:
                # A single POST per job. A timeout here is reported, never retried.
                job=client.submit(ring)
                pending=dict(job=job,ring=ring,stamp=stamp,created=time.time())
                rp.atomic_json(pending_file,pending)
            job=str(uuid.UUID(pending['job']));stamp=pending['stamp']
            start=clock()
            while True:
                check(cancelled)
                progress('Gebied bij leverancier voorbereiden…',int(clock()-start),0)
                state=client.status(job);check(cancelled)
                if state.get('Error'):raise ValueError('De gebiedsdienst kon dit gebied niet voorbereiden. Het bestaande pakket blijft behouden.')
                if state.get('Complete') is True:break
                if clock()-start>=MAX_WAIT:
                    raise ValueError('De gebiedsdienst heeft meer tijd nodig. Kies later Downloaden / bijwerken om dezelfde aanvraag te vervolgen.')
                # A status check is not a new extraction attempt. At most one
                # every five seconds, with promptly cancellable waiting.
                for _ in range(20):check(cancelled);pause(.25)
            stage=directory/uuid.uuid4().hex;stage.mkdir()
            pbf=stage/'region.osm.pbf';total=client.download(job,pbf,cancelled,progress)
            stats=ingest(stage,pbf,stamp,cancelled,progress);check(cancelled)
            info=dict(region,snapshot=stage.name,stamp=stamp,checked=time.time(),stats=stats)
            for path in stage.iterdir():
                if path.is_file():path.unlink()
            with rp.PACKAGE_LOCK,FileLock(rp.package_root(folder)/'publish.lock',wait=30):
                check(cancelled);rp.atomic_json(directory/'active.json',info);published=True
                if old:
                    try:rp.clean_stage(directory/old['snapshot'])
                    except OSError:pass
            pending_file.unlink(missing_ok=True)
            return dict(info,result='updated' if old else 'installed',download_bytes=total)
    finally:
        if stage and not published:
            try:rp.clean_stage(stage)
            except OSError:pass
        rp.JOB_LOCK.release()
