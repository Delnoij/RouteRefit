# SPDX-License-Identifier: GPL-3.0-only
"""Local waypoint form and portable photo attachments."""

from __future__ import annotations
from pathlib import Path
from dataclasses import replace
import hashlib, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.parse import quote

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def validate_photo(path):
    p = Path(path)
    if not p.is_file() or p.suffix.lower() not in PHOTO_SUFFIXES:
        raise ValueError("Kies een JPG, PNG, WebP of GIF.")
    if p.stat().st_size > 25_000_000:
        raise ValueError("Kies een foto kleiner dan 25 MB.")
    head = p.open("rb")
    with head:
        raw = head.read(16)
    if not (
        raw.startswith(b"\xff\xd8\xff")
        or raw.startswith(b"\x89PNG\r\n\x1a\n")
        or raw.startswith((b"GIF87a", b"GIF89a"))
        or raw.startswith(b"RIFF")
        and raw[8:12] == b"WEBP"
    ):
        raise ValueError("Dit bestand is geen herkenbare foto.")
    try:
        from PIL import Image

        with Image.open(p) as image:
            if image.width * image.height > 60_000_000:
                raise ValueError("Kies een foto van maximaal 60 megapixel.")
            image.verify()
    except ImportError:
        pass
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("De foto kan niet worden gelezen.") from exc
    return p


def portable_photo_links(waypoints, gpx_path, approved_keys):
    """Only explicitly selected/approved local photos are included, never remote links."""
    dest = Path(gpx_path)
    folder = dest.parent / (dest.stem + "-fotos")
    links = {}
    prepared = []
    for w in waypoints:
        if not w.photo or w.key not in approved_keys:
            continue
        p = validate_photo(w.photo)
        raw = p.read_bytes()
        name = hashlib.sha256(raw).hexdigest()[:24] + p.suffix.lower()
        target = folder / name
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("Een fotobestand met deze naam bestaat al en wijkt af.")
        links[w.key] = quote(folder.name + "/" + name, safe="/")
        prepared.append((target, raw))
    # Validate all attachments before writing any of them.
    for p, raw in prepared:
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            with p.open("xb") as handle:
                handle.write(raw)
    return links


class WaypointDialog(tk.Toplevel):
    def __init__(self, parent, waypoint, on_save, photo_approved=False):
        super().__init__(parent)
        self.title("Waypoint · naam, foto en omschrijving")
        self.transient(parent)
        self.grab_set()
        self.waypoint = waypoint
        self.on_save = on_save
        self.approved_photo = photo_approved
        self.photo = waypoint.photo
        self.name = tk.StringVar(value=waypoint.name)
        self.picture = None
        box = ttk.Frame(self, padding=18)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Naam").pack(anchor="w")
        ttk.Entry(box, textvariable=self.name, width=60).pack(fill="x", pady=(3, 12))
        ttk.Label(box, text=f"Positie  {waypoint.lat:.6f}, {waypoint.lon:.6f}").pack(anchor="w")
        ttk.Label(box, text="Omschrijving · maximaal 1.500 tekens").pack(anchor="w", pady=(12, 4))
        self.text = tk.Text(box, width=65, height=7, wrap="word", font=("Segoe UI", 10))
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", waypoint.description)
        self.count = ttk.Label(box)
        self.count.pack(anchor="e", pady=4)
        self.text.bind("<<Modified>>", self.modified)
        controls = ttk.Frame(box)
        controls.pack(fill="x", pady=6)
        ttk.Button(controls, text="Foto kiezen…", command=self.choose_photo).pack(side="left")
        ttk.Button(controls, text="Foto weghalen", command=self.remove_photo).pack(
            side="left", padx=6
        )
        self.photo_name = ttk.Label(box, wraplength=550)
        self.photo_name.pack(anchor="w", pady=4)
        self.preview = ttk.Label(box)
        self.preview.pack(pady=4)
        buttons = ttk.Frame(box)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Annuleren", command=self.destroy).pack(side="right")
        self.save_button = ttk.Button(buttons, text="Waypoint bewaren", command=self.save)
        self.save_button.pack(side="right", padx=8)
        self.modified()
        self.show_photo()
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 80}+{parent.winfo_rooty() + 45}")

    def modified(self, event=None):
        count = len(self.text.get("1.0", "end-1c"))
        self.count.config(
            text=f"{count:,} / 1.500 tekens", foreground="#b7342d" if count > 1500 else "#536557"
        )
        if hasattr(self, "save_button"):
            self.save_button.config(state="disabled" if count > 1500 else "normal")
        self.text.edit_modified(False)

    def choose_photo(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Foto bij waypoint kiezen",
            filetypes=[("Foto", "*.jpg *.jpeg *.png *.webp *.gif")],
        )
        if path:
            try:
                validate_photo(path)
            except ValueError as exc:
                return messagebox.showerror("Foto niet toegevoegd", str(exc), parent=self)
            self.photo = str(Path(path).resolve())
            self.approved_photo = True
            self.show_photo()

    def remove_photo(self):
        self.photo = ""
        self.approved_photo = False
        self.show_photo()

    def show_photo(self):
        self.picture = None
        self.preview.config(image="", text="")
        self.photo_name.config(text=Path(self.photo).name if self.photo else "Geen foto toegevoegd")
        if not self.photo or not self.approved_photo:
            return
        try:
            from PIL import Image, ImageOps, ImageTk

            with Image.open(validate_photo(self.photo)) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((500, 140))
                self.picture = ImageTk.PhotoImage(image)
            self.preview.config(image=self.picture)
        except Exception:
            self.preview.config(text="Fotobestand toegevoegd; voorbeeld niet beschikbaar.")

    def save(self):
        waypoint = replace(
            self.waypoint,
            name=self.name.get().strip(),
            description=self.text.get("1.0", "end-1c"),
            photo=self.photo,
        )
        try:
            waypoint.validate()
            if self.photo and self.approved_photo:
                validate_photo(self.photo)
            self.on_save(waypoint, self.approved_photo)
        except Exception as exc:
            return messagebox.showerror("Waypoint niet bewaard", str(exc), parent=self)
        self.destroy()
