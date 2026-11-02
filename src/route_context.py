# SPDX-License-Identifier: GPL-3.0-only
"""Direct map actions for unwanted detours and local route repair."""

import math
import tkinter as tk


def nearest_line_point(segments, pixel, x, y, after=None):
    candidates = []
    for si, segment in enumerate(segments):
        for i, (a, b) in enumerate(zip(segment, segment[1:])):
            ax, ay = pixel(a)
            bx, by = pixel(b)
            dx, dy = bx - ax, by - ay
            den = dx * dx + dy * dy
            f = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / den)) if den else 0
            gap = math.hypot(x - ax - f * dx, y - ay - f * dy)
            if gap <= 24:
                candidates.append((gap, si, i + (f > 0.5)))
    if not candidates:
        return None
    candidates.sort()
    if after is not None:
        later = [
            row
            for row in candidates
            if row[1] == after[0] and row[2] > after[1] and row[0] <= candidates[0][0] + 3
        ]
        if later:
            candidates = later
    return tuple(candidates[0][1:])


class RouteContextUI:
    def route_context_menu(self, event):
        if self.busy or not self.track:
            return "break"
        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None
        hit = nearest_line_point(self.edit_segments, self.canvas.pixel, event.x, event.y)
        end_hit = nearest_line_point(
            self.edit_segments, self.canvas.pixel, event.x, event.y, after=self.range_anchor
        )
        issue_index = None
        for i, issue in enumerate(self.auto_issues):
            p = self.edit_segments[issue.segment][issue.start]
            px, py = self.canvas.pixel(p)
            if math.hypot(event.x - px, event.y - py) < 50:
                issue_index = i
                break
            if hit and issue.segment == hit[0] and issue.start <= hit[1] <= issue.end:
                issue_index = i
                break
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Automatisch uitlijnen", command=self.automatic_alignment_action)
        menu.add_command(label="Handmatig uitlijnen", command=self.manual_alignment)
        menu.add_separator()
        anchor = None
        for si, indices in enumerate(self.anchor_indices):
            for index in indices:
                px,py = self.canvas.pixel(self.edit_segments[si][index])
                if math.hypot(event.x-px,event.y-py) <= 20:
                    anchor = (si,index)
                    break
            if anchor: break
        if anchor:
            si,index = anchor
            controls = self.anchor_indices[si]
            menu.add_command(label="Hoofdpunt verwijderen en opnieuw verbinden",
                command=lambda si=si,index=index: self.quick_anchor_edit(si,index,remove=True),
                state="disabled" if index in (controls[0],controls[-1]) else "normal")
        elif hit:
            menu.add_command(label="Hoofdpunt toevoegen",command=lambda: self.context_add_anchor(hit))
        if hit:
            si,index=hit
            controls=self.anchor_indices[si]
            left=max((i for i in controls if i<=index),default=0)
            right=next((i for i in controls if i>left),len(self.edit_segments[si])-1)
            menu.add_command(label="Dit stuk opnieuw verbinden",
                             command=lambda si=si,left=left,right=right: self.quick_section_alignment(si,left,right))
        position=self.canvas.point(event.x,event.y)
        menu.add_command(label="Waypoint hier toevoegen…",command=lambda:self.add_waypoint(position))
        if issue_index is not None:
            menu.add_command(
                label="Dit probleem met tussenpunten aanpassen…",
                command=lambda: self.context_problem(issue_index, True),
            )
            menu.add_command(
                label="Herstelvoorstel voor dit probleem zoeken…",
                command=lambda: self.context_problem(issue_index, False),
            )
            menu.add_separator()
        if hit:
            menu.add_command(
                label="Begin te verwijderen stuk hier", command=lambda: self.context_start(hit)
            )
        if (
            self.range_anchor is not None
            and end_hit
            and end_hit[0] == self.range_anchor[0]
            and end_hit != self.range_anchor
        ):
            menu.add_command(
                label="Eind te verwijderen stuk hier…", command=lambda: self.context_end(end_hit)
            )
        if self.range_selection:
            menu.add_command(label="Gekozen stuk opnieuw uitlijnen",
                             command=lambda:self.quick_section_alignment(*self.range_selection))
            menu.add_command(
                label="Gekozen stuk met tussenpunten vervangen…",
                command=self.replace_range_with_via,
            )
            menu.add_command(label="Gekozen stuk handmatig behouden", command=self.keep_range)
        if len(self.edit_segments) > 1:
            menu.add_command(label="Routedelen verbinden…", command=self.connect_segments)
        menu.add_separator()
        menu.add_command(
            label="Ongedaan maken",
            command=self.undo,
            state="normal" if self.history else "disabled",
        )
        menu.add_command(label="Hele route tonen", command=self.reset_view)
        menu.add_command(label="Uitlijnen stoppen", command=self.stop_alignment)
        # Keep a reference for deterministic UI tests and later disposal.
        old = getattr(self, "route_popup", None)
        if old is not None:
            old.destroy()
        self.route_popup = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def context_add_anchor(self, hit):
        si,index=hit
        if index in self.anchor_indices[si]: return
        self.remember()
        self.anchor_indices[si]=sorted(set(self.anchor_indices[si]+[index]))
        self.selection=hit
        self.edit_revision+=1
        self.invalidate()
        self.manual_alignment()

    def context_start(self, hit):
        self.mapmode.set("range")
        self.canvas.set_mode("range")
        self.range_anchor = hit
        self.range_selection = None
        self.selection = hit
        self.pointinfo.set(
            "Begin gekozen. Klik met rechts bij het einde van de omweg en kies Eind te verwijderen stuk hier…"
        )
        self.draw()

    def context_end(self, hit):
        if self.busy or self.range_anchor is None or hit[0] != self.range_anchor[0]:
            return
        a, b = sorted((self.range_anchor[1], hit[1]))
        if a == b:
            return
        self.range_selection = (hit[0], a, b)
        self.range_anchor = None
        self.draw()
        self.quick_section_alignment(*self.range_selection)

    def context_problem(self, index, guided):
        if self.busy or not 0 <= index < len(self.auto_issues):
            return
        self.issue_cursor = index
        p = self.auto_issues[index]
        self.range_selection = (p.segment, p.start, p.end)
        self.range_anchor = None
        if guided:
            self.replace_range_with_via()
        else:
            self.recover_range()

    def replace_range_with_via(self):
        if self.busy or not self.range_selection:
            return
        si, a, b = self.range_selection
        if a < b:
            self.connection_editor(si, section=(a, b))
