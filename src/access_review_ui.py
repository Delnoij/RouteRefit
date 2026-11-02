# SPDX-License-Identifier: GPL-3.0-only
"""Explicit, route-local access review with unchanged geometry and an audit trail."""

import copy
import math
from datetime import datetime, timezone
from tkinter import messagebox
from routing_repair import leg_key
from access_review import access_only_issues, ACCESS_REVIEW_WARNING

ACCESS_REVIEW_PROMPT = (
    "Toegangsmeldingen accepteren voor deze route?\n\n"
    "Alleen problemen die door OSM-toegangstags ontstaan worden geaccepteerd. "
    "De bestaande lijn, hoogtes en tijden blijven behouden. Dit maakt een verboden weg niet toegestaan.\n\n"
    "Neem plaatselijke regels en bebording in acht. Controleer zelf of je hier met de gekozen activiteit mag komen. "
    "Je keuze wordt in het controlerapport vermeld en kan met Ongedaan worden teruggedraaid."
)


class AccessReviewUI:
    def clear_access_reviews(self):
        for record in getattr(self, "access_reviews", []):
            self.manual_sections.difference_update(tuple(k) for k in record["added_manual_keys"])
        self.access_reviews = []

    def restore_access_reviews(self, saved, mode):
        self.access_reviews = []
        records = saved.get("accepted_access_issues", [])
        if not isinstance(records, list):
            return
        for record in records[:1000]:
            if not isinstance(record, dict) or record.get("mode") != mode:
                continue
            keys = record.get("added_manual_keys")
            if not isinstance(keys, list) or not keys:
                continue
            if not all(isinstance(k, list) and len(k) == 5 and
                       all(type(v) in (int, float) and math.isfinite(v) for v in k) and
                       tuple(k) in self.manual_sections for k in keys):
                continue
            self.access_reviews.append(dict(
                mode=mode, reason=str(record.get("reason", ""))[:2000],
                accepted_at=str(record.get("accepted_at", ""))[:80],
                added_manual_keys=copy.deepcopy(keys), geometry_changed=False,
                local_rules_warning=ACCESS_REVIEW_WARNING,
            ))

    def accept_access_issues(self):
        if self.busy or not self.track:
            return
        if not self.roadmap or self.auto_checked_key != self.routing_key():
            return messagebox.showinfo("Eerst controleren", "Kies eerst Opnieuw controleren; daarna kun je toegangsmeldingen accepteren.")
        if not self.auto_issues:
            return messagebox.showinfo("Toegangsmeldingen", "Er zijn geen open uitlijnproblemen om te beoordelen.")
        if not messagebox.askyesno("Toegangsmeldingen accepteren", ACCESS_REVIEW_PROMPT, default="no", parent=self):
            return
        key = self.routing_key()
        segments = [list(s) for s in self.edit_segments]
        controls = [list(row) for row in self.anchor_indices]
        issues = copy.deepcopy(self.auto_issues)
        mode = self.routing_mode()
        radius = float(self.snapradius.get().replace(",", "."))
        road = self.roadmap
        private = self.private_roads.get()

        def done(accepted):
            if key != self.routing_key():
                return
            if not accepted:
                return messagebox.showinfo("Toegangsmeldingen", "Geen probleem kon uitsluitend aan toegangstags worden toegeschreven. De meldingen en de lijn blijven behouden.")
            self.history.append(dict(
                action="access_review", manual_sections=set(self.manual_sections),
                access_reviews=copy.deepcopy(getattr(self, "access_reviews", [])),
                anchors=[list(row) for row in self.anchor_indices],
                issues=copy.deepcopy(self.auto_issues), routing_key=key,
            ))
            if len(self.history) > 20:
                self.history.pop(0)
            for issue in accepted:
                si, start, end = issue.segment, issue.start, issue.end
                anchors = sorted(set(self.anchor_indices[si] + [start, end]))
                self.anchor_indices[si] = anchors
                added = []
                for a, b in zip(anchors, anchors[1:]):
                    if start <= a < b <= end:
                        manual = leg_key(si, self.edit_segments[si][a], self.edit_segments[si][b])
                        if manual not in self.manual_sections:
                            self.manual_sections.add(manual)
                            added.append(list(manual))
                self.access_reviews.append(dict(
                    mode=mode, reason=issue.reason,
                    accepted_at=datetime.now(timezone.utc).isoformat(),
                    added_manual_keys=added, geometry_changed=False,
                    local_rules_warning=ACCESS_REVIEW_WARNING,
                ))
            self.auto_issues = [issue for issue in self.auto_issues if issue not in accepted]
            self.invalidate()
            self.dirty = True
            self.issue = None
            self.range_selection = None
            self.range_anchor = None
            self.repairbar.pack_forget()
            self.auto_summary.set(f"{len(self.auto_issues)} open problemen")
            self.status.set("Toegangsmeldingen geaccepteerd; de lijn is ongewijzigd. Neem plaatselijke regels in acht.")
            self.pointinfo.set(ACCESS_REVIEW_WARNING)
            self.messages.insert("end", "\n" + ACCESS_REVIEW_WARNING)
            self.draw()
            if self.auto_issues:
                self.navigate_problem(0)

        self.job(lambda: access_only_issues(road, segments, controls, issues, mode, radius, private),
                 done, "Toegangsmeldingen beoordelen zonder de lijn te wijzigen…")

    def undo_access_review(self, state):
        self.manual_sections = state["manual_sections"]
        self.access_reviews = state["access_reviews"]
        self.anchor_indices = state["anchors"]
        current = state["routing_key"] == self.routing_key()
        if not current:
            self.clear_access_reviews()
        self.auto_issues = state["issues"] if current else []
        self.auto_checked_key = self.routing_key() if current else None
        self.invalidate()
        self.dirty = True
        self.issue = None
        self.range_selection = None
        self.auto_summary.set(f"{len(self.auto_issues)} open problemen")
        self.pointinfo.set("Toegangsbeoordeling ongedaan gemaakt. De lijn is ongewijzigd.")
        self.status.set("Toegangsbeoordeling ongedaan gemaakt. De lijn is ongewijzigd.")
        self.draw()
