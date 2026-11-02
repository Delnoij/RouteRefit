# SPDX-License-Identifier: GPL-3.0-only
"""OS-owned locks release automatically on application crashes."""
import os
import time


class FileLock:
    def __init__(self,path,wait=0):self.path,self.wait,self.stream=path,wait,None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.stream=self.path.open('a+b')
        if self.stream.tell()==0:self.stream.write(b'0');self.stream.flush()
        end=time.monotonic()+self.wait
        while True:
            try:
                self.stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic()>=end:
                    self.stream.close();self.stream=None
                    raise ValueError('Een ander RouteRefit-venster gebruikt de gebiedspakketten. Probeer later opnieuw.')
                time.sleep(.05)
    def __exit__(self,*args):
        if self.stream:
            self.stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_UN)
            self.stream.close();self.stream=None
