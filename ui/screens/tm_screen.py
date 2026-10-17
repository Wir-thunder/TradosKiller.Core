"""
ui.screens.tm_screen - Translation Memories management screen.

Screen for managing translation memories with search, filter,
find & replace, and bulk operations.
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QTableView, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame,
)

from core.tm import TranslationMemory
from core.segment import SegState
from ui.tm_model import TmEditorModel
from io_layer.tmx import iter_tmx, detect_tmx_langs
from io_layer.sdlxliff import iter_sdlxliff, detect_sdlxliff_langs
from io_layer.sdltm import iter_sdltm, detect_sdltm_langs, write_sdltm
from io_layer.tmx_writer import write_tmx
from io_layer.sdlxliff_writer import write_sdlxliff


class TmScreen(QWidget):
    """Translation Memories management screen."""
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tm: Optional[TranslationMemory] = None
        self._src_lang = "en-US"
        self._tgt_lang = "pt-BR"
        self.model: Optional[TmEditorModel] = None
        
        self._apply_dark_theme()
        self._build_ui()
    
    def _apply_dark_theme(self) -> None:
        """Apply dark theme consistent with main window."""
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
        palette.setColor(QPalette.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.Button, QColor(30, 30, 30))
        palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.Highlight, QColor(61, 174, 233))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        self.setPalette(palette)
    
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("Translation Memories")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #8eb4f3;")
        layout.addWidget(header)
        
        # Main splitter
        from PySide6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel: Load TM
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        load_label = QLabel("Load Translation Memory")
        load_label.setStyleSheet("font-weight: bold; color: #ddd;")
        left_layout.addWidget(load_label)
        
        btn_create = QPushButton("➕ Nova Memória (.sdltm)")
        btn_create.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f;
                color: #93c5fd;
                border: 1px solid #3b82f6;
                border-radius: 4px;
                padding: 8px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
                color: white;
            }
        """)
        btn_create.clicked.connect(self._create_new_sdltm)
        left_layout.addWidget(btn_create)

        btn_load = QPushButton("Load TMX/SDLXLIFF/SDLTM")
        btn_load.setStyleSheet("""
            QPushButton {
                background-color: #3dae73;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #4dbe83;
            }
        """)
        btn_load.clicked.connect(self._load_file)
        left_layout.addWidget(btn_load)
        
        # TM info
        self.tm_info = QLabel("No TM loaded")
        self.tm_info.setStyleSheet("color: #aaa; font-size: 10px;")
        self.tm_info.setWordWrap(True)
        left_layout.addWidget(self.tm_info)
        
        left_layout.addStretch()
        
        splitter.addWidget(left_panel)
        
        # Right panel: TM editor
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        
        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
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
        search_layout.addWidget(self.search_box, stretch=3)
        
        search_layout.addWidget(QLabel("in:"))
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
        search_layout.addWidget(self.field_box)
        
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet("color: #8eb4f3;")
        search_layout.addWidget(self.lbl_count)
        
        right_layout.addLayout(search_layout)
        
        # Find & Replace
        fr_layout = QHBoxLayout()
        fr_layout.addWidget(QLabel("Find:"))
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
        fr_layout.addWidget(self.find_box, stretch=2)
        
        fr_layout.addWidget(QLabel("Replace with:"))
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
        fr_layout.addWidget(self.repl_box, stretch=2)
        
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
        fr_layout.addWidget(self.cmb_field)
        
        self.chk_regex = QCheckBox("regex")
        self.chk_case = QCheckBox("Aa")
        self.chk_case.setToolTip("Case sensitive")
        self.chk_only = QCheckBox("in filter only")
        self.chk_only.setChecked(True)
        self.chk_only.setToolTip("Apply only to visible rows (filtered)")
        fr_layout.addWidget(self.chk_regex)
        fr_layout.addWidget(self.chk_case)
        fr_layout.addWidget(self.chk_only)
        
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
        """)
        btn_repl.clicked.connect(self._on_replace_all)
        fr_layout.addWidget(btn_repl)
        
        right_layout.addLayout(fr_layout)
        
        # Table
        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
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
        right_layout.addWidget(self.table)
        
        # Action buttons
        act_layout = QHBoxLayout()
        
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
        act_layout.addWidget(btn_tr)
        
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
        act_layout.addWidget(btn_ap)
        
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
        act_layout.addWidget(btn_del)
        
        act_layout.addStretch()
        
        # Export buttons
        btn_tmx = QPushButton("Export TMX")
        btn_tmx.setStyleSheet("""
            QPushButton {
                background-color: #8eb4f3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #9ec4ff;
            }
        """)
        btn_tmx.clicked.connect(lambda: self.export("tmx"))
        act_layout.addWidget(btn_tmx)
        
        btn_sdl = QPushButton("Export SDLXLIFF")
        btn_sdl.setStyleSheet("""
            QPushButton {
                background-color: #8eb4f3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #9ec4ff;
            }
        """)
        btn_sdl.clicked.connect(lambda: self.export("sdlxliff"))
        act_layout.addWidget(btn_sdl)

        btn_sdltm = QPushButton("Export SDLTM")
        btn_sdltm.setStyleSheet("""
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
        btn_sdltm.clicked.connect(lambda: self.export("sdltm"))
        act_layout.addWidget(btn_sdltm)
        
        right_layout.addLayout(act_layout)
        
        splitter.addWidget(right_panel)
        splitter.setSizes([250, 750])
        
        layout.addWidget(splitter)
    
    def _create_new_sdltm(self) -> None:
        """Abre diálogo para criar uma nova memória .sdltm vazia e a carrega."""
        from ui.create_sdltm_dialog import CreateSdltmDialog
        dlg = CreateSdltmDialog(default_src=self._src_lang, default_tgt=self._tgt_lang, parent=self)
        if dlg.exec() and dlg.created_path:
            self.load_tm_file(dlg.created_path)

    def _load_file(self) -> None:
        """Load a translation memory file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Translation Memory", "",
            "Translation Memories (*.sdltm *.tmx *.sdlxliff *.xlf *.xliff);;SDL TM (*.sdltm);;TMX (*.tmx);;SDLXLIFF (*.sdlxliff);;All Files (*.*)"
        )
        if not path:
            return
        
        ext = os.path.splitext(path)[1].lower()
        
        if ext not in (".tmx", ".sdlxliff", ".xlf", ".xliff", ".sdltm"):
            QMessageBox.warning(self, "Unsupported File", "Only SDLTM, TMX, and SDLXLIFF files are supported.")
            return
        
        try:
            import uuid
            db = f"{os.path.splitext(path)[0]}.tm-{uuid.uuid4().hex[:10]}.db"
            tm = TranslationMemory(db)
            
            if ext == ".tmx":
                src, tgt = detect_tmx_langs(path)
                n = tm.add_many(iter_tmx(path, src, tgt), src or "", tgt or "")
            elif ext == ".sdltm":
                src, tgt = detect_sdltm_langs(path)
                n = tm.add_many(iter_sdltm(path, src, tgt), src or "", tgt or "")
            else:
                src, tgt = detect_sdlxliff_langs(path)
                n = tm.add_many(iter_sdlxliff(path), src or "", tgt or "")
            
            tm.rebuild_fts()
            
            self.tm = tm
            self._src_lang = src or "en-US"
            self._tgt_lang = tgt or "pt-BR"
            
            self.model = TmEditorModel(tm)
            self.table.setModel(self.model)
            
            from PySide6.QtWidgets import QAbstractItemView
            self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
            
            for i, w in enumerate((60, 470, 470, 100, 60)):
                self.table.setColumnWidth(i, w)
            
            self.tm_info.setText(f"Loaded: {os.path.basename(path)}\nSegments: {n:,}\nSource: {self._src_lang}\nTarget: {self._tgt_lang}")
            self._update_status()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")
    
    def _on_search(self) -> None:
        """Handle search/filter."""
        if not self.model:
            return
        
        q = self.search_box.text().strip()
        field = {"both": "both", "source": "source", "translation": "target"}[
            self.field_box.currentText()]
        self.model.apply_filter(q, field)
        self._update_status()
    
    def _update_status(self) -> None:
        """Update status label."""
        if not self.tm or not self.model:
            self.lbl_count.setText("No TM loaded")
            return
        
        vis = self.model.rowCount()
        total = self.tm.count()
        tr = self.tm.count_translated()
        self.lbl_count.setText(f"{vis} of {total}  ·  translated: {tr}")
    
    def _selected_ids(self) -> list[int]:
        """Get selected row IDs."""
        if not self.model:
            return []
        
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            rid = self.model.id_at(idx.row())
            if rid >= 0:
                ids.append(rid)
        return ids
    
    def _on_replace_all(self) -> None:
        """Handle replace all."""
        if not self.tm:
            QMessageBox.warning(self, "Replace", "No TM loaded.")
            return
        
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
        QMessageBox.information(self, "Replace", f"{n} occurrence(s) replaced {scope}.")
    
    def _bulk_state(self, state: SegState) -> None:
        """Mark selected rows with a state."""
        if not self.tm:
            return
        
        ids = self._selected_ids()
        if not ids:
            QMessageBox.information(self, "State", "Select rows in the table.")
            return
        
        n = self.tm.set_state(ids, state)
        self.model.refresh()
        self._update_status()
    
    def _on_delete(self) -> None:
        """Delete selected rows."""
        if not self.tm:
            return
        
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
    
    def export(self, kind: str) -> None:
        """Export TM."""
        if not self.tm:
            QMessageBox.warning(self, "Export", "No TM loaded.")
            return
        
        if kind == "tmx":
            path, _ = QFileDialog.getSaveFileName(
                self, "Export TMX", "", "TMX (*.tmx)")
            if not path:
                return
            n = write_tmx(self.tm, path, self._src_lang, self._tgt_lang)
        elif kind == "sdltm":
            path, _ = QFileDialog.getSaveFileName(
                self, "Export SDL TM", "", "SDL TM (*.sdltm)")
            if not path:
                return
            n = write_sdltm(self.tm, path, self._src_lang, self._tgt_lang)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export SDLXLIFF", "", "SDLXLIFF (*.sdlxliff)")
            if not path:
                return
            n = write_sdlxliff(self.tm, path, self._src_lang, self._tgt_lang,
                               original=os.path.basename(path))
        
        QMessageBox.information(self, "Export", f"Exported {n} segments to:\n{path}")
