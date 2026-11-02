# SPDX-License-Identifier: GPL-3.0-only
"""Optional public region downloads and small daily updates; never receives a GPX."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time
import urllib.request
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from package_geometry import parse_poly,covered_boxes
from package_index import check,ingest
from road_index import RoadIndex,road_xml,INDEX_LOCK,missing_rectangles
from app_version import VERSION
from package_lock import FileLock

PACKAGE_LOCK=threading.RLock()
SETTINGS_LOCK=threading.RLock()
JOB_LOCK=threading.Lock()
WEEK=7*86400
MAX_PACKAGE=500_000_000
MAX_DIFF=20_000_000
CATALOG=Path(__file__).with_name('regions.json')


def safe_url(url):
    parsed=urllib.parse.urlsplit(url)
    if (parsed.scheme!='https' or parsed.netloc!='download.geofabrik.de' or
        parsed.query or parsed.fragment or '..' in parsed.path.split('/')):
        raise ValueError('Onbekende leverancier van gebiedsgegevens.')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,safe_url(newurl))


def retrieve(url,dest,cancelled,progress,limit=MAX_PACKAGE):
    """One streaming attempt, finite read/deadline, no retries or route payloads."""
    safe_url(url);check(cancelled)
    request=urllib.request.Request(url,headers={'User-Agent':f'RouteRefit/{VERSION} (optional offline regions)'})
    started=time.monotonic();size=0;last=0
    with urllib.request.build_opener(Redirect).open(request,timeout=20) as response:
        total=int(response.headers.get('Content-Length','0'))
        if total>limit:raise ValueError('Dit pakket is te groot. Kies een kleinere regio, bijvoorbeeld een provincie.')
        reserve=max(total*8,500_000_000) if limit==MAX_PACKAGE else max(total*2,8_000_000)
        if shutil.disk_usage(dest.parent).free < reserve:
            raise ValueError('Onvoldoende vrije schijfruimte voor het gebied en de voorbereiding.')
        with dest.open('wb') as stream:
            while True:
                check(cancelled)
                if time.monotonic()-started>1800:raise TimeoutError('Gebiedsdownload duurt te lang.')
                data=response.read1(262144)
                if not data:break
                size+=len(data)
                if size>limit:raise ValueError('Dit pakket is te groot. Kies een kleinere regio, bijvoorbeeld een provincie.')
                stream.write(data)
                if time.monotonic()-last>.25:
                    progress('Gebied downloaden…',size,total);last=time.monotonic()
        if total and size!=total:raise ValueError('De download is onvolledig. Het bestaande pakket blijft behouden.')
    check(cancelled)
    return size


def atomic_json(path,data):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)


def catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


def custom_regions(folder):
    try:
        items=json.loads((package_root(folder)/'custom.json').read_text(encoding='utf-8'))
        return [r for r in items if r.get('provider')=='sliceosm' and re.fullmatch('eigen-[0-9a-f]{32}',r['id'])]
    except (OSError,ValueError,KeyError,TypeError):return []


def save_custom(folder,region):
    with SETTINGS_LOCK:
        items=custom_regions(folder)
        items=[r for r in items if r['id']!=region['id']]+[region]
        atomic_json(package_root(folder)/'custom.json',items)


def package_root(folder):
    root=Path(folder)/'Gebiedspakketten';root.mkdir(parents=True,exist_ok=True)
    return root


def installed(folder):
    result=[]
    root=Path(folder)/'Gebiedspakketten'
    for file in sorted(root.glob('*/active.json')):
        try:
            item=json.loads(file.read_text(encoding='utf-8'))
            if not re.fullmatch('[0-9a-f]{32}',item['snapshot']):continue
            if not re.fullmatch('[a-zA-Z0-9_-]+',item['id']) or file.parent.name!=item['id']:continue
            if not (file.parent/item['snapshot']/'Wegenindex/wegen.sqlite3').is_file():continue
            result.append(item)
        except (OSError,ValueError,KeyError):continue
    return result


def preferences(folder):
    try:return json.loads((package_root(folder)/'settings.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {'weekly':True,'attempts':{}}


def set_weekly(folder,enabled):
    with SETTINGS_LOCK:
        data=preferences(folder);data['weekly']=bool(enabled)
        atomic_json(package_root(folder)/'settings.json',data)


def due_packages(folder,now=None):
    now=now or time.time();settings=preferences(folder)
    if not settings.get('weekly',True):return []
    return [p for p in installed(folder) if p.get('provider')!='sliceosm' and now-p.get('checked',0)>=WEEK
            and now-settings.get('attempts',{}).get(p['id'],0)>=86400]


def parse_state(text):
    values=dict(line.split('=',1) for line in text.splitlines() if '=' in line and not line.startswith('#'))
    sequence=int(values['sequenceNumber'])
    stamp=datetime.fromisoformat(values['timestamp'].replace('\\:',':').replace('Z','+00:00'))
    if sequence<0 or stamp.tzinfo is None:raise ValueError('Ongeldige updategegevens.')
    return sequence,int(stamp.timestamp()*1_000_000_000)


def sequence_url(base,sequence,suffix):
    value=f'{sequence:09d}'
    return safe_url(base+'/'+value[:3]+'/'+value[3:6]+'/'+value[6:]+suffix)


def clean_stage(stage):
    # Only known files below this generated snapshot; no user routes live here.
    for path in stage.glob('*'):
        if path.is_file():path.unlink(missing_ok=True)
    sub=stage/'Wegenindex'
    if sub.is_dir():
        for path in sub.iterdir():
            if path.is_file():path.unlink(missing_ok=True)
        sub.rmdir()
    stage.rmdir()


def install_or_update(folder,region,cancelled=lambda:False,progress=lambda *a:None,full=False,fetch=retrieve):
    """Publish only a fully checked snapshot; updates do not touch active proposals."""
    if region.get('provider')=='sliceosm':
        from custom_download import install
        return install(folder,region,cancelled,progress,full)
    if not JOB_LOCK.acquire(False):raise ValueError('Er loopt al een gebiedstaak.')
    stage=None;published=False;joblock=None
    try:
        joblock=FileLock(package_root(folder)/'job.lock');joblock.__enter__()
        ident=region['id']
        if not re.fullmatch('[a-zA-Z0-9_-]+',ident):raise ValueError('Ongeldig gebied.')
        url=safe_url(region['url'])
        if not url.endswith('-latest.osm.pbf'):raise ValueError('Ongeldig gebiedsbestand.')
        directory=package_root(folder)/ident;directory.mkdir(exist_ok=True)
        (directory/'DATA-LICENSE.txt').write_text(
            'Map data: © OpenStreetMap contributors. Open Database License (ODbL) 1.0.\n'
            'https://www.openstreetmap.org/copyright\nhttps://opendatacommons.org/licenses/odbl/1-0/\n'
            'Regional extracts provided by Geofabrik: https://download.geofabrik.de/\n',encoding='utf-8')
        old=next((p for p in installed(folder) if p['id']==ident),None)
        with SETTINGS_LOCK:
            prefs=preferences(folder);prefs.setdefault('attempts',{})[ident]=time.time()
            atomic_json(package_root(folder)/'settings.json',prefs)
        stage=directory/uuid.uuid4().hex;stage.mkdir()
        def small(url,name,limit=2_000_000):
            path=stage/name
            progress('Gebied controleren…',0,0)
            fetch(url,path,cancelled,lambda *args:None,limit)
            return path
        base=url.removesuffix('-latest.osm.pbf')
        update_url=base+'-updates'
        poly=small(base+'.poly','area.poly')
        rings=parse_poly(poly.read_text(encoding='utf-8'))
        poly_digest=hashlib.sha256(poly.read_bytes()).hexdigest()
        state=small(update_url+'/state.txt','state.txt')
        sequence,stamp=parse_state(state.read_text(encoding='utf-8'))
        if old and not full:
            if poly_digest!=old['polygon_digest'] or sequence-old['sequence']>90 or sequence<old['sequence']:
                raise ValueError('Een volledig nieuw pakket is nodig. Kies Opnieuw downloaden. Het bestaande pakket blijft bruikbaar.')
            if sequence==old['sequence']:
                check(cancelled)
                with PACKAGE_LOCK:
                    old['checked']=time.time();atomic_json(directory/'active.json',old)
                return dict(old,result='unchanged',download_bytes=0)
            progress('Wijzigingen ophalen…',0,sequence-old['sequence'])
            source=directory/old['snapshot']/'Wegenindex/wegen.sqlite3'
            if shutil.disk_usage(stage).free<source.stat().st_size+128_000_000:
                raise ValueError('Onvoldoende vrije schijfruimte voor een veilige update. Het bestaande pakket blijft behouden.')
            (stage/'Wegenindex').mkdir()
            shutil.copy2(source,stage/'Wegenindex/wegen.sqlite3')
            total=0;stats=old['stats']
            for number in range(old['sequence']+1,sequence+1):
                check(cancelled)
                delta=stage/'changes.osc.gz'
                total+=fetch(sequence_url(update_url,number,'.osc.gz'),delta,cancelled,progress,MAX_DIFF)
                if total>64_000_000:raise ValueError('Veel wijzigingen beschikbaar. Kies Opnieuw downloaden. Het bestaande pakket blijft bruikbaar.')
                stats=ingest(stage,delta,stamp,cancelled,progress,updating=True)
                delta.unlink()
            result='updated'
        else:
            import osmium
            md5=small(url+'.md5','download.md5',2000).read_text(encoding='utf-8').split()[0]
            if not re.fullmatch('[a-fA-F0-9]{32}',md5):raise ValueError('Controlegetal van het gebied ontbreekt.')
            pbf=stage/'region.osm.pbf';total=fetch(url,pbf,cancelled,progress,MAX_PACKAGE)
            with pbf.open('rb') as stream:
                if hashlib.file_digest(stream,'md5').hexdigest()!=md5.lower():
                    raise ValueError('De downloadcontrole is mislukt. Het bestaande pakket blijft behouden.')
            with osmium.io.Reader(str(pbf),osmium.osm.NOTHING) as reader:
                header=reader.header()
                if header.get('osmosis_replication_base_url').rstrip('/')!=update_url:
                    raise ValueError('Het gebied bevat geen passende updategegevens.')
                sequence=int(header.get('osmosis_replication_sequence_number'))
                stamp=int(datetime.fromisoformat(header.get('osmosis_replication_timestamp').replace('Z','+00:00')).timestamp()*1e9)
            stats=ingest(stage,pbf,stamp,cancelled,progress)
            pbf.unlink();result='installed'
        check(cancelled)
        info=dict(id=ident,name=region['name'],url=url,snapshot=stage.name,sequence=sequence,
                  stamp=stamp,polygon=rings,polygon_digest=poly_digest,checked=time.time(),stats=stats)
        for path in stage.iterdir():
            if path.is_file():path.unlink()
        with PACKAGE_LOCK,FileLock(package_root(folder)/'publish.lock',wait=30):
            check(cancelled);atomic_json(directory/'active.json',info);published=True
            if old:
                previous=directory/old['snapshot']
                try:clean_stage(previous)
                except OSError:pass # A reader in another app instance may still own it.
        return dict(info,result=result,download_bytes=total)
    finally:
        if stage and not published:
            try:clean_stage(stage)
            except OSError:pass
        if joblock:joblock.__exit__(None,None,None)
        JOB_LOCK.release()


def sync_packages(index,wanted,query=None,progress=None,cancelled=None):
    """Materialize only a route corridor, once per package revision and query."""
    cancelled=cancelled or (lambda:False)
    requested=list(query or wanted)
    requested.extend(missing_rectangles(wanted,requested))
    if not installed(index.folder):return
    with PACKAGE_LOCK,INDEX_LOCK,FileLock(package_root(index.folder)/'publish.lock',wait=30):
        for item in installed(index.folder):
            check(cancelled)
            boxes=covered_boxes(requested,item['polygon'])
            if not boxes:continue
            signature=hashlib.sha256(json.dumps(requested).encode()).hexdigest()[:24]
            relative=f"Pakketcorridors/{item['id']}-{signature}.osm"
            known=index.db.execute('SELECT stamp FROM sources WHERE path=?',(relative,)).fetchone()
            if known and known[0]>=item['stamp']:continue
            if progress:progress('Gebiedspakket voor deze route voorbereiden…')
            package=package_root(index.folder)/item['id']/item['snapshot']
            # Published snapshots are immutable. Never let RoadIndex's repair
            # path turn a damaged/missing regional database into empty coverage.
            regional=RoadIndex.__new__(RoadIndex);regional.folder=package.resolve()
            regional.path=regional.folder/'Wegenindex/wegen.sqlite3'
            regional.db=sqlite3.connect(regional.path.as_uri()+'?mode=ro',uri=True)
            with regional:
                regional.identity=regional.db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0]
                road=regional.read([],requested)
                root=ET.fromstring(road_xml(road)) if road else ET.Element('osm',version='0.6')
            stamp=datetime.fromtimestamp(item['stamp']/1e9,timezone.utc).isoformat()
            ET.SubElement(root,'meta',osm_base=stamp)
            path=index.folder/relative;path.parent.mkdir(exist_ok=True)
            raw=ET.tostring(root,encoding='utf-8',xml_declaration=True)
            # A stopped materialization must never publish a partial map/index.
            check(cancelled)
            tmp=path.with_suffix('.tmp');tmp.write_bytes(raw);os.replace(tmp,path)
            index.ingest_files([(path,boxes)])
