from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from charts import ChartWindow, DIMENSIONS
from ocr import LocalOcr, OcrError, normalize_date

SUPPORTED_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
FIELDS = DIMENSIONS


class OcrExcelApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Registre manuscrit")
        self.root.geometry("1000x620")
        self.image_paths: list[Path] = []
        self.events: queue.Queue[tuple] = queue.Queue()
        self.is_processing = False

        self._build_ui()
        self.root.after(100, self._read_events)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        ttk.Label(
            container,
            text="Choisissez le dossier contenant les photos du registre.",
        ).grid(row=0, column=0, sticky="w")
        folder_row = ttk.Frame(container)
        folder_row.grid(row=1, column=0, sticky="ew", pady=(6, 12))
        folder_row.columnconfigure(0, weight=1)
        self.folder_var = tk.StringVar(value="Aucun dossier sélectionné")
        ttk.Label(folder_row, textvariable=self.folder_var).grid(row=0, column=0, sticky="w")
        self.folder_button = ttk.Button(
            folder_row, text="Choisir un dossier…", command=self._choose_folder
        )
        self.folder_button.grid(row=0, column=1, padx=(8, 0))
        self.process_button = ttk.Button(
            folder_row,
            text="Lire les images",
            command=self._start_processing,
            state="disabled",
        )
        self.process_button.grid(row=0, column=2, padx=(8, 0))

        table_frame = ttk.Frame(container)
        table_frame.grid(row=2, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(table_frame, columns=("date", "name", "action"), show="headings")
        for key, title, width in (
            ("date", "Date", 150),
            ("name", FIELDS[1], 220),
            ("action", "Action", 560),
        ):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=90, stretch=key == "action")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.table.bind("<Double-1>", self._edit_cell)

        controls = ttk.Frame(container)
        controls.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(controls, text="Ajouter une ligne", command=self._add_row).pack(side="left")
        ttk.Button(controls, text="Supprimer la sélection", command=self._delete_rows).pack(
            side="left", padx=(8, 0)
        )
        self.export_button = ttk.Button(
            controls, text="Exporter vers Excel…", command=self._export, state="disabled"
        )
        self.export_button.pack(side="right")
        self.chart_button = ttk.Button(
            controls, text="Visualiser les données…", command=self._show_charts, state="disabled"
        )
        self.chart_button.pack(side="right", padx=(0, 8))

        status_row = ttk.Frame(container)
        status_row.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        status_row.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Prêt")
        ttk.Label(status_row, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status_row, mode="determinate", length=220)
        self.progress.grid(row=0, column=1, sticky="e")
        ttk.Label(
            container,
            text="Vérifiez et corrigez les résultats avant l'export (double-cliquez sur une cellule).",
        ).grid(row=5, column=0, sticky="w", pady=(8, 0))

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choisir le dossier des images")
        if not selected:
            return
        folder = Path(selected)
        self.image_paths = sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        self.folder_var.set(str(folder))
        if not self.image_paths:
            self.process_button.configure(state="disabled")
            messagebox.showwarning(
                "Aucune image trouvée",
                "Ce dossier ne contient aucune image prise en charge "
                "(JPG, PNG, TIFF, BMP ou WebP).",
            )
            return
        self.process_button.configure(state="normal")
        self.status_var.set(f"{len(self.image_paths)} image(s) prête(s)")

    def _start_processing(self) -> None:
        if self.is_processing or not self.image_paths:
            return
        self.is_processing = True
        self.process_button.configure(state="disabled")
        self.folder_button.configure(state="disabled")
        self._update_data_buttons()
        self.progress.configure(maximum=len(self.image_paths), value=0)
        self.status_var.set("Traitement local en cours…")
        self._clear_table()
        threading.Thread(target=self._process_images, daemon=True).start()

    def _process_images(self) -> None:
        ocr = LocalOcr()
        failures: list[str] = []
        for index, image_path in enumerate(self.image_paths, start=1):
            try:
                records = ocr.extract(image_path)
            except OcrError as exc:
                failures.append(f"{image_path.name} : {exc}")
            else:
                self.events.put(("records", records))
            self.events.put(("progress", index, image_path.name))
        self.events.put(("finished", failures))

    def _read_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "records":
                    for record in event[1]:
                        self.table.insert(
                            "",
                            "end",
                            values=(record["date"], record["name"], record["action"]),
                        )
                elif event[0] == "progress":
                    self.progress.configure(value=event[1])
                    self.status_var.set(f"Image {event[1]} sur {len(self.image_paths)} : {event[2]}")
                elif event[0] == "finished":
                    self._finish_processing(event[1])
        except queue.Empty:
            pass
        self.root.after(100, self._read_events)

    def _finish_processing(self, failures: list[str]) -> None:
        self.is_processing = False
        self.process_button.configure(state="normal" if self.image_paths else "disabled")
        self.folder_button.configure(state="normal")
        self._update_data_buttons()
        if failures:
            self.status_var.set(f"Terminé avec {len(failures)} erreur(s)")
            messagebox.showwarning(
                "Traitement terminé avec des erreurs",
                "\n".join(failures[:8])
                + (f"\n… et {len(failures) - 8} autre(s)." if len(failures) > 8 else ""),
            )
        else:
            self.status_var.set(f"Terminé — {len(self.table.get_children())} ligne(s) à vérifier")

    def _edit_cell(self, event: tk.Event) -> None:
        region = self.table.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.table.identify_row(event.y)
        column_id = self.table.identify_column(event.x)
        if not row_id or not column_id:
            return
        bounds = self.table.bbox(row_id, column_id)
        if not bounds:
            return
        x, y, width, height = bounds
        column_index = int(column_id[1:]) - 1
        current_value = self.table.item(row_id, "values")[column_index]
        editor = ttk.Entry(self.table)
        editor.insert(0, current_value)
        editor.select_range(0, "end")
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()

        def save_edit(_event: tk.Event | None = None) -> None:
            if not editor.winfo_exists():
                return
            if self.table.exists(row_id):
                values = list(self.table.item(row_id, "values"))
                value = editor.get()
                values[column_index] = normalize_date(value) if column_index == 0 else value
                self.table.item(row_id, values=values)
            editor.destroy()
            self._update_data_buttons()

        editor.bind("<Return>", save_edit)
        editor.bind("<FocusOut>", save_edit)
        editor.bind("<Escape>", lambda _event: editor.destroy())

    def _add_row(self) -> None:
        self.table.insert("", "end", values=("", "", ""))
        self._update_data_buttons()

    def _delete_rows(self) -> None:
        selected = self.table.selection()
        if not selected:
            return
        for row_id in selected:
            self.table.delete(row_id)
        self._update_data_buttons()

    def _clear_table(self) -> None:
        for row_id in self.table.get_children():
            self.table.delete(row_id)

    def _rows(self) -> list[tuple[str, ...]]:
        return [
            tuple(self.table.set(row_id, field) for field in self.table["columns"])
            for row_id in self.table.get_children()
        ]

    def _update_data_buttons(self) -> None:
        state = "normal" if not self.is_processing and self.table.get_children() else "disabled"
        self.export_button.configure(state=state)
        self.chart_button.configure(state=state)

    def _show_charts(self) -> None:
        ChartWindow(self.root, self._rows())

    def _export(self) -> None:
        rows = self._rows()
        if not rows:
            messagebox.showwarning("Aucune donnée", "Il n'y a aucune ligne à exporter.")
            return
        destination = filedialog.asksaveasfilename(
            title="Enregistrer le fichier Excel",
            defaultextension=".xlsx",
            filetypes=[("Classeur Excel", "*.xlsx")],
            initialfile="registre_ocr.xlsx",
        )
        if not destination:
            return

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Registre"
        sheet.append(FIELDS)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row_number, row in enumerate(rows, start=2):
            for column, value in enumerate(row, start=1):
                sheet.cell(row_number, column, value).data_type = "s"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.column_dimensions["A"].width = 16
        sheet.column_dimensions["B"].width = 28
        sheet.column_dimensions["C"].width = 70
        for row in sheet.iter_rows(min_row=2):
            row[2].alignment = Alignment(wrap_text=True, vertical="top")

        try:
            workbook.save(destination)
        except OSError as exc:
            messagebox.showerror("Échec de l'export", f"Impossible d'enregistrer le fichier : {exc}")
            return
        self.status_var.set(f"Fichier Excel enregistré : {destination}")
        messagebox.showinfo("Export terminé", "Le fichier Excel a bien été créé.")


def main() -> None:
    root = tk.Tk()
    OcrExcelApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
