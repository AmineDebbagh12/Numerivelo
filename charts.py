from __future__ import annotations

import re
import tkinter as tk
from collections import Counter
from datetime import date
from tkinter import ttk

from action_keywords import find_components


DIMENSIONS = ("Date", "Nom / prénom", "Action")
COMPONENT_VIEW = "Composants vélo"


def summarize(rows: list[tuple[str, ...]], column: int) -> list[tuple[str, int]]:
    groups: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for row in rows:
        if not any(value.strip() for value in row):
            continue
        value = " ".join(row[column].split())
        if column == 0:
            match = re.fullmatch(r"(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2}|\d{4})", value)
            if match:
                day, month, year = map(int, match.groups())
                if len(match[3]) == 2:
                    year += 2000
                try:
                    value = date(year, month, day).isoformat()
                except ValueError:
                    pass
        key = value.casefold()
        groups[key] += 1
        labels.setdefault(key, value)

    def order(key: str) -> tuple:
        if column == 0:
            return (not bool(key), key)
        return (not bool(key), -groups[key], key)

    return [(labels[key] or "Non renseigné", groups[key]) for key in sorted(groups, key=order)]


def summarize_components(rows: list[tuple[str, ...]]) -> list[tuple[str, int]]:
    counts = Counter(component for row in rows for component in find_components(row[2]))
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))


class ChartWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, rows: list[tuple[str, ...]]) -> None:
        super().__init__(parent)
        self.title("Visualisations du registre")
        self.geometry("780x520")
        self.minsize(480, 260)
        self.rows = rows
        panel = ttk.Frame(self, padding=12)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        self.selector = ttk.Combobox(panel, values=(*DIMENSIONS, COMPONENT_VIEW), state="readonly")
        self.selector.current(0)
        self.selector.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.canvas = tk.Canvas(panel, background="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(panel, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.selector.bind("<<ComboboxSelected>>", self._change_dimension)
        self.canvas.bind("<Configure>", self._draw)
        self._draw()

    def _change_dimension(self, _event: tk.Event) -> None:
        self.canvas.yview_moveto(0)
        self._draw()

    def _draw(self, _event: tk.Event | None = None) -> None:
        canvas = self.canvas
        canvas.delete("all")
        if self.selector.get() == COMPONENT_VIEW:
            groups = summarize_components(self.rows)
            title = "Interventions par composant" if groups else "Aucun composant reconnu dans les actions"
        else:
            groups = summarize(self.rows, self.selector.current())
            title = f"Interventions comptées : {sum(n for _, n in groups)}"
        width = max(canvas.winfo_width(), 450)
        canvas.create_text(16, 18, text=title, anchor="w")
        bar_start = int(width * 0.43)
        max_count = max((n for _, n in groups), default=1)
        y = 40
        for label, count in groups:
            item = canvas.create_text(16, y, text=label, width=bar_start - 32, anchor="nw")
            _, _, _, bottom = canvas.bbox(item)
            end = bar_start + max(1, int((width - bar_start - 65) * count / max_count))
            canvas.create_rectangle(bar_start, y + 2, end, y + 19, fill="#246c70", outline="")
            canvas.create_text(end + 8, y + 10, text=str(count), anchor="w")
            y = max(bottom + 12, y + 31)
        canvas.configure(scrollregion=(0, 0, width, y))
