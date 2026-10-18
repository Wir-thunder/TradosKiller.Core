"""
ui.project_settings_dialog - Diálogo de Configurações do Projeto (Project Settings - Alt+F8).

Implementa a tela oficial do SDL Trados Studio para gestão e associação de Memórias de Tradução:
- Language Pairs -> All Language Pairs -> Translation Memory and Automated Translation.
- Adicionar Memórias existentes (.sdltm, .tmx).
- Criar Nova Memória (.sdltm).
- Configurações por memória: Enabled, Lookup, Concordance, Update e Penalty.
"""
from __future__ import annotations

import os
from typing import List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTreeWidget,
    QTreeWidgetItem, QSplitter, QFrame, QMenu, QFileDialog,
    QMessageBox, QSpinBox, QCheckBox
)

from core.attached_tm import AttachedTMConfig
from io_layer.sdltm import create_empty_sdltm, detect_sdltm_langs


class ProjectSettingsDialog(QDialog):
    """Diálogo completo de Project Settings estilo SDL Trados Studio."""

    tms_updated = Signal(list)  # List[AttachedTMConfig]

    def __init__(self, current_tms: List[AttachedTMConfig],
                 src_lang: str = "en-US", tgt_lang: str = "pt-PT",
                 project_name: str = "Projeto Ativo", parent=None) -> None:
        super().__init__(parent)
        self.tms = [AttachedTMConfig(**tm.to_dict()) for tm in current_tms]
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.project_name = project_name

        self.setWindowTitle(f"Project Settings — {self.project_name}")
        self.resize(840, 520)
        self._apply_dark_theme()
        self._build_ui()
        self._populate_table()

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                font-size: 11px;
                color: #cccccc;
            }
            QTreeWidget {
                background-color: #252526;
                color: #dddddd;
                border: 1px solid #333333;
                border-radius: 4px;
                font-size: 11px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: white;
            }
            QTableWidget {
                background-color: #252526;
                gridline-color: #333333;
                selection-background-color: #094771;
                selection-color: white;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #2d2d30;
                color: #8eb4f3;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #3e3e42;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 5px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)

        # ---------------- Painel Esquerdo: Árvore de Configurações
        left_widget = QFrame()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)

        item_proj = QTreeWidgetItem(tree, [f"Project: {self.project_name}"])
        item_pairs = QTreeWidgetItem(item_proj, ["Language Pairs"])
        item_all = QTreeWidgetItem(item_pairs, ["All Language Pairs"])
        self.item_tm = QTreeWidgetItem(item_all, ["Translation Memory and Automated Translation"])
        item_tb = QTreeWidgetItem(item_all, ["Termbases"])

        tree.expandAll()
        tree.setCurrentItem(self.item_tm)
        left_layout.addWidget(tree)
        splitter.addWidget(left_widget)

        # ---------------- Painel Direito: Configuração de TMs
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(8)

        # Cabeçalho da seção
        header_lbl = QLabel("Translation Memory and Automated Translation")
        header_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #8eb4f3;")
        right_layout.addWidget(header_lbl)

        sub_lbl = QLabel(
            "Especifique as bases de memória de tradução associadas a este documento. "
            "Ao confirmar segmentos (Ctrl+Enter), as TMs marcadas com 'Update' serão atualizadas."
        )
        sub_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px; margin-bottom: 4px;")
        sub_lbl.setWordWrap(True)
        right_layout.addWidget(sub_lbl)

        # Barra de Botões: Usar ▾, Remover, Up, Down
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(6)

        self.btn_use = QPushButton("Usar / Use ▾")
        self.btn_use.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                font-weight: bold;
                padding: 5px 14px;
            }
            QPushButton:hover { background-color: #1c97ea; }
        """)
        menu_use = QMenu(self.btn_use)
        act_add_existing = menu_use.addAction("📁 File-based Translation Memory (.sdltm, .tmx)...")
        act_add_existing.triggered.connect(self._add_existing_tm)
        act_create_new = menu_use.addAction("✨ Criar Nova Memória de Tradução (.sdltm)...")
        act_create_new.triggered.connect(self._create_new_tm)
        self.btn_use.setMenu(menu_use)
        btn_bar.addWidget(self.btn_use)

        btn_remove = QPushButton("Remover")
        btn_remove.clicked.connect(self._remove_selected_tm)
        btn_bar.addWidget(btn_remove)

        btn_up = QPushButton("▲ Mover para Cima")
        btn_up.clicked.connect(self._move_up)
        btn_bar.addWidget(btn_up)

        btn_down = QPushButton("▼ Mover para Baixo")
        btn_down.clicked.connect(self._move_down)
        btn_bar.addWidget(btn_down)

        btn_bar.addStretch()
        right_layout.addLayout(btn_bar)

        # Tabela de Memórias Associadas
        self.table_tms = QTableWidget()
        self.table_tms.setColumnCount(7)
        self.table_tms.setHorizontalHeaderLabels([
            "Ativo", "Memória de Tradução", "Tipo", "Consultar (Lookup)",
            "Concordância", "Atualizar (Update)", "Penalidade"
        ])
        self.table_tms.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5, 6):
            self.table_tms.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table_tms.itemChanged.connect(self._on_table_item_changed)
        right_layout.addWidget(self.table_tms)

        splitter.addWidget(right_widget)
        splitter.setSizes([220, 600])
        layout.addWidget(splitter)

        # ---------------- Barra Inferior de Ações
        bot_bar = QHBoxLayout()
        bot_bar.addStretch()

        btn_ok = QPushButton("OK")
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                font-weight: bold;
                padding: 6px 20px;
            }
            QPushButton:hover { background-color: #1c97ea; }
        """)
        btn_ok.clicked.connect(self._on_ok)
        bot_bar.addWidget(btn_ok)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        bot_bar.addWidget(btn_cancel)

        layout.addLayout(bot_bar)

    def _populate_table(self) -> None:
        self.table_tms.blockSignals(True)
        self.table_tms.setRowCount(len(self.tms))

        for row, tm in enumerate(self.tms):
            # Col 0: Ativo (Checkbox)
            item_enabled = QTableWidgetItem()
            item_enabled.setFlags(item_enabled.flags() | Qt.ItemIsUserCheckable)
            item_enabled.setCheckState(Qt.Checked if tm.enabled else Qt.Unchecked)
            self.table_tms.setItem(row, 0, item_enabled)

            # Col 1: Nome da Memória com path no tooltip
            item_name = QTableWidgetItem(tm.name)
            item_name.setToolTip(tm.path)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            self.table_tms.setItem(row, 1, item_name)

            # Col 2: Tipo
            item_type = QTableWidgetItem(tm.file_type)
            item_type.setFlags(item_type.flags() & ~Qt.ItemIsEditable)
            item_type.setForeground(QColor(140, 140, 140))
            self.table_tms.setItem(row, 2, item_type)

            # Col 3: Lookup (Checkbox)
            item_lookup = QTableWidgetItem()
            item_lookup.setFlags(item_lookup.flags() | Qt.ItemIsUserCheckable)
            item_lookup.setCheckState(Qt.Checked if tm.lookup else Qt.Unchecked)
            self.table_tms.setItem(row, 3, item_lookup)

            # Col 4: Concordance (Checkbox)
            item_concordance = QTableWidgetItem()
            item_concordance.setFlags(item_concordance.flags() | Qt.ItemIsUserCheckable)
            item_concordance.setCheckState(Qt.Checked if tm.concordance else Qt.Unchecked)
            self.table_tms.setItem(row, 4, item_concordance)

            # Col 5: Update (Checkbox)
            item_update = QTableWidgetItem()
            item_update.setFlags(item_update.flags() | Qt.ItemIsUserCheckable)
            item_update.setCheckState(Qt.Checked if tm.update else Qt.Unchecked)
            self.table_tms.setItem(row, 5, item_update)

            # Col 6: Penalty (%)
            item_pen = QTableWidgetItem(f"{tm.penalty}%")
            item_pen.setFlags(item_pen.flags() & ~Qt.ItemIsEditable)
            item_pen.setTextAlignment(Qt.AlignCenter)
            self.table_tms.setItem(row, 6, item_pen)

        self.table_tms.blockSignals(False)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if row < 0 or row >= len(self.tms):
            return
        col = item.column()
        tm = self.tms[row]

        if col == 0:
            tm.enabled = (item.checkState() == Qt.Checked)
        elif col == 3:
            tm.lookup = (item.checkState() == Qt.Checked)
        elif col == 4:
            tm.concordance = (item.checkState() == Qt.Checked)
        elif col == 5:
            tm.update = (item.checkState() == Qt.Checked)

    def _add_existing_tm(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Memória de Tradução", "",
            "Memórias de Tradução (*.sdltm *.tmx);;Memória SDLTM (*.sdltm);;TMX Standard (*.tmx)"
        )
        if not path:
            return

        # Checa duplicidade
        if any(os.path.abspath(tm.path) == os.path.abspath(path) for tm in self.tms):
            QMessageBox.information(self, "Aviso", "Esta memória de tradução já está associada ao projeto.")
            return

        new_tm = AttachedTMConfig(path=path)
        self.tms.append(new_tm)
        self._populate_table()

    def _create_new_tm(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Criar Nova Memória SDLTM", "New_Translation_Memory.sdltm",
            "Memória SDLTM (*.sdltm)"
        )
        if not path:
            return

        try:
            create_empty_sdltm(path, src_lang=self.src_lang, tgt_lang=self.tgt_lang)
            new_tm = AttachedTMConfig(path=path, update=True)
            self.tms.append(new_tm)
            self._populate_table()
            QMessageBox.information(self, "Sucesso", f"Nova base .sdltm criada e associada:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível criar a memória:\n{e}")

    def _remove_selected_tm(self) -> None:
        row = self.table_tms.currentRow()
        if row >= 0 and row < len(self.tms):
            self.tms.pop(row)
            self._populate_table()

    def _move_up(self) -> None:
        row = self.table_tms.currentRow()
        if row > 0:
            self.tms[row], self.tms[row - 1] = self.tms[row - 1], self.tms[row]
            self._populate_table()
            self.table_tms.selectRow(row - 1)

    def _move_down(self) -> None:
        row = self.table_tms.currentRow()
        if row >= 0 and row < len(self.tms) - 1:
            self.tms[row], self.tms[row + 1] = self.tms[row + 1], self.tms[row]
            self._populate_table()
            self.table_tms.selectRow(row + 1)

    def _on_ok(self) -> None:
        self.tms_updated.emit(self.tms)
        self.accept()

