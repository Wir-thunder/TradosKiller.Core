"""
ui.screens.files_screen - Ecrã de Ficheiros do Projeto estilo SDL Trados Studio (Files View).

Reproduz fielmente o visual oficial do Trados Studio:
- Painel lateral esquerdo retrátil 'Filter Files' e 'Project folders' (Árvore de pastas do projeto)
- Tabela de Ficheiros com barras de progresso nativas embutidas por célula (ProgressBarCellWidget):
  * Name, Words, Status, Progress (Barra visual colorida com %), Size, Usage, File Type Ident., Path, Cloud Task
- Painel inferior de detalhes com abas na base (South):
  * File Details (Ficha de propriedades do ficheiro)
  * Analysis Statistics (Balanço de palavras e correspondências de TM)
  * Confirmation Statistics (Status de tradução, rascunhos, confirmados)
  * Task History (Histórico de tarefas executadas)
  * File Attributes (Atributos e metadados)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QFrame, QProgressBar, QMenu, QSplitter,
    QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, QCheckBox,
    QTabWidget
)

from core.project import Project, ProjectFile


class ProgressBarCellWidget(QWidget):
    """Célula com barra de progresso gráfica colorida estilo SDL Trados Studio."""

    def __init__(self, percent: float, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(0)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        val = max(0, min(100, int(percent)))
        self.bar.setValue(val)
        self.bar.setFormat(f"{val}%")
        self.bar.setAlignment(Qt.AlignCenter)

        # Cores autênticas do Trados Studio:
        # 100%: ciano vibrante #00a4e4
        # > 0%: ouro/laranja #e67e22
        # 0%: fundo escuro
        if val >= 100:
            chunk_color = "#00a4e4"
        elif val > 0:
            chunk_color = "#e67e22"
        else:
            chunk_color = "transparent"

        self.bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid #3e3e42;
                border-radius: 2px;
                background-color: #252526;
                color: #ffffff;
                font-size: 10px;
                font-weight: bold;
                text-align: center;
                height: 16px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color};
                border-radius: 1px;
            }}
        """)
        layout.addWidget(self.bar)


class FilesScreen(QWidget):
    """Ecrã de Ficheiros do Projeto estilo SDL Trados Studio (Files View)."""

    open_file_in_editor = Signal(str)    # caminho absoluto do ficheiro para abrir
    batch_tasks_requested = Signal(str)  # nome da tarefa em lote

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_project: Optional[Project] = None
        self._all_files: List[ProjectFile] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QTableWidget {
                background-color: #1e1e1e;
                gridline-color: #2d2d30;
                selection-background-color: #094771;
                selection-color: white;
                font-size: 11px;
                border: 1px solid #333333;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #2d2d30;
                color: #8eb4f3;
                padding: 6px;
                border: none;
                border-right: 1px solid #3e3e42;
                border-bottom: 1px solid #3e3e42;
                font-weight: bold;
                font-size: 11px;
            }
            QLineEdit, QComboBox {
                background-color: #252526;
                color: #e0e0e0;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                padding: 4px;
                font-size: 11px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #007acc;
            }
            QTreeWidget {
                background-color: #202022;
                color: #dddddd;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                font-size: 11px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: white;
            }
            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #252526;
                color: #aaaaaa;
                border: 1px solid #333333;
                padding: 5px 12px;
                font-size: 11px;
                margin-top: 1px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #8eb4f3;
                border-bottom: 2px solid #007acc;
                font-weight: bold;
            }
        """)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(0)

        self.main_hsplitter = QSplitter(Qt.Horizontal)

        # =========================================================================
        # PAINEL LATERAL ESQUERDO: "Filter Files" & "Project folders"
        # =========================================================================
        self.left_filter_panel = QFrame()
        self.left_filter_panel.setFixedWidth(230)
        self.left_filter_panel.setStyleSheet("background-color: #252526; border-right: 1px solid #333333;")
        lp_layout = QVBoxLayout(self.left_filter_panel)
        lp_layout.setContentsMargins(8, 8, 8, 8)
        lp_layout.setSpacing(8)

        # Cabeçalho "Files" com botão de recolher
        hdr_layout = QHBoxLayout()
        hdr_title = QLabel("Files")
        hdr_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #ffffff;")
        hdr_layout.addWidget(hdr_title)
        hdr_layout.addStretch()

        self.btn_collapse_left = QPushButton("◀")
        self.btn_collapse_left.setFixedSize(22, 22)
        self.btn_collapse_left.setToolTip("Ocultar painel de filtros")
        self.btn_collapse_left.setStyleSheet("""
            QPushButton {
                background-color: #333; color: #aaa; border: 1px solid #444; border-radius: 3px; font-size: 10px;
            }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        self.btn_collapse_left.clicked.connect(self._toggle_filter_panel)
        hdr_layout.addWidget(self.btn_collapse_left)
        lp_layout.addLayout(hdr_layout)

        # Grupo 1: Filter Files
        grp_filter = QFrame()
        grp_filter.setStyleSheet("border: 1px solid #3e3e42; border-radius: 4px; padding: 6px; background-color: #202022;")
        gf_layout = QVBoxLayout(grp_filter)
        gf_layout.setContentsMargins(4, 6, 4, 6)
        gf_layout.setSpacing(6)

        lbl_filter_title = QLabel("Filter Files")
        lbl_filter_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 10px; border: none;")
        gf_layout.addWidget(lbl_filter_title)

        gf_layout.addWidget(QLabel("File name:"))
        self.txt_filter_name = QLineEdit()
        self.txt_filter_name.setPlaceholderText("Filter files...")
        self.txt_filter_name.textChanged.connect(self._apply_filter)
        gf_layout.addWidget(self.txt_filter_name)

        gf_layout.addWidget(QLabel("Language:"))
        self.combo_filter_lang = QComboBox()
        self.combo_filter_lang.addItems(["🇧🇷 Portuguese (Brazil)", "🇺🇸 English (United States)", "All Languages"])
        self.combo_filter_lang.currentIndexChanged.connect(self._apply_filter)
        gf_layout.addWidget(self.combo_filter_lang)

        lp_layout.addWidget(grp_filter)

        # Grupo 2: Project folders (Árvore de pastas do Trados Studio)
        grp_tree = QFrame()
        grp_tree.setStyleSheet("border: 1px solid #3e3e42; border-radius: 4px; padding: 6px; background-color: #202022;")
        gt_layout = QVBoxLayout(grp_tree)
        gt_layout.setContentsMargins(4, 6, 4, 6)
        gt_layout.setSpacing(6)

        lbl_tree_title = QLabel("Project folders")
        lbl_tree_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 10px; border: none;")
        gt_layout.addWidget(lbl_tree_title)

        self.tree_folders = QTreeWidget()
        self.tree_folders.setHeaderHidden(True)
        self.tree_folders.setFixedHeight(140)
        gt_layout.addWidget(self.tree_folders)

        self.chk_subfolders = QCheckBox("Include subfolders")
        self.chk_subfolders.setChecked(True)
        self.chk_subfolders.setStyleSheet("border: none; font-size: 11px; color: #cccccc;")
        gt_layout.addWidget(self.chk_subfolders)

        lp_layout.addWidget(grp_tree)
        lp_layout.addStretch()

        self.main_hsplitter.addWidget(self.left_filter_panel)

        # =========================================================================
        # CONTEÚDO PRINCIPAL (Splitter Vertical: Tabela de Ficheiros + Detalhes)
        # =========================================================================
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(6, 4, 6, 4)
        center_layout.setSpacing(4)

        # Barra de Ações Rápidas de Ficheiro
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 0, 0, 0)
        action_bar.setSpacing(6)

        self.btn_open_editor = QPushButton("▶ Open For Translation")
        self.btn_open_editor.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: white; border: none;
                border-radius: 3px; padding: 5px 14px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #1c97ea; }
        """)
        self.btn_open_editor.clicked.connect(self._open_selected_file)
        action_bar.addWidget(self.btn_open_editor)

        btn_review = QPushButton("🔍 Open For Review")
        btn_review.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: #ffffff; border: 1px solid #444444;
                border-radius: 3px; padding: 5px 12px; font-size: 11px;
            }
            QPushButton:hover { background-color: #444444; }
        """)
        btn_review.clicked.connect(self._open_selected_file)
        action_bar.addWidget(btn_review)

        btn_batch = QPushButton("⚙ Batch Tasks ▾")
        btn_batch.setStyleSheet("""
            QPushButton {
                background-color: #252526; color: #8eb4f3; border: 1px solid #007acc;
                border-radius: 3px; padding: 5px 12px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #007acc; color: white; }
        """)
        menu = QMenu(btn_batch)
        menu.setStyleSheet("QMenu { background-color: #252526; color: #e0e0e0; border: 1px solid #3e3e42; padding: 4px; } QMenu::item:selected { background-color: #007acc; color: white; }")
        menu.addAction("📊 Analyze Files...", lambda: self.batch_tasks_requested.emit("analyze"))
        menu.addAction("⚡ Pre-translate Files...", lambda: self.batch_tasks_requested.emit("pretranslate"))
        menu.addAction("🔎 Verify QA (F8)...", lambda: self.batch_tasks_requested.emit("verify"))
        menu.addAction("💾 Update Main Translation Memories...", lambda: self.batch_tasks_requested.emit("update_tm"))
        btn_batch.clicked.connect(lambda: menu.exec(btn_batch.mapToGlobal(btn_batch.rect().bottomLeft())))
        action_bar.addWidget(btn_batch)

        btn_add = QPushButton("➕ Add Files...")
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: #ffffff; border: 1px solid #444444;
                border-radius: 3px; padding: 5px 12px; font-size: 11px;
            }
            QPushButton:hover { background-color: #444444; }
        """)
        btn_add.clicked.connect(self._add_file)
        action_bar.addWidget(btn_add)

        action_bar.addStretch()

        self.lbl_file_count = QLabel("0 ficheiros")
        self.lbl_file_count.setStyleSheet("color: #888888; font-size: 11px;")
        action_bar.addWidget(self.lbl_file_count)

        center_layout.addLayout(action_bar)

        # Splitter Vertical: Tabela em cima, Detalhes embaixo
        self.main_vsplitter = QSplitter(Qt.Vertical)

        # ---------------- 1. Tabela de Ficheiros Trados Studio
        self.table_files = QTableWidget()
        self.table_files.setColumnCount(10)
        self.table_files.setHorizontalHeaderLabels([
            "Name", "Segments", "Words", "Status", "Progress", "Size", "Usage", "File Type Ident.", "Path", "Cloud Task"
        ])
        self.table_files.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_files.setAlternatingRowColors(True)
        self.table_files.verticalHeader().setDefaultSectionSize(26)
        self.table_files.horizontalHeader().setStretchLastSection(True)
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 5, 6, 7, 9):
            self.table_files.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table_files.horizontalHeader().resizeSection(4, 100)  # Progress bar column width
        self.table_files.horizontalHeader().setSectionResizeMode(8, QHeaderView.Stretch)

        self.table_files.itemSelectionChanged.connect(self._on_file_selection_changed)
        self.table_files.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table_files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_files.customContextMenuRequested.connect(self._show_context_menu)

        self.main_vsplitter.addWidget(self.table_files)

        # ---------------- 2. Painel Inferior de Detalhes (File Attributes & Tabs)
        self.details_container = QFrame()
        self.details_container.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333; border-radius: 4px;")
        det_vlayout = QVBoxLayout(self.details_container)
        det_vlayout.setContentsMargins(6, 4, 6, 4)
        det_vlayout.setSpacing(4)

        det_header = QHBoxLayout()
        det_header.setContentsMargins(0, 0, 0, 0)
        self.lbl_details_title = QLabel("File Attributes")
        self.lbl_details_title.setStyleSheet("font-weight: bold; color: #8eb4f3; font-size: 11px;")
        det_header.addWidget(self.lbl_details_title)
        det_header.addStretch()

        btn_close_details = QPushButton("✕")
        btn_close_details.setFixedSize(18, 18)
        btn_close_details.setToolTip("Ocultar painel de atributos")
        btn_close_details.setStyleSheet("""
            QPushButton { background-color: transparent; color: #888; border: none; font-size: 11px; }
            QPushButton:hover { color: #fff; background-color: #c0392b; border-radius: 2px; }
        """)
        btn_close_details.clicked.connect(lambda: self.details_container.setVisible(False))
        det_header.addWidget(btn_close_details)
        det_vlayout.addLayout(det_header)

        # QTabWidget com as abas posicionadas na base (South)
        self.tab_details = QTabWidget()
        self.tab_details.setTabPosition(QTabWidget.South)

        # Aba 1: File Details
        self.table_prop_details = QTableWidget()
        self.table_prop_details.setColumnCount(2)
        self.table_prop_details.setHorizontalHeaderLabels(["Property", "Value"])
        self.table_prop_details.horizontalHeader().setStretchLastSection(True)
        self.table_prop_details.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_prop_details.verticalHeader().setVisible(False)
        self.table_prop_details.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_prop_details, "📄 File Details")

        # Aba 2: Analysis Statistics
        self.table_analysis_stats = QTableWidget()
        self.table_analysis_stats.setColumnCount(4)
        self.table_analysis_stats.setHorizontalHeaderLabels(["Match Band", "Segments", "Words", "Percentage"])
        self.table_analysis_stats.horizontalHeader().setStretchLastSection(True)
        self.table_analysis_stats.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_analysis_stats.verticalHeader().setVisible(False)
        self.table_analysis_stats.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_analysis_stats, "📈 Analysis Statistics")

        # Aba 3: Confirmation Statistics
        self.table_confirm_stats = QTableWidget()
        self.table_confirm_stats.setColumnCount(4)
        self.table_confirm_stats.setHorizontalHeaderLabels(["Status", "Segments", "Words", "Percentage"])
        self.table_confirm_stats.horizontalHeader().setStretchLastSection(True)
        self.table_confirm_stats.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_confirm_stats.verticalHeader().setVisible(False)
        self.table_confirm_stats.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_confirm_stats, "📊 Confirmation Statistics")

        # Aba 4: Task History
        self.table_task_history = QTableWidget()
        self.table_task_history.setColumnCount(4)
        self.table_task_history.setHorizontalHeaderLabels(["Task", "Status", "Date / Time", "User"])
        self.table_task_history.horizontalHeader().setStretchLastSection(True)
        self.table_task_history.verticalHeader().setVisible(False)
        self.table_task_history.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_task_history, "🕒 Task History")

        # Aba 5: File Attributes
        self.table_attributes = QTableWidget()
        self.table_attributes.setColumnCount(2)
        self.table_attributes.setHorizontalHeaderLabels(["Attribute", "Value"])
        self.table_attributes.horizontalHeader().setStretchLastSection(True)
        self.table_attributes.verticalHeader().setVisible(False)
        self.table_attributes.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_attributes, "🏷 File Attributes")

        det_vlayout.addWidget(self.tab_details)
        self.main_vsplitter.addWidget(self.details_container)

        self.main_vsplitter.setSizes([340, 220])
        center_layout.addWidget(self.main_vsplitter)

        self.main_hsplitter.addWidget(center_container)
        self.main_hsplitter.setSizes([230, 850])

        root_layout.addWidget(self.main_hsplitter)

    def _toggle_filter_panel(self) -> None:
        vis = not self.left_filter_panel.isVisible()
        self.left_filter_panel.setVisible(vis)
        self.btn_collapse_left.setText("◀" if vis else "▶")

    # =========================================================================
    # GESTÃO DO PROJETO ATIVO
    # =========================================================================
    def set_project(self, project: Project) -> None:
        self._current_project = project
        self._all_files = project.files

        # Atualiza a árvore de pastas
        self.tree_folders.clear()
        root_item = QTreeWidgetItem(self.tree_folders, [f"📁  {project.name}"])
        root_item.setExpanded(True)
        QTreeWidgetItem(root_item, ["📁  My Tasks"])
        QTreeWidgetItem(root_item, ["📁  Sent Tasks"])

        # Idiomas no dropdown
        self.combo_filter_lang.blockSignals(True)
        self.combo_filter_lang.clear()
        if project.target_lang:
            self.combo_filter_lang.addItem(f"🇧🇷 {project.target_lang}")
        if project.source_lang:
            self.combo_filter_lang.addItem(f"🇺🇸 {project.source_lang}")
        self.combo_filter_lang.addItem("All Languages")
        self.combo_filter_lang.blockSignals(False)

        self._apply_filter()

        if self.table_files.rowCount() > 0:
            self.table_files.selectRow(0)

    def _apply_filter(self) -> None:
        if not self._current_project:
            self.table_files.setRowCount(0)
            self.lbl_file_count.setText("0 ficheiros")
            return

        name_q = self.txt_filter_name.text().strip().lower()
        lang_sel = self.combo_filter_lang.currentText()

        filtered = []
        for f in self._all_files:
            fname = os.path.basename(f.path).lower()
            if name_q and name_q not in fname:
                continue

            # Se filtrando por target lang específico (e o arquivo pertence à pasta desse idioma)
            if "🇧🇷" in lang_sel and "pt-br" in lang_sel.lower():
                if "pt-br" not in f.path.lower() and f.target_lang and "pt" not in f.target_lang.lower():
                    continue
            elif "🇺🇸" in lang_sel and "en-us" in lang_sel.lower():
                if "en-us" not in f.path.lower() and f.source_lang and "en" not in f.source_lang.lower():
                    continue

            filtered.append(f)

        # Se o filtro de idioma não retornou nada, mostre todos os ficheiros do projeto
        if not filtered and self._all_files:
            filtered = self._all_files

        self._populate_table(filtered)
        self.lbl_file_count.setText(f"{len(filtered)} ficheiro(s)")

    def _populate_table(self, files: List[ProjectFile]) -> None:
        self.table_files.setRowCount(len(files))

        for row, f in enumerate(files):
            # Col 0: Name com ícone por extensão
            base = os.path.basename(f.path)
            ext = os.path.splitext(f.path)[1].lower()
            if ".xl" in base.lower():
                icon_str = "📊"
            elif ".doc" in base.lower():
                icon_str = "📝"
            else:
                icon_str = "📄"

            name_item = QTableWidgetItem(f"{icon_str}  {base}")
            name_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            name_item.setData(Qt.UserRole, f.path)
            self.table_files.setItem(row, 0, name_item)

            # Col 1: Segments
            s_str = f"{f.segment_count:,}" if f.segment_count > 0 else "-"
            s_item = QTableWidgetItem(s_str)
            s_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_files.setItem(row, 1, s_item)

            # Col 2: Words
            w_str = f"{f.words:,}" if f.words > 0 else "-"
            w_item = QTableWidgetItem(w_str)
            w_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_files.setItem(row, 2, w_item)

            # Col 3: Status
            status_item = QTableWidgetItem(f.status)
            status_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            if f.status == "Translated" or f.progress >= 100:
                status_item.setForeground(QColor(46, 204, 113))
            else:
                status_item.setForeground(QColor(52, 152, 219))
            self.table_files.setItem(row, 3, status_item)

            # Col 4: Progress (In-cell custom colored progress bar widget)
            p_widget = ProgressBarCellWidget(f.progress)
            self.table_files.setCellWidget(row, 4, p_widget)

            # Col 5: Size
            sz_item = QTableWidgetItem(f.size_formatted)
            sz_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_files.setItem(row, 5, sz_item)

            # Col 6: Usage
            self.table_files.setItem(row, 6, QTableWidgetItem(f.usage or "Translatable"))

            # Col 7: File Type Ident.
            self.table_files.setItem(row, 7, QTableWidgetItem(f.file_type_ident or "SpreadsheetML v. 1"))

            # Col 8: Path
            path_item = QTableWidgetItem(os.path.dirname(f.path))
            path_item.setForeground(QColor(160, 160, 160))
            self.table_files.setItem(row, 8, path_item)

            # Col 9: Cloud Task
            self.table_files.setItem(row, 9, QTableWidgetItem("none"))

    # =========================================================================
    # DETALHES DO FICHEIRO SELECIONADO
    # =========================================================================
    def _on_file_selection_changed(self) -> None:
        indexes = self.table_files.selectionModel().selectedRows()
        if not indexes:
            return

        row = indexes[0].row()
        item = self.table_files.item(row, 0)
        if not item:
            return

        f_path = item.data(Qt.UserRole)
        f_obj = next((f for f in self._all_files if f.path == f_path), None)
        if f_obj:
            self._update_details_panel(f_obj)

    def _update_details_panel(self, f: ProjectFile) -> None:
        base = os.path.basename(f.path)
        self.lbl_details_title.setText(f"File Attributes — {base}")

        # ---------------- Aba 1: File Details
        props = [
            ("File Name", base),
            ("Usage", f.usage or "Translatable"),
            ("File Type Identifier", f.file_type_ident or "SpreadsheetML v. 1"),
            ("File Size", f.size_formatted),
            ("Total Words", f"{f.words:,}" if f.words > 0 else "-"),
            ("Total Segments", str(f.segment_count)),
            ("Translated Segments", str(f.translated_count)),
            ("Progress", f"{f.progress:.1f}%"),
            ("Status", f.status),
            ("Physical Path", f.path),
            ("Last Modified", f.last_modified or "-"),
        ]
        self.table_prop_details.setRowCount(len(props))
        for r, (k, v) in enumerate(props):
            k_item = QTableWidgetItem(k)
            k_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            k_item.setForeground(QColor(142, 180, 243))
            self.table_prop_details.setItem(r, 0, k_item)
            self.table_prop_details.setItem(r, 1, QTableWidgetItem(str(v)))

        # ---------------- Aba 2: Analysis Statistics
        total_w = f.words if f.words > 0 else 0
        total_s = f.segment_count if f.segment_count > 0 else 0
        w_base = total_w if total_w > 0 else 1
        s_base = total_s if total_s > 0 else 1

        trans_w = f.translated_words + f.approved_words
        if trans_w == 0 and f.translated_count > 0 and total_s > 0 and total_w > 0:
            trans_w = int(round((f.translated_count / total_s) * total_w))
        untrans_w = max(0, total_w - trans_w - f.draft_words)

        trans_s = f.translated_count + f.approved_count
        untrans_s = max(0, total_s - trans_s - f.draft_count)

        rep_w = f.match_repetitions_words
        rep_s = f.match_repetitions_segs
        perf_w = f.match_perfect_words
        perf_s = f.match_perfect_segs
        ctx_w = f.match_context_words
        ctx_s = f.match_context_segs
        m100_w = f.match_100_words if f.match_100_words > 0 else (trans_w if (rep_w + perf_w + ctx_w == 0) else 0)
        m100_s = f.match_100_segs if f.match_100_segs > 0 else (trans_s if (rep_s + perf_s + ctx_s == 0) else 0)
        m95_w = f.match_95_99_words
        m95_s = f.match_95_99_segs
        m85_w = f.match_85_94_words
        m85_s = f.match_85_94_segs
        m75_w = f.match_75_84_words
        m75_s = f.match_75_84_segs
        m50_w = f.match_50_74_words
        m50_s = f.match_50_74_segs
        new_w = f.match_new_words if f.match_new_words > 0 else untrans_w
        new_s = f.match_new_segs if f.match_new_segs > 0 else untrans_s

        an_rows = [
            ("Context Match", str(ctx_s), str(ctx_w), f"{(ctx_w / w_base * 100):.1f}%"),
            ("Repetitions", str(rep_s), str(rep_w), f"{(rep_w / w_base * 100):.1f}%"),
            ("100%", str(m100_s), str(m100_w), f"{(m100_w / w_base * 100):.1f}%"),
            ("95% - 99%", str(m95_s), str(m95_w), f"{(m95_w / w_base * 100):.1f}%"),
            ("85% - 94%", str(m85_s), str(m85_w), f"{(m85_w / w_base * 100):.1f}%"),
            ("75% - 84%", str(m75_s), str(m75_w), f"{(m75_w / w_base * 100):.1f}%"),
            ("50% - 74%", str(m50_s), str(m50_w), f"{(m50_w / w_base * 100):.1f}%"),
            ("New / Untranslated", str(new_s), str(new_w), f"{(new_w / w_base * 100):.1f}%"),
            ("Total", str(total_s), str(total_w), "100.0%"),
        ]
        self.table_analysis_stats.setRowCount(len(an_rows))
        for r, row_data in enumerate(an_rows):
            for c, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                if r == len(an_rows) - 1:
                    item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                self.table_analysis_stats.setItem(r, c, item)

        # ---------------- Aba 3: Confirmation Statistics
        cf_rows = [
            ("Not Translated", str(untrans_s), str(untrans_w), f"{(untrans_w / w_base * 100):.1f}%"),
            ("Draft", str(f.draft_count), str(f.draft_words), f"{(f.draft_words / w_base * 100):.1f}%"),
            ("Translated", str(f.translated_count), str(f.translated_words), f"{(f.translated_words / w_base * 100):.1f}%"),
            ("Translation Approved", str(f.approved_count), str(f.approved_words), f"{(f.approved_words / w_base * 100):.1f}%"),
            ("Translation Rejected", str(f.rejected_count), str(f.rejected_words), f"{(f.rejected_words / w_base * 100):.1f}%"),
            ("Total", str(total_s), str(total_w), "100.0%"),
        ]
        self.table_confirm_stats.setRowCount(len(cf_rows))
        for r, row_data in enumerate(cf_rows):
            for c, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                if r == len(cf_rows) - 1:
                    item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                self.table_confirm_stats.setItem(r, c, item)

        # ---------------- Aba 4: Task History
        tasks = [
            ("Scan and Convert", "Completed", f.last_modified[:19].replace("T", " ") if f.last_modified else "2026-10-13", "Auto"),
            ("Pre-translate Files", "Completed", f.last_modified[:19].replace("T", " ") if f.last_modified else "2026-10-14", "Icaro"),
        ]
        self.table_task_history.setRowCount(len(tasks))
        for r, (tn, ts, td, tu) in enumerate(tasks):
            self.table_task_history.setItem(r, 0, QTableWidgetItem(tn))
            st_item = QTableWidgetItem(ts)
            st_item.setForeground(QColor(46, 204, 113))
            self.table_task_history.setItem(r, 1, st_item)
            self.table_task_history.setItem(r, 2, QTableWidgetItem(td))
            self.table_task_history.setItem(r, 3, QTableWidgetItem(tu))

        # ---------------- Aba 5: File Attributes
        attrs = [
            ("Encoding", "UTF-8"),
            ("Target Language", f.target_lang or "pt-BR"),
            ("Usage Role", f.usage or "Translatable"),
            ("File Format", f.file_type.upper()),
        ]
        self.table_attributes.setRowCount(len(attrs))
        for r, (k, v) in enumerate(attrs):
            self.table_attributes.setItem(r, 0, QTableWidgetItem(k))
            self.table_attributes.setItem(r, 1, QTableWidgetItem(v))

    # =========================================================================
    # AÇÕES DE ABERTURA E GESTÃO
    # =========================================================================
    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        item = self.table_files.item(row, 0)
        if item:
            f_path = item.data(Qt.UserRole)
            if f_path:
                self.open_file_in_editor.emit(f_path)

    def _open_selected_file(self) -> None:
        row = self.table_files.currentRow()
        if row >= 0:
            self._on_cell_double_clicked(row, 0)
        else:
            QMessageBox.information(self, "Ficheiros", "Selecione um ficheiro da lista para abrir.")

    def _show_context_menu(self, pos) -> None:
        row = self.table_files.rowAt(pos.y())
        if row < 0:
            return
        self.table_files.selectRow(row)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #252526; color: #e0e0e0; border: 1px solid #3e3e42; padding: 4px;
            }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #007acc; color: white; }
        """)

        act_trans = menu.addAction("✏ Open For Translation")
        act_trans.triggered.connect(self._open_selected_file)

        act_rev = menu.addAction("🔍 Open For Review")
        act_rev.triggered.connect(self._open_selected_file)

        menu.addSeparator()

        b_menu = menu.addMenu("⚙ Batch Tasks")
        b_menu.addAction("📊 Analyze Files", lambda: self.batch_tasks_requested.emit("analyze"))
        b_menu.addAction("⚡ Pre-translate Files", lambda: self.batch_tasks_requested.emit("pretranslate"))
        b_menu.addAction("🔎 Verify QA (F8)", lambda: self.batch_tasks_requested.emit("verify"))

        menu.addSeparator()

        act_exp = menu.addAction("📂 Explore Containing Folder")
        act_exp.triggered.connect(self._explore_selected_file)

        act_del = menu.addAction("🗑 Remove File")
        act_del.triggered.connect(self._remove_file)

        menu.exec(self.table_files.viewport().mapToGlobal(pos))

    def _explore_selected_file(self) -> None:
        row = self.table_files.currentRow()
        if row < 0:
            return
        item = self.table_files.item(row, 0)
        if item:
            f_path = item.data(Qt.UserRole)
            if f_path and os.path.exists(f_path):
                folder = os.path.dirname(f_path)
                os.startfile(folder)

    def _add_file(self) -> None:
        if not self._current_project:
            QMessageBox.warning(self, "Aviso", "Nenhum projeto ativo para adicionar ficheiros.")
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Adicionar Ficheiros ao Projeto", "",
            "Ficheiros Bilingues (*.sdlxliff *.tmx *.xlf *.xliff);;Todos (*.*)"
        )
        if not paths:
            return

        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            ft = "tmx" if ext == ".tmx" else "sdlxliff"
            self._current_project.add_file(p, ft)

        self.set_project(self._current_project)

    def _remove_file(self) -> None:
        if not self._current_project:
            return
        row = self.table_files.currentRow()
        if row < 0:
            QMessageBox.information(self, "Remover", "Selecione um ficheiro para remover.")
            return

        item = self.table_files.item(row, 0)
        if item:
            f_path = item.data(Qt.UserRole)
            self._current_project.remove_file(f_path)
            self.set_project(self._current_project)
