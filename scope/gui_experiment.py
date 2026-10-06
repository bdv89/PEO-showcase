"""Composants Qt de la fiche d'expérience : formulaire et fenêtre « Fiche » d'une série.

Logique (lecture/écriture du meta, historique, empreintes) dans
:mod:`scope.experiment` ; ce module ne fait que l'afficher. Import Qt paresseux
(:func:`widgets`), comme ``gui.AcquisitionWorker`` : importer ``scope`` reste
possible sans PyQt.
"""

from __future__ import annotations

import functools
from pathlib import Path

from . import experiment

GROUPS = [
    ("Opérateur", ("operateur", "objectif")),
    ("Échantillon", ("echantillon.id", "echantillon.materiau", "echantillon.surface_cm2",
                     "echantillon.preparation")),
    ("Bain", ("bain.composition", "bain.concentration", "bain.temperature_C", "bain.pH",
              "bain.reference")),
    ("Consigne de pilotage", ("consigne.mode", "consigne.valeur", "consigne.unite",
                              "consigne.frequence_Hz", "consigne.rapport_cyclique",
                              "consigne.polarite", "consigne.duree_prevue")),
    ("Tags et notes", ("tags", "notes")),
]
CHOICES = {
    "consigne.mode": ["", "courant", "tension"],
    "consigne.unite": ["", "A", "A/dm²", "V"],
    "consigne.polarite": ["", "unipolaire", "bipolaire"],
}
PLACEHOLDERS = {
    "echantillon.id": "ex. AL-042 (repart vide à chaque essai)",
    "echantillon.surface_cm2": "ex. 12.5",
    "consigne.duree_prevue": "ex. 20 min",
    "tags": "séparés par des virgules",
}
_REQUIRED = {key for key, _l, req in experiment.FICHE_FIELDS if req}


@functools.lru_cache(maxsize=None)
def widgets():
    """Retourne ``(FicheForm, FicheDialog)`` (classes construites au premier appel)."""
    from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

    class TagCompleter(QtWidgets.QCompleter):
        """Complète le dernier tag d'une liste « a, b, c »."""

        def splitPath(self, path):  # noqa: N802 — override Qt
            return [path.rsplit(",", 1)[-1].strip()]

        def pathFromIndex(self, index):  # noqa: N802 — override Qt
            head = self.widget().text().rsplit(",", 1)
            prefix = head[0].strip() + ", " if len(head) > 1 else ""
            return prefix + super().pathFromIndex(index)

    def repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    class FicheForm(QtWidgets.QWidget):
        """Formulaire de la fiche ; émet ``edited`` à chaque modification."""

        edited = QtCore.Signal()

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.fields: dict[str, QtWidgets.QWidget] = {}
            self._tags_model = QtCore.QStringListModel(self)
            for title, keys in GROUPS:
                box = QtWidgets.QGroupBox(title)
                form = QtWidgets.QFormLayout(box)
                form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
                for key in keys:
                    widget = self._make_field(key)
                    label = experiment.FIELD_LABELS[key] + (" *" if key in _REQUIRED else "")
                    form.addRow(label, widget)
                    self.fields[key] = widget
                layout.addWidget(box)

        def _make_field(self, key):
            if key in CHOICES:
                w = QtWidgets.QComboBox()
                w.setEditable(True)
                w.addItems(CHOICES[key])
                w.currentTextChanged.connect(lambda _t: self.edited.emit())
            elif key == "notes":
                w = QtWidgets.QPlainTextEdit()
                w.setPlaceholderText("Observations, incidents (repart vide à chaque essai)")
                w.setFixedHeight(80)
                w.textChanged.connect(self.edited.emit)
            else:
                w = QtWidgets.QLineEdit()
                w.setPlaceholderText(PLACEHOLDERS.get(key, ""))
                w.textChanged.connect(lambda _t: self.edited.emit())
                if key == "tags":
                    completer = TagCompleter(self._tags_model, w)
                    completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
                    w.setCompleter(completer)
            return w

        # --- valeurs -------------------------------------------------------------
        def get_fiche(self) -> dict:
            fiche = experiment.empty_fiche()
            for key, w in self.fields.items():
                if isinstance(w, QtWidgets.QComboBox):
                    value = w.currentText().strip()
                elif isinstance(w, QtWidgets.QPlainTextEdit):
                    value = w.toPlainText().strip()
                else:
                    value = w.text().strip()
                experiment.set_field(fiche, key, experiment.parse_tags(value) if key == "tags" else value)
            return fiche

        def set_fiche(self, fiche: dict) -> None:
            for key, w in self.fields.items():
                value = experiment.get_field(fiche, key)
                text = ", ".join(value) if key == "tags" else str(value or "")
                w.blockSignals(True)
                if isinstance(w, QtWidgets.QComboBox):
                    w.setCurrentText(text)
                elif isinstance(w, QtWidgets.QPlainTextEdit):
                    w.setPlainText(text)
                else:
                    w.setText(text)
                w.blockSignals(False)
            self.edited.emit()

        def set_tag_suggestions(self, tags: list[str]) -> None:
            self._tags_model.setStringList(tags)

        def set_locked(self, locked: bool) -> None:
            for w in self.fields.values():
                w.setEnabled(not locked)

        def highlight_missing(self, on: bool) -> list[str]:
            """Champs obligatoires vides en rouge (si ``on``) ; retourne leurs clés."""
            missing = experiment.missing_fields(self.get_fiche())
            for key, w in self.fields.items():
                flag = "true" if on and key in missing else "false"
                if w.property("missing") != flag:
                    w.setProperty("missing", flag)
                    repolish(w)
            return missing

    class FicheDialog(QtWidgets.QDialog):
        """Fiche d'une série enregistrée : fiche, résultats post-essai, pièces jointes,
        historique et traçabilité. Chaque enregistrement passe par le meta (journalisé)."""

        def __init__(self, series_dir, tag_suggestions=(), parent=None):
            super().__init__(parent)
            self.series_dir = Path(series_dir)
            self.meta = experiment.load_meta(self.series_dir)
            self.setWindowTitle(f"Fiche — {self.meta['experiment_id']}")
            self.resize(760, 680)
            layout = QtWidgets.QVBoxLayout(self)
            tabs = QtWidgets.QTabWidget()
            layout.addWidget(tabs)

            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            self.form = FicheForm()
            self.form.set_tag_suggestions(list(tag_suggestions))
            self.form.set_fiche(self.meta["fiche"])
            self.form.highlight_missing(True)
            self.form.edited.connect(lambda: self.form.highlight_missing(True))
            scroll.setWidget(self.form)
            tabs.addTab(scroll, "Fiche")
            tabs.addTab(self._build_results(), "Résultats")
            tabs.addTab(self._build_attachments(), "Pièces jointes")
            self.history = QtWidgets.QTableWidget(0, 5)
            self.history.setHorizontalHeaderLabels(["Date", "Utilisateur", "Champ", "Avant", "Après"])
            self.history.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.history.horizontalHeader().setStretchLastSection(True)
            tabs.addTab(self.history, "Historique")
            self.trace = QtWidgets.QPlainTextEdit()
            self.trace.setReadOnly(True)
            self.trace.setStyleSheet("font-family: Consolas, 'SF Mono', monospace;")
            tabs.addTab(self.trace, "Traçabilité")

            buttons = QtWidgets.QHBoxLayout()
            buttons.addStretch(1)
            btn_close = QtWidgets.QPushButton("Fermer")
            btn_close.setProperty("kind", "ghost")
            btn_save = QtWidgets.QPushButton("Enregistrer")
            btn_save.setProperty("kind", "primary")
            btn_close.clicked.connect(self.reject)
            btn_save.clicked.connect(self._save)
            buttons.addWidget(btn_close)
            buttons.addWidget(btn_save)
            layout.addLayout(buttons)
            self._refresh()

        # --- onglets ----------------------------------------------------------------
        def _build_results(self):
            page = QtWidgets.QWidget()
            v = QtWidgets.QVBoxLayout(page)
            v.addWidget(QtWidgets.QLabel("Mesures après l'essai (épaisseur, masse, dureté…)"))
            self.results = QtWidgets.QTableWidget(0, 3)
            self.results.setHorizontalHeaderLabels(["Grandeur", "Valeur", "Unité"])
            self.results.horizontalHeader().setStretchLastSection(True)
            for r in self.meta["resultats"]:
                self._add_result_row(r.get("nom", ""), r.get("valeur", ""), r.get("unite", ""))
            v.addWidget(self.results)
            row = QtWidgets.QHBoxLayout()
            add, remove = QtWidgets.QPushButton("Ajouter une ligne"), QtWidgets.QPushButton("Supprimer la ligne")
            add.setProperty("kind", "ghost")
            remove.setProperty("kind", "ghost")
            add.clicked.connect(lambda: self._add_result_row("", "", ""))
            remove.clicked.connect(lambda: self.results.removeRow(self.results.currentRow()))
            row.addWidget(add)
            row.addWidget(remove)
            row.addStretch(1)
            v.addLayout(row)
            return page

        def _add_result_row(self, nom, valeur, unite):
            r = self.results.rowCount()
            self.results.insertRow(r)
            for c, text in enumerate((nom, valeur, unite)):
                self.results.setItem(r, c, QtWidgets.QTableWidgetItem(str(text)))

        def _results_from_table(self) -> list[dict]:
            out = []
            for r in range(self.results.rowCount()):
                cells = [(self.results.item(r, c).text().strip() if self.results.item(r, c) else "")
                         for c in range(3)]
                if any(cells):
                    out.append(dict(zip(("nom", "valeur", "unite"), cells)))
            return out

        def _build_attachments(self):
            page = QtWidgets.QWidget()
            v = QtWidgets.QVBoxLayout(page)
            v.addWidget(QtWidgets.QLabel("Copiées dans le dossier pieces_jointes/ de la série "
                                         "(jamais écrasées), avec leur empreinte SHA-256."))
            self.attachments = QtWidgets.QListWidget()
            v.addWidget(self.attachments)
            row = QtWidgets.QHBoxLayout()
            add = QtWidgets.QPushButton("Ajouter des fichiers…")
            add.setProperty("kind", "primary")
            open_dir = QtWidgets.QPushButton("Ouvrir le dossier")
            open_dir.setProperty("kind", "ghost")
            add.clicked.connect(self._add_attachments)
            open_dir.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(
                QtCore.QUrl.fromLocalFile(str(self.series_dir / "pieces_jointes"
                                              if (self.series_dir / "pieces_jointes").is_dir()
                                              else self.series_dir))))
            row.addWidget(add)
            row.addWidget(open_dir)
            row.addStretch(1)
            v.addLayout(row)
            return page

        def _add_attachments(self):
            paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Pièces jointes")
            if not paths:
                return
            user, when = experiment.current_user(), experiment.now_iso()
            self.meta = experiment.update_meta(self.series_dir, lambda m: [
                experiment.add_attachment(m, self.series_dir, p, user=user, when=when) for p in paths])
            self._refresh()

        # --- enregistrement / affichage ---------------------------------------------------
        def _save(self):
            user, when = experiment.current_user(), experiment.now_iso()
            fiche, results = self.form.get_fiche(), self._results_from_table()

            def mutate(m):
                experiment.apply_fiche(m, fiche, user=user, when=when)
                experiment.set_results(m, results, user=user, when=when)

            self.meta = experiment.update_meta(self.series_dir, mutate)
            self._refresh()
            self.accept()

        def _refresh(self):
            m = self.meta
            self.attachments.clear()
            for a in m["pieces_jointes"]:
                self.attachments.addItem(f"{a['fichier']}    —    ajouté le {a['ajoute_le']}    "
                                         f"—    sha256 {a['sha256'][:12]}…")
            self.history.setRowCount(0)
            for h in reversed(m["historique"]):
                r = self.history.rowCount()
                self.history.insertRow(r)
                for c, key in enumerate(("date", "utilisateur", "champ", "avant", "apres")):
                    value = h.get(key)
                    text = ", ".join(map(str, value)) if isinstance(value, list) else str(value if value is not None else "")
                    self.history.setItem(r, c, QtWidgets.QTableWidgetItem(text))
            self.history.resizeColumnsToContents()
            report = experiment.verify_checksums(m, self.series_dir) if m["empreintes"] else None
            dates = m.get("dates", {})
            lines = [
                f"Identifiant      : {m['experiment_id']}",
                f"UUID             : {m.get('uuid', '—')}",
                f"Poste / session  : {m.get('station', '—')} / {m.get('utilisateur_windows', '—')}",
                f"Armée            : {dates.get('armee') or '—'}",
                f"Début (signal)   : {dates.get('debut') or '—'}",
                f"Fin              : {dates.get('fin') or '— (en cours ou interrompue)'}",
                f"Captures         : {len(m.get('captures', []))}",
                "",
            ]
            info = m.get("empreintes_info", {})
            if report is None:
                lines.append("Empreintes       : aucune (calculées à l'ouverture dans l'onglet Analyse)")
            else:
                when = info.get("date", "?") + (" (a posteriori)" if info.get("a_posteriori") else "")
                lines.append(f"Empreintes       : {len(m['empreintes'])} fichier(s), {when}")
                verdict = "INTÈGRES" if not (report["modifie"] or report["manquant"]) else "ÉCARTS"
                lines.append(f"Vérification     : {verdict} — {len(report['ok'])} ok")
                for k in ("modifie", "manquant", "nouveau"):
                    if report[k]:
                        lines.append(f"   {k:9}: {', '.join(report[k])}")
            lines += ["", "Analyses :"]
            for a in m["analyses"] or []:
                s = a.get("synthese", {})
                lines.append(f"  {a['date']}  {a['origine']:<13} algo {a['algo_version']}  "
                             f"{s.get('n_ok', '?')}/{s.get('n_captures', '?')} ok  "
                             f"{s.get('mode_majoritaire', '')}" + ("  [FORCÉ]" if a.get("force") else ""))
                absent = a.get("integrite", {}).get("captures_absentes")
                if absent:
                    lines.append(f"      captures retirées : {', '.join(f'#{i}' for i in absent)}")
            if not m["analyses"]:
                lines.append("  aucune")
            self.trace.setPlainText("\n".join(lines))

    return FicheForm, FicheDialog
