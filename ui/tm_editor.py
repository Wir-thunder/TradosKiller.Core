"""
ui.tm_editor - Editor de Memoria (TM) - o "anti-catar-milho".

Janela dedicada a gerir a Translation Memory em massa:
  - busca/filtro instantaneo (fonte / traducao / ambos)
  - edicao inline na tabela (duplo clique)
  - Localizar & Substituir em massa (literal ou regex), com opcao
    de actuar so nos resultados filtrados
  - operacoes em lote: marcar traduzido/aprovado, eliminar
  - exportar TMX / SDLXLIFF
Anti-crash: tabela filtra por ids e so carrega dados das linhas visiveis.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTableView,
    QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tm import TranslationMemory               # noqa: E402
from core.segment import SegState                   # noqa: E402
from ui.tm_model import TmEditorModel               # noqa: E402
from io_layer.tmx_writer import write_tmx           # noqa: E402
from io_layer.sdlxliff_writer import write_sdlxliff # noqa: E402


class TmEditorWindow(QMainWindow):
    def __init__(self, tm: TranslationMemory,
                 src_lang: str = "en-US", tgt_lang: str = "pt-BR",
                 parent=None) -> None:
        super().__init__(parent)
        self.tm = tm
        self._src_lang = src_lang
        self._tgt_lang = tgt_lang
        self.setWindowTitle("Memory Editor — CAT Tool")
        self.resize(1200, 760)
        self.model = TmEditorModel(tm)
        self._apply_dark_theme()
        self._build_ui()
        self._build_menu()
        self._update_status()

    def _apply_dark_theme(self) -> None:
        """Aplica o tema dark consistente com a janela principal."""
        app = QApplication.instance()
        palette = QPalette()
        
        dark_bg = QColor(30, 30, 30)
        darker_bg = QColor(25, 25, 25)
        text_color = QColor(220, 220, 220)
        accent_color = QColor(61, 174, 233)
        
        palette.setColor(QPalette.Window, dark_bg)
        palette.setColor(QPalette.WindowText, text_color)
        palette.setColor(QPalette.Base, darker_bg)
        palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
        palette.setColor(QPalette.Text, text_color)
        palette.setColor(QPalette.Button, dark_bg)
        palette.setColor(QPalette.ButtonText, text_color)
        palette.setColor(QPalette.Highlight, accent_color)
        palette.setColor(QPalette.HighlightedText, Qt.white)
        
        app.setPalette(palette)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("text to search… (filters as you type)")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
            QLineEdit:focus {
                border: 1px solid #3dae73;
            }
        """)
        self.search_box.textChanged.connect(self._on_search)
        bar.addWidget(self.search_box, stretch=3)
        bar.addWidget(QLabel("in:"))
        self.field_box = QComboBox()
        self.field_box.addItems(["both", "source", "translation"])
        self.field_box.setStyleSheet("""
            QComboBox {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self.field_box.currentIndexChanged.connect(self._on_search)
        bar.addWidget(self.field_box)
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("color: #8eb4f3;")
        bar.addWidget(self.lbl_count)
        root.addLayout(bar)

        fr = QHBoxLayout()
        fr.addWidget(QLabel("Find:"))
        self.find_box = QLineEdit()
        self.find_box.setPlaceholderText("search…")
        self.find_box.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        fr.addWidget(self.find_box, stretch=2)
        fr.addWidget(QLabel("Replace with:"))
        self.repl_box = QLineEdit()
        self.repl_box.setPlaceholderText("new text…")
        self.repl_box.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        fr.addWidget(self.repl_box, stretch=2)
        self.cmb_field = QComboBox()
        self.cmb_field.addItems(["translation", "source"])
        self.cmb_field.setStyleSheet("""
            QComboBox {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        fr.addWidget(self.cmb_field)
        self.chk_regex = QCheckBox("regex")
        self.chk_case = QCheckBox("Aa")
        self.chk_case.setToolTip("Case sensitive")
        self.chk_only = QCheckBox("in filter only")
        self.chk_only.setChecked(True)
        self.chk_only.setToolTip("Apply only to visible rows (filtered)")
        fr.addWidget(self.chk_regex)
        fr.addWidget(self.chk_case)
        fr.addWidget(self.chk_only)
        btn_repl = QPushButton("Replace All")
        btn_repl.setStyleSheet("""
            QPushButton {
                background-color: #3dae73;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4dbe83;
            }
            QPushButton:pressed {
                background-color: #2d9e63;
            }
        """)
        btn_repl.clicked.connect(self._on_replace_all)
        fr.addWidget(btn_repl)
        root.addLayout(fr)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked
                                   | QAbstractItemView.SelectedClicked)
        self.table.setStyleSheet("""
            QTableView {
                background-color: #1e1e1e;
                gridline-color: #333;
                selection-background-color: #3dae73;
                selection-color: white;
            }
            QTableView::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #8eb4f3;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #444;
                font-weight: bold;
            }
        """)
        for i, w in enumerate((60, 470, 470, 100, 60)):
            self.table.setColumnWidth(i, w)
        root.addWidget(self.table)

        act = QHBoxLayout()
        btn_tr = QPushButton("Mark Translated")
        btn_tr.setStyleSheet("""
            QPushButton {
                background-color: #3dae73;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4dbe83;
            }
        """)
        btn_tr.clicked.connect(lambda: self._bulk_state(SegState.TRANSLATED))
        act.addWidget(btn_tr)
        btn_ap = QPushButton("Mark Approved")
        btn_ap.setStyleSheet("""
            QPushButton {
                background-color: #3dae73;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4dbe83;
            }
        """)
        btn_ap.clicked.connect(lambda: self._bulk_state(SegState.APPROVED))
        act.addWidget(btn_ap)
        btn_del = QPushButton("Delete Selected")
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #f75c4c;
            }
        """)
        btn_del.clicked.connect(self._on_delete)
        act.addWidget(btn_del)
        act.addStretch()
        root.addLayout(act)

        self.statusBar().showMessage("Memory Editor ready.")

    def _build_menu(self) -> None:
        mb = self.menuBar()
        m_exp = mb.addMenu("&Exportar")
        a_tmx = QAction("Exportar &TMX…", self)
        a_tmx.triggered.connect(lambda: self.export("tmx"))
        m_exp.addAction(a_tmx)
        a_sdl = QAction("Exportar &SDLXLIFF…", self)
        a_sdl.triggered.connect(lambda: self.export("sdlxliff"))
        m_exp.addAction(a_sdl)

    def _on_search(self) -> None:
        q = self.search_box.text().strip()
        field = {"both": "both", "source": "source", "translation": "target"}[
            self.field_box.currentText()]
        self.model.apply_filter(q, field)
        self._update_status()

    def _update_status(self) -> None:
        vis = self.model.rowCount()
        total = self.tm.count()
        tr = self.tm.count_translated()
        self.lbl_count.setText(f"{vis} de {total}  ·  traduzidos: {tr}")

    def _selected_ids(self) -> list[int]:
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            rid = self.model.id_at(idx.row())
            if rid >= 0:
                ids.append(rid)
        return ids

    def _on_replace_all(self) -> None:
        find = self.find_box.text()
        if not find:
            QMessageBox.warning(self, "Replace", "Enter text to find.")
            return
        repl = self.repl_box.text()
        field = "source" if self.cmb_field.currentText() == "source" else "target"
        only = self.model.visible_ids() if self.chk_only.isChecked() else None
        n = self.tm.bulk_replace(find, repl, field=field,
                                 case_sensitive=self.chk_case.isChecked(),
                                 use_regex=self.chk_regex.isChecked(), only_ids=only)
        self.model.refresh()
        self._update_status()
        scope = "in filter" if only is not None else "in entire TM"
        QMessageBox.information(
            self, "Replace", f"{n} occurrence(s) replaced {scope}.")

    def _bulk_state(self, state: SegState) -> None:
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "State", "Select rows in the table.")
            return
        n = self.tm.set_state(ids, state)
        self.model.refresh()
        self._update_status()
        self.statusBar().showMessage(f"{n} row(s) marked as {state.value}.")

    def _on_delete(self) -> None:
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "Delete", "Select rows in the table.")
            return
        resp = QMessageBox.question(
            self, "Delete",
            f"Delete {len(ids)} segment(s)? This cannot be undone.")
        if resp != QMessageBox.Yes:
            return
        n = self.tm.delete_ids(ids)
        self._on_search()
        self._update_status()
        self.statusBar().showMessage(f"{n} segment(s) deleted.")

    def export(self, kind: str) -> None:
        if kind == "tmx":
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar TMX", "", "TMX (*.tmx)")
            if not path:
                return
            n = write_tmx(self.tm, path, self._src_lang, self._tgt_lang)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar SDLXLIFF", "", "SDLXLIFF (*.sdlxliff)")
            if not path:
                return
            n = write_sdlxliff(self.tm, path, self._src_lang, self._tgt_lang,
                               original=os.path.basename(path))
        self.statusBar().showMessage(
            f"Exportado: {n} unidades -> {os.path.basename(path)}")
