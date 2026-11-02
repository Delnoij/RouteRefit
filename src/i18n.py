# SPDX-License-Identifier: GPL-3.0-only
"""Presentation-only localization. Route data and internal setting keys stay intact."""

import json
import re
from functools import lru_cache
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

LANGUAGES = {"nl": "Nederlands", "en": "English", "de": "Deutsch", "fr": "Français", "es": "Español", "pt": "Português"}
language = "nl"
catalog = {}
_installed = False
_fragments = {}
_fragment_pattern = None


def configure(code, folder):
    global language, catalog, _fragments, _fragment_pattern
    language = code if code in LANGUAGES else "nl"
    path = Path(folder) / "locales" / f"{language}.json"
    catalog = (
        json.loads(path.read_text(encoding="utf-8")) if language != "nl" and path.exists() else {}
    )
    _fragments = {k[1:]: v for k, v in catalog.items() if k.startswith("~")}
    _fragment_pattern = (
        re.compile("|".join(re.escape(k) for k in sorted(_fragments, key=len, reverse=True)))
        if _fragments
        else None
    )
    _translate_text.cache_clear()


def tr(value):
    if not isinstance(value, str) or language == "nl":
        return value
    return _translate_text(value)


@lru_cache(maxsize=4096)
def _translate_text(value):
    if value in catalog:
        return catalog[value]
    if "\n" in value:
        return "\n".join(tr(line) for line in value.split("\n"))
    if value.strip() in catalog:
        return (
            value[: len(value) - len(value.lstrip())]
            + catalog[value.strip()]
            + value[len(value.rstrip()) :]
        )
    # Fragments are deliberately marked, to avoid translating arbitrary names/paths.
    if not _fragment_pattern:
        return value
    return _fragment_pattern.sub(lambda m: _fragments[m.group()], value)


class DisplayVar(tk.StringVar):
    """Store source text for application logic; expose translated text to Tcl widgets."""

    def __init__(self, *args, **kwargs):
        self.source = kwargs.get("value", "")
        if "value" in kwargs:
            kwargs["value"] = tr(kwargs["value"])
        super().__init__(*args, **kwargs)

    def set(self, value):
        self.source = value
        super().set(tr(value))

    def get(self):
        return self.source


def options(opts):
    opts = dict(opts or {})
    for key in ("text", "label", "title"):
        if key in opts:
            opts[key] = tr(opts[key])
    return opts


def install():
    global _installed
    if _installed:
        return
    _installed = True
    original = tk.BaseWidget.__init__

    def init(self, master, widgetName, cnf={}, kw={}, extra=()):
        return original(self, master, widgetName, options(cnf), options(kw), extra)

    tk.BaseWidget.__init__ = init
    original_configure = tk.Misc._configure

    def config(self, cmd, cnf, kw):
        if isinstance(cnf, dict):
            cnf = options(cnf)
        return original_configure(self, cmd, cnf, options(kw))

    tk.Misc._configure = config
    original_menu = tk.Menu.add

    def menu(self, itemType, cnf={}, **kw):
        return original_menu(self, itemType, options(cnf), **options(kw))

    tk.Menu.add = menu
    original_heading = ttk.Treeview.heading

    def heading(self, column, option=None, **kw):
        return original_heading(self, column, option, **options(kw))

    ttk.Treeview.heading = heading
    original_insert = ttk.Treeview.insert

    def insert(self, parent, index, iid=None, **kw):
        if "values" in kw:
            kw["values"] = tuple(
                tr(v) if i in getattr(self, "localized_columns", ()) else v
                for i, v in enumerate(kw["values"])
            )
        return original_insert(self, parent, index, iid, **kw)

    ttk.Treeview.insert = insert
    original_item = ttk.Treeview.item

    def item(self, item, option=None, **kw):
        if "values" in kw:
            kw["values"] = tuple(
                tr(v) if i in getattr(self, "localized_columns", ()) else v
                for i, v in enumerate(kw["values"])
            )
        return original_item(self, item, option, **kw)

    ttk.Treeview.item = item
    original_text = tk.Text.insert

    def text(self, index, chars, *args):
        return original_text(
            self, index, tr(chars) if getattr(self, "localize", False) else chars, *args
        )

    tk.Text.insert = text
    original_create = tk.Canvas._create

    def create(self, itemType, args, kw):
        return original_create(self, itemType, args, options(kw))

    tk.Canvas._create = create
    original_title = tk.Wm.wm_title

    def title(self, string=None):
        return original_title(self, tr(string))

    tk.Wm.title = tk.Wm.wm_title = title
    original_show = messagebox._show

    def show(title=None, message=None, _icon=None, _type=None, **kw):
        return original_show(tr(title), tr(message), _icon, _type, **kw)

    messagebox._show = show
    original_dialog = filedialog._Dialog.__init__

    def dialog(self, master=None, **kw):
        if "title" in kw:
            kw["title"] = tr(kw["title"])
        if "filetypes" in kw:
            kw["filetypes"] = [(tr(label), extensions) for label, extensions in kw["filetypes"]]
        return original_dialog(self, master, **kw)

    filedialog._Dialog.__init__ = dialog
    original_combo = ttk.Combobox.__init__

    def combo(self, master=None, **kw):
        internal = kw.get("textvariable")
        values = kw.get("values", ())
        if internal is not None and values and language != "nl":
            display = tk.StringVar(master, value=tr(internal.get()))
            kw["textvariable"] = display
            kw["values"] = [tr(v) for v in values]
            original_combo(self, master, **kw)
            self._locale_variables = (internal, display)
            busy = [False]

            def from_internal(*args):
                if not busy[0]:
                    busy[0] = True
                    try:
                        display.set(tr(internal.get()))
                    finally:
                        busy[0] = False

            def from_display(*args):
                if not busy[0]:
                    busy[0] = True
                    try:
                        internal.set(
                            next((v for v in values if tr(v) == display.get()), display.get())
                        )
                    finally:
                        busy[0] = False

            a = internal.trace_add("write", from_internal)
            b = display.trace_add("write", from_display)

            def cleanup(event):
                if event.widget == self:
                    internal.trace_remove("write", a)
                    display.trace_remove("write", b)

            self.bind("<Destroy>", cleanup, add="+")
        else:
            original_combo(self, master, **kw)

    ttk.Combobox.__init__ = combo


def initialize(base, resources, override=None):
    code = override
    if code is None:
        try:
            code = json.loads((Path(base) / "voorkeuren.json").read_text(encoding="utf-8")).get(
                "language", "nl"
            )
        except (OSError, ValueError, AttributeError):
            code = "nl"
    configure(code, resources)
    install()
