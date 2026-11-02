# SPDX-License-Identifier: GPL-3.0-only
"""Keyboard-accessible local calendar and 24-hour time picker, no network."""
import calendar
from datetime import date
import tkinter as tk
from tkinter import ttk

MONTHS = {
 'nl': 'januari februari maart april mei juni juli augustus september oktober november december',
 'en': 'January February March April May June July August September October November December',
 'de': 'Januar Februar März April Mai Juni Juli August September Oktober November Dezember',
 'fr': 'janvier février mars avril mai juin juillet août septembre octobre novembre décembre',
 'es': 'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre',
 'pt': 'janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro',
}
WEEKDAYS = {'nl':'ma di wo do vr za zo', 'en':'Mo Tu We Th Fr Sa Su',
 'de':'Mo Di Mi Do Fr Sa So', 'fr':'lu ma me je ve sa di',
 'es':'lu ma mi ju vi sá do', 'pt':'se te qu qu se sá do'}


class CalendarPicker(ttk.Frame):
    def __init__(self, master, variable, language='nl'):
        super().__init__(master)
        self.variable = variable
        self.language = language
        selected = date.fromisoformat(variable.get())
        self.year,self.month = selected.year,selected.month
        header = ttk.Frame(self);header.pack(fill='x')
        ttk.Button(header,text='‹',width=3,command=lambda:self.move(-1)).pack(side='left')
        self.title = ttk.Label(header,anchor='center');self.title.pack(side='left',fill='x',expand=True)
        ttk.Button(header,text='›',width=3,command=lambda:self.move(1)).pack(side='right')
        self.days = ttk.Frame(self);self.days.pack(fill='x',pady=4)
        self.draw()

    def move(self, delta):
        number = self.year*12+self.month-1+delta
        year,month = number//12,number%12+1
        if 1<=year<=9999:
            self.year,self.month=year,month;self.draw()

    def choose(self, day):
        self.variable.set(date(self.year,self.month,day).isoformat());self.draw()

    def draw(self):
        self.title.config(text=f'{MONTHS[self.language].split()[self.month-1]} {self.year}')
        for child in self.days.winfo_children():child.destroy()
        for column,label in enumerate(WEEKDAYS[self.language].split()):
            self.days.columnconfigure(column,weight=1)
            ttk.Label(self.days,text=label,anchor='center').grid(row=0,column=column,sticky='ew')
        selected=date.fromisoformat(self.variable.get())
        for row,week in enumerate(calendar.monthcalendar(self.year,self.month),1):
            for column,day in enumerate(week):
                if day:
                    button=ttk.Button(self.days,text=str(day),width=3,command=lambda d=day:self.choose(d))
                    button.grid(row=row,column=column,sticky='ew',padx=1,pady=1)
                    if selected == date(self.year,self.month,day):button.state(['pressed'])


class TimePicker(ttk.Frame):
    def __init__(self,master,variable):
        super().__init__(master)
        hour,minute=variable.get().split(':')
        self.hour=tk.StringVar(value=hour);self.minute=tk.StringVar(value=minute)
        ttk.Spinbox(self,values=tuple(f'{i:02}' for i in range(24)),textvariable=self.hour,
                    width=4,wrap=True,state='readonly').pack(side='left')
        ttk.Label(self,text=' : ').pack(side='left')
        ttk.Spinbox(self,values=tuple(f'{i:02}' for i in range(60)),textvariable=self.minute,
                    width=4,wrap=True,state='readonly').pack(side='left')
        def changed(*args):variable.set(self.hour.get()+':'+self.minute.get())
        self.hour.trace_add('write',changed);self.minute.trace_add('write',changed)
