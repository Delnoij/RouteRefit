# SPDX-License-Identifier: GPL-3.0-only
"""Cooperate with Windows: normal speed when spare, yield under competing load."""
import ctypes
from ctypes import wintypes
import os
import sys
import threading
import time


def competing_load(previous,current):
    idle,kernel,user,own= (b-a for a,b in zip(previous,current))
    total=kernel+user
    return max(0.,min(1.,(total-idle-own)/total)) if total>0 else 0.


class Resources:
    def __init__(self):
        self.busy=False;self.stop=threading.Event();self.handle=None;self.cache_kib=32768
        self.samples=0;self.busy_samples=0;self.load_sum=0.

    def __enter__(self):
        if os.name!='nt':return self
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.GetCurrentProcess.restype=wintypes.HANDLE
        self.kernel.OpenThread.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.kernel.OpenThread.restype=wintypes.HANDLE
        self.kernel.SetThreadPriority.argtypes=[wintypes.HANDLE,ctypes.c_int]
        self.kernel.GetThreadPriority.argtypes=[wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self.kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
        self.kernel.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        self.kernel.GetPriorityClass.argtypes=[wintypes.HANDLE]
        self.process=self.kernel.GetCurrentProcess();self.process_priority=self.kernel.GetPriorityClass(self.process)
        self.headless='--package-worker' in sys.argv
        self.handle=self.kernel.OpenThread(0x60,False,threading.get_native_id())
        self.priority=self.kernel.GetThreadPriority(self.handle) if self.handle else 0
        class Memory(ctypes.Structure):
            _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(name,ctypes.c_ulonglong) for name in ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
        memory=Memory();memory.length=ctypes.sizeof(memory)
        if self.kernel.GlobalMemoryStatusEx(ctypes.byref(memory)) and memory.available>2*1024**3:self.cache_kib=131072
        self.thread=threading.Thread(target=self.monitor,daemon=True,name='package-resources');self.thread.start()
        return self

    def sample(self):
        def value(ft):return (ft.dwHighDateTime<<32)|ft.dwLowDateTime
        idle,kernel,user=(wintypes.FILETIME() for _ in range(3))
        created,exit_time,pk,pu=(wintypes.FILETIME() for _ in range(4))
        if not self.kernel.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)):raise OSError('CPU sample')
        if not self.kernel.GetProcessTimes(self.process,*map(ctypes.byref,(created,exit_time,pk,pu))):raise OSError('Process sample')
        return tuple(map(value,(idle,kernel,user)))+(value(pk)+value(pu),)

    def monitor(self):
        try:
            previous=self.sample();quiet=0
            while not self.stop.wait(1):
                current=self.sample();load=competing_load(previous,current);previous=current
                quiet=quiet+1 if load<.2 else 0
                if load>.4:self.busy=True
                elif quiet>=3:self.busy=False
                self.samples+=1;self.busy_samples+=int(self.busy);self.load_sum+=load
                if self.handle:self.kernel.SetThreadPriority(self.handle,-1 if self.busy else self.priority)
                if self.headless:self.kernel.SetPriorityClass(self.process,0x4000 if self.busy else self.process_priority)
        except (OSError,AttributeError):pass

    def cooperate(self):
        if self.busy:time.sleep(.004)

    def __exit__(self,*args):
        self.stop.set()
        if hasattr(self,'thread'):self.thread.join(timeout=2)
        if self.handle:
            self.kernel.SetThreadPriority(self.handle,self.priority);self.kernel.CloseHandle(self.handle)
        if getattr(self,'headless',False):self.kernel.SetPriorityClass(self.process,self.process_priority)
