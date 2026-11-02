# SPDX-License-Identifier: GPL-3.0-only
"""Small Windows 11 inspired indeterminate indicator; owned by the UI thread."""
import time
import tkinter as tk
from tkinter import ttk


class FluentProgress(tk.Canvas):
    def __init__(self, master, length=100):
        background = ttk.Style(master).lookup('TFrame', 'background') or '#f3f3f3'
        super().__init__(master, width=length, height=10, background=background,
                         highlightthickness=0, borderwidth=0)
        self._timer = None
        self._started = None
        self.bind('<Destroy>', self._destroyed, add='+')

    def start(self, interval=None):
        if self._started is not None:
            return
        self._started = time.monotonic()
        self._tick()

    def stop(self):
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None
        self._started = None
        self.delete('all')

    def _destroyed(self, event):
        if event.widget is self and self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None

    def _tick(self):
        self.delete('all')
        width = max(self.winfo_width(), int(self['width']))
        phase = ((time.monotonic() - self._started) / 1.4) % 1
        # A rounded accent stroke glides along a quiet, thin track.
        self.create_line(3, 5, width-3, 5, fill='#d6d6d6', width=3, capstyle='round')
        center = (width + 36) * (phase * phase * (3 - 2 * phase)) - 18
        left, right = max(3, center-18), min(width-3, center+18)
        if right > left:
            self.create_line(left, 5, right, 5, fill='#0078d4', width=3, capstyle='round')
        self._timer = self.after(16, self._tick)
