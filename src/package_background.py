# SPDX-License-Identifier: GPL-3.0-only
"""Explicit opt-in Windows background jobs; no startup task exists by default."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from package_lock import FileLock
from package_index import PackageCancelled
from region_packages import package_root,atomic_json,install_or_update,due_packages


def settings(folder):
    try:return json.loads((package_root(folder)/'background.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {'enabled':False}


def command(folder):
    args=[sys.executable]
    if not getattr(sys,'frozen',False):args.append(str(Path(__file__).with_name('werkbank.py')))
    return args+['--package-worker',str(Path(folder).resolve())]


def configure(folder,enabled,register=None):
    """Only called by the checkbox, never merely on opening the application."""
    previous=settings(folder)
    ident=previous.get('task_id') or uuid.uuid4().hex
    task='RouteRefit-Gebieden-'+ident
    if not enabled:
        # Cancel a running worker even if Task Scheduler is temporarily unavailable.
        atomic_json(package_root(folder)/'background.json',dict(previous,enabled=False,task_id=ident))
        stop_all(folder)
    (register or windows_task)(task,command(folder),enabled)
    atomic_json(package_root(folder)/'background.json',dict(enabled=bool(enabled),task_id=ident))


def windows_task(name,args,enabled):
    if os.name!='nt':raise ValueError('Achtergrondwerk buiten RouteRefit is alleen beschikbaar onder Windows.')
    # JSON arrives on stdin; paths never become PowerShell source text.
    script=r'''
$ErrorActionPreference = 'Stop'
$cfg = [Console]::In.ReadToEnd() | ConvertFrom-Json
if ($cfg.enabled) {
  $action = New-ScheduledTaskAction -Execute $cfg.exe -Argument $cfg.arguments
  $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
  $triggers = @((New-ScheduledTaskTrigger -AtLogOn -User $user),(New-ScheduledTaskTrigger -Daily -At '09:00'))
  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
  Register-ScheduledTask -TaskName $cfg.name -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Description 'RouteRefit: alleen ingeschakeld gebiedswerk, zonder routes te uploaden.' -Force | Out-Null
} else {
  $task = Get-ScheduledTask -TaskName $cfg.name -ErrorAction SilentlyContinue
  if ($task) { Unregister-ScheduledTask -TaskName $cfg.name -Confirm:$false }
}
'''
    data=json.dumps(dict(name=name,exe=args[0],arguments=subprocess.list2cmdline(args[1:]),enabled=enabled))
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-Command',script],
                          input=data,text=True,capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise ValueError('Windows kon de achtergrondoptie niet wijzigen. Achtergrondwerk is niet ingeschakeld.' if enabled else 'Achtergrondwerk is gestopt, maar Windows kon de geplande taak niet verwijderen. Probeer uitschakelen opnieuw.')


def jobs_dir(folder):
    p=package_root(folder)/'Achtergrondtaken';p.mkdir(exist_ok=True);return p


def enqueue(folder,regions,full=False):
    if not settings(folder).get('enabled'):raise ValueError('Schakel achtergrondwerk eerst zelf in.')
    job=uuid.uuid4().hex
    atomic_json(jobs_dir(folder)/(job+'.json'),dict(id=job,state='queued',regions=regions,full=bool(full),created=time.time()))
    return job


def status(folder,job):
    if len(job)!=32 or any(c not in '0123456789abcdef' for c in job):return {}
    try:return json.loads((jobs_dir(folder)/(job+'.json')).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}


def stop(folder,job):
    if len(job)==32 and all(c in '0123456789abcdef' for c in job):
        (jobs_dir(folder)/(job+'.stop')).touch()


def stop_all(folder):
    for p in jobs_dir(folder).glob('*.json'):
        item=status(folder,p.stem)
        if item.get('state') in ('queued','running'):stop(folder,p.stem)


def launch(folder):
    if not settings(folder).get('enabled'):return
    flags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name=='nt' else 0
    subprocess.Popen(command(folder),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=flags,close_fds=True)


def pending(folder):
    return sorted([status(folder,p.stem) for p in jobs_dir(folder).glob('*.json')
                   if status(folder,p.stem).get('state') in ('queued','running')],key=lambda j:j.get('created',0))


def mark_abandoned(folder,job):
    """Detect a helper that failed to start or exited, without retrying it."""
    try:
        with FileLock(package_root(folder)/'worker.lock'):
            item=status(folder,job)
            if item.get('state') in ('queued','running'):
                item.update(state='error',message='Achtergrondtaak niet actief. Het bestaande pakket blijft behouden. Kies opnieuw Downloaden / bijwerken.')
                atomic_json(jobs_dir(folder)/(job+'.json'),item)
    except ValueError:pass # A live helper owns the lock.


def run(folder):
    if not settings(folder).get('enabled'):return
    try:
        with FileLock(package_root(folder)/'worker.lock'):
            # Work interrupted by a Windows shutdown is left for review, never
            # silently retried. A supplier job can still be resumed manually.
            for item in pending(folder):
                if item['state']=='running':
                    item.update(state='error',message='Achtergrondtaak onderbroken. Het bestaande pakket blijft behouden. Kies opnieuw Downloaden / bijwerken.')
                    atomic_json(jobs_dir(folder)/(item['id']+'.json'),item)
            if not pending(folder):
                due=due_packages(folder)
                if due:enqueue(folder,due)
            while settings(folder).get('enabled'):
                queue=pending(folder)
                if not queue:break
                item=queue[0];job=item['id'];path=jobs_dir(folder)/(job+'.json')
                cancel_state=[0.,False]
                def cancelled():
                    if time.monotonic()-cancel_state[0]>.25:
                        cancel_state[:]=[time.monotonic(),not settings(folder).get('enabled') or (jobs_dir(folder)/(job+'.stop')).exists()]
                    return cancel_state[1]
                item['state']='running';atomic_json(path,item)
                try:
                    results=[]
                    for region in item['regions']:
                        if cancelled():raise PackageCancelled()
                        def progress(label,done,total):
                            item.update(progress=[region['name'],label,done,total],heartbeat=time.time())
                            atomic_json(path,item)
                        results.append(install_or_update(folder,region,cancelled,progress,item['full']))
                    item.update(state='done',results=results)
                except Exception as exc:
                    message='Gebiedstaak gestopt. Het bestaande pakket blijft behouden.' if cancelled() or isinstance(exc,PackageCancelled) else str(exc) if isinstance(exc,ValueError) else 'Gebiedstaak niet voltooid. Het bestaande pakket blijft behouden. Probeer later opnieuw.'
                    item.update(state='error',message=message)
                atomic_json(path,item)
    except ValueError:
        # Another worker owns the queue; let it finish without extra attempts.
        return
