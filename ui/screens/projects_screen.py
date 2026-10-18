"""
ui.screens.projects_screen - Ecrã de Gestão de Projetos estilo SDL Trados Studio (Projects View).

Reproduz fielmente o visual oficial do Trados Studio:
- Painel lateral esquerdo retrátil 'Filter Projects' (Project name, Status, Due date, Type, Customer)
- Tabela principal de Projetos (Name, Status, Due Date, Created At, Type, Location, Server, Organization)
- Painel inferior de detalhes com abas na base (South):
  * Project Details (Ficha de propriedades chave-valor)
  * Confirmation Statistics (Estatísticas de confirmação e progresso)
  * Analysis Statistics (Balanço de palavras e correspondências de TM)
  * Task History (Histórico de tarefas e tarefas em lote)
  * Project Attributes (Atributos e metadados)
- Leitura automática do registro mestre projects.xml do SDL Trados Studio
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QAction
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QLineEdit, QComboBox, QFrame, QSplitter,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QMenu, QProgressBar
)

from core.project import Project, ProjectFile, is_project_file
from core.config import load_config, save_config
from io_layer.sdlproj import parse_sdlproj, is_sdlproj_file, parse_projects_xml
from ui.screens.files_screen import ProgressBarCellWidget


class ProjectsScreen(QWidget):
    """Ecrã de Gestão de Projetos estilo SDL Trados Studio (Projects View)."""

    project_opened = Signal(object)  # Project object
    file_opened = Signal(str)        # specific file path to open in editor

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._config = load_config()
        self._current_project: Optional[Project] = None
        self._all_projects: List[dict] = []  # List of project metadata dicts
        self._cached_projects: dict[str, Project] = {}

        # Compatibilidade com chamadas herdadas
        self.name_edit = QLineEdit()
        self.file_table = QTableWidget()

        self._build_ui()
        self._load_projects()

    def _update_file_table(self) -> None:
        """Compatibilidade com chamadas herdadas."""
        pass

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
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

        # Splitter principal: Painel de Filtro à esquerda, Conteúdo à direita
        self.main_hsplitter = QSplitter(Qt.Horizontal)

        # =========================================================================
        # PAINEL LATERAL ESQUERDO: "Filter Projects"
        # =========================================================================
        self.left_filter_panel = QFrame()
        self.left_filter_panel.setFixedWidth(230)
        self.left_filter_panel.setStyleSheet("background-color: #252526; border-right: 1px solid #333333;")
        lp_layout = QVBoxLayout(self.left_filter_panel)
        lp_layout.setContentsMargins(8, 8, 8, 8)
        lp_layout.setSpacing(8)

        # Cabeçalho "Projects" com botão de recolher
        hdr_layout = QHBoxLayout()
        hdr_title = QLabel("Projects")
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

        # Grupo "Filter Projects"
        grp_filter = QFrame()
        grp_filter.setStyleSheet("border: 1px solid #3e3e42; border-radius: 4px; padding: 6px; background-color: #202022;")
        gf_layout = QVBoxLayout(grp_filter)
        gf_layout.setContentsMargins(4, 6, 4, 6)
        gf_layout.setSpacing(6)

        lbl_grp_title = QLabel("Filter Projects")
        lbl_grp_title.setStyleSheet("color: #888888; font-weight: bold; font-size: 10px; border: none;")
        gf_layout.addWidget(lbl_grp_title)

        # 1. Project name
        gf_layout.addWidget(QLabel("Project name:"))
        self.txt_filter_name = QLineEdit()
        self.txt_filter_name.setPlaceholderText("Filter by name...")
        self.txt_filter_name.textChanged.connect(self._apply_filters)
        gf_layout.addWidget(self.txt_filter_name)

        # 2. Status
        gf_layout.addWidget(QLabel("Status:"))
        self.combo_filter_status = QComboBox()
        self.combo_filter_status.addItems(["Show all projects", "In Progress", "Completed", "New"])
        self.combo_filter_status.currentIndexChanged.connect(self._apply_filters)
        gf_layout.addWidget(self.combo_filter_status)

        # 3. Due date
        gf_layout.addWidget(QLabel("Due date:"))
        self.combo_filter_due = QComboBox()
        self.combo_filter_due.addItems(["Show all projects", "Today", "This week", "This month", "Overdue"])
        self.combo_filter_due.currentIndexChanged.connect(self._apply_filters)
        gf_layout.addWidget(self.combo_filter_due)

        # 4. Type
        gf_layout.addWidget(QLabel("Type:"))
        self.combo_filter_type = QComboBox()
        self.combo_filter_type.addItems(["Show all projects", "Studio project", "Package", "CAT Project"])
        self.combo_filter_type.currentIndexChanged.connect(self._apply_filters)
        gf_layout.addWidget(self.combo_filter_type)

        # 5. Customer
        gf_layout.addWidget(QLabel("Customer:"))
        self.combo_filter_customer = QComboBox()
        self.combo_filter_customer.addItems(["Show all projects"])
        self.combo_filter_customer.currentIndexChanged.connect(self._apply_filters)
        gf_layout.addWidget(self.combo_filter_customer)

        lp_layout.addWidget(grp_filter)
        lp_layout.addStretch()

        self.main_hsplitter.addWidget(self.left_filter_panel)

        # =========================================================================
        # CONTEÚDO PRINCIPAL (Splitter Vertical: Tabela de Projetos + Detalhes)
        # =========================================================================
        center_container = QWidget()
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(6, 4, 6, 4)
        center_layout.setSpacing(4)

        # Barra de Ações Rápidas do Projeto
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 0, 0, 0)
        action_bar.setSpacing(6)

        btn_new_proj = QPushButton("➕ Novo Projeto...")
        btn_new_proj.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white; border: none;
                border-radius: 3px; padding: 5px 12px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #2ecc71; }
        """)
        btn_new_proj.clicked.connect(self._new_project)
        action_bar.addWidget(btn_new_proj)

        btn_open_proj = QPushButton("📂 Abrir Projeto...")
        btn_open_proj.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: #ffffff; border: 1px solid #444444;
                border-radius: 3px; padding: 5px 12px; font-size: 11px;
            }
            QPushButton:hover { background-color: #444444; }
        """)
        btn_open_proj.clicked.connect(self._open_project_dialog)
        action_bar.addWidget(btn_open_proj)

        btn_open_files = QPushButton("▶ Abrir para Tradução (Ficheiros)")
        btn_open_files.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: white; border: none;
                border-radius: 3px; padding: 5px 14px; font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #1c97ea; }
        """)
        btn_open_files.clicked.connect(self._open_selected_project)
        action_bar.addWidget(btn_open_files)

        action_bar.addStretch()

        self.lbl_project_count = QLabel("0 projetos")
        self.lbl_project_count.setStyleSheet("color: #888888; font-size: 11px;")
        action_bar.addWidget(self.lbl_project_count)

        center_layout.addLayout(action_bar)

        # Splitter Vertical: Tabela em cima, Detalhes embaixo
        self.main_vsplitter = QSplitter(Qt.Vertical)

        # ---------------- 1. Tabela de Projetos Trados Studio
        self.table_projects = QTableWidget()
        self.table_projects.setColumnCount(9)
        self.table_projects.setHorizontalHeaderLabels([
            "Name", "Status", "Progress", "Due Date", "Created At", "Type", "Location", "Server", "Organization"
        ])
        self.table_projects.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_projects.setAlternatingRowColors(True)
        self.table_projects.verticalHeader().setDefaultSectionSize(26)
        self.table_projects.horizontalHeader().setStretchLastSection(True)
        self.table_projects.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 3, 4, 5, 7, 8):
            self.table_projects.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table_projects.horizontalHeader().resizeSection(2, 100)
        self.table_projects.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)

        self.table_projects.itemSelectionChanged.connect(self._on_project_selection_changed)
        self.table_projects.cellDoubleClicked.connect(lambda r, c: self._open_selected_project())
        self.table_projects.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_projects.customContextMenuRequested.connect(self._show_context_menu)

        self.main_vsplitter.addWidget(self.table_projects)

        # ---------------- 2. Painel Inferior de Detalhes (Project Details & Tabs)
        self.details_container = QFrame()
        self.details_container.setStyleSheet("background-color: #1e1e1e; border: 1px solid #333333; border-radius: 4px;")
        det_vlayout = QVBoxLayout(self.details_container)
        det_vlayout.setContentsMargins(6, 4, 6, 4)
        det_vlayout.setSpacing(4)

        # Header da barra de detalhes
        det_header = QHBoxLayout()
        det_header.setContentsMargins(0, 0, 0, 0)
        self.lbl_details_title = QLabel("Project Details")
        self.lbl_details_title.setStyleSheet("font-weight: bold; color: #8eb4f3; font-size: 11px;")
        det_header.addWidget(self.lbl_details_title)
        det_header.addStretch()

        btn_close_details = QPushButton("✕")
        btn_close_details.setFixedSize(18, 18)
        btn_close_details.setToolTip("Ocultar painel de detalhes")
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

        # Aba 1: Project Details (Ficha de propriedades chave-valor)
        self.table_prop_details = QTableWidget()
        self.table_prop_details.setColumnCount(2)
        self.table_prop_details.setHorizontalHeaderLabels(["Property", "Value"])
        self.table_prop_details.horizontalHeader().setStretchLastSection(True)
        self.table_prop_details.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table_prop_details.verticalHeader().setVisible(False)
        self.table_prop_details.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_prop_details, "📄 Project Details")

        # Aba 2: Confirmation Statistics
        self.table_confirm_stats = QTableWidget()
        self.table_confirm_stats.setColumnCount(4)
        self.table_confirm_stats.setHorizontalHeaderLabels(["Status", "Segments", "Words", "Percentage"])
        self.table_confirm_stats.horizontalHeader().setStretchLastSection(True)
        self.table_confirm_stats.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_confirm_stats.verticalHeader().setVisible(False)
        self.table_confirm_stats.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_confirm_stats, "📊 Confirmation Statistics")

        # Aba 3: Analysis Statistics
        self.table_analysis_stats = QTableWidget()
        self.table_analysis_stats.setColumnCount(4)
        self.table_analysis_stats.setHorizontalHeaderLabels(["Match Band", "Segments", "Words", "Percentage"])
        self.table_analysis_stats.horizontalHeader().setStretchLastSection(True)
        self.table_analysis_stats.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_analysis_stats.verticalHeader().setVisible(False)
        self.table_analysis_stats.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_analysis_stats, "📈 Analysis Statistics")

        # Aba 4: Task History
        self.table_task_history = QTableWidget()
        self.table_task_history.setColumnCount(4)
        self.table_task_history.setHorizontalHeaderLabels(["Task", "Status", "Date / Time", "User"])
        self.table_task_history.horizontalHeader().setStretchLastSection(True)
        self.table_task_history.verticalHeader().setVisible(False)
        self.table_task_history.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_task_history, "🕒 Task History")

        # Aba 5: Project Attributes
        self.table_attributes = QTableWidget()
        self.table_attributes.setColumnCount(2)
        self.table_attributes.setHorizontalHeaderLabels(["Attribute", "Value"])
        self.table_attributes.horizontalHeader().setStretchLastSection(True)
        self.table_attributes.verticalHeader().setVisible(False)
        self.table_attributes.setAlternatingRowColors(True)
        self.tab_details.addTab(self.table_attributes, "🏷 Project Attributes")

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
    # CARREGAMENTO E ATUALIZAÇÃO DOS PROJETOS
    # =========================================================================
    def _load_projects(self) -> None:
        """Carrega todos os projetos do registro projects.xml do Trados Studio e de configurações recentes."""
        self._all_projects = []
        seen_paths = set()

        # 1. Carrega do projects.xml oficial do Trados Studio
        studio_projects = parse_projects_xml()
        for p in studio_projects:
            path_norm = os.path.normpath(p["path"])
            if path_norm not in seen_paths:
                self._all_projects.append(p)
                seen_paths.add(path_norm)

        # 2. Carrega de projetos recentes da aplicação
        for r_path in self._config.recent_projects:
            if os.path.exists(r_path):
                path_norm = os.path.normpath(r_path)
                if path_norm not in seen_paths:
                    name = Path(r_path).stem
                    mtime = datetime.fromtimestamp(os.path.getmtime(r_path)).strftime("%d/%m/%Y %H:%M:%S")
                    ptype = "Studio project" if is_sdlproj_file(r_path) else "CAT Project"
                    self._all_projects.append({
                        "name": name,
                        "path": r_path,
                        "status": "In Progress",
                        "due_date": "[none]",
                        "created_at": mtime,
                        "type": ptype,
                        "location": os.path.dirname(r_path),
                        "server": "(none)",
                        "organization": "n/a",
                        "created_by": "Local"
                    })
                    seen_paths.add(path_norm)

        # Aplica filtros e popula tabela
        self._apply_filters()

        # Seleciona o primeiro projeto por padrão se houver
        if self.table_projects.rowCount() > 0:
            self.table_projects.selectRow(0)

    def _apply_filters(self) -> None:
        """Filtra a lista de projetos em tempo real com base nos campos do painel esquerdo."""
        name_q = self.txt_filter_name.text().strip().lower()
        status_q = self.combo_filter_status.currentText().strip()
        type_q = self.combo_filter_type.currentText().strip()

        filtered = []
        for p in self._all_projects:
            if name_q and name_q not in p["name"].lower():
                continue
            if status_q != "Show all projects" and p["status"].lower() != status_q.lower():
                continue
            if type_q != "Show all projects" and p["type"].lower() != type_q.lower():
                continue
            filtered.append(p)

        self._populate_projects_table(filtered)
        self.lbl_project_count.setText(f"{len(filtered)} projeto(s)")

    def _populate_projects_table(self, projects: List[dict]) -> None:
        self.table_projects.setRowCount(len(projects))

        for row, p in enumerate(projects):
            # Col 0: Name (com ícone de pasta/projeto Trados)
            name_item = QTableWidgetItem(f"📁  {p['name']}")
            name_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            name_item.setData(Qt.UserRole, p["path"])
            self.table_projects.setItem(row, 0, name_item)

            # Col 1: Status
            status_item = QTableWidgetItem(p.get("status", "In Progress"))
            status_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            if p.get("status") == "Completed":
                status_item.setForeground(QColor(46, 204, 113))
            else:
                status_item.setForeground(QColor(52, 152, 219))
            self.table_projects.setItem(row, 1, status_item)

            # Col 2: Progress (barra de progresso gráfica)
            proj_path = p.get("path", "")
            prog = 0.0
            if p.get("status") == "Completed":
                prog = 100.0
            elif proj_path in self._cached_projects:
                prog = self._cached_projects[proj_path].overall_progress()
            self.table_projects.setCellWidget(row, 2, ProgressBarCellWidget(prog))

            # Col 3: Due Date
            due_item = QTableWidgetItem(p.get("due_date", "[none]"))
            due_item.setForeground(QColor(160, 160, 160))
            self.table_projects.setItem(row, 3, due_item)

            # Col 4: Created At
            created_item = QTableWidgetItem(p.get("created_at", ""))
            self.table_projects.setItem(row, 4, created_item)

            # Col 5: Type
            type_item = QTableWidgetItem(p.get("type", "Studio project"))
            self.table_projects.setItem(row, 5, type_item)

            # Col 6: Location
            loc_item = QTableWidgetItem(p.get("location", ""))
            loc_item.setForeground(QColor(180, 180, 180))
            self.table_projects.setItem(row, 6, loc_item)

            # Col 7: Server
            self.table_projects.setItem(row, 7, QTableWidgetItem(p.get("server", "(none)")))

            # Col 8: Organization
            self.table_projects.setItem(row, 8, QTableWidgetItem(p.get("organization", "n/a")))

    # =========================================================================
    # DETALHES DO PROJETO SELECIONADO
    # =========================================================================
    def _on_project_selection_changed(self) -> None:
        indexes = self.table_projects.selectionModel().selectedRows()
        if not indexes:
            return

        row = indexes[0].row()
        item = self.table_projects.item(row, 0)
        if not item:
            return

        proj_path = item.data(Qt.UserRole)
        if not proj_path:
            return

        proj = self._get_or_load_project(proj_path)
        if not proj:
            return

        self._current_project = proj
        # Atualiza a barra de progresso da linha na tabela de projetos
        self.table_projects.setCellWidget(row, 2, ProgressBarCellWidget(proj.overall_progress()))
        self._update_details_panel(proj)

    def _get_or_load_project(self, path: str) -> Optional[Project]:
        if path in self._cached_projects:
            return self._cached_projects[path]

        if not os.path.exists(path):
            return None

        try:
            if is_sdlproj_file(path):
                proj = parse_sdlproj(path)
            else:
                proj = Project.load(path)

            if proj:
                self._cached_projects[path] = proj
                return proj
        except Exception:
            pass
        return None

    def _update_details_panel(self, proj: Project) -> None:
        """Atualiza todas as abas inferiores com os dados reais do projeto selecionado."""
        self.lbl_details_title.setText(f"Project Details — {proj.name}")

        # ---------------- Aba 1: Ficha de Propriedades (Key-Value)
        translatable_files = sum(1 for f in proj.files if getattr(f, "usage", "") == "Translatable" or f.path.endswith(".sdlxliff"))
        ref_files = len(proj.files) - translatable_files
        files_str = f"{translatable_files} translatable, {ref_files} reference"

        props = [
            ("Name", proj.name),
            ("Description", proj.description or "(none)"),
            ("Location", proj.location or os.path.dirname(proj.path)),
            ("Customer", proj.customer or "(none)"),
            ("Status", proj.status),
            ("Source Language", proj.source_lang or "English (United States)"),
            ("Target Languages", proj.target_lang or "Portuguese (Brazil)"),
            ("Project Template", proj.project_template or "(none)"),
            ("Reference Project", proj.reference_project or "(none)"),
            ("Files", files_str),
            ("Server", proj.server or "(none)"),
            ("Organization", proj.organization or "n/a"),
        ]

        self.table_prop_details.setRowCount(len(props))
        for r, (k, v) in enumerate(props):
            k_item = QTableWidgetItem(k)
            k_item.setFont(QFont("Segoe UI", 9, QFont.Bold))
            k_item.setForeground(QColor(142, 180, 243))
            v_item = QTableWidgetItem(str(v))
            self.table_prop_details.setItem(r, 0, k_item)
            self.table_prop_details.setItem(r, 1, v_item)

        # ---------------- Aba 2: Confirmation Statistics
        total_words = proj.total_words()
        total_segs = proj.total_segments()
        w_base = total_words if total_words > 0 else 1
        s_base = total_segs if total_segs > 0 else 1

        trans_w = sum(f.translated_words for f in proj.files)
        appr_w = sum(f.approved_words for f in proj.files)
        draft_w = sum(f.draft_words for f in proj.files)
        rej_w = sum(f.rejected_words for f in proj.files)
        untrans_w = sum(f.untranslated_words for f in proj.files)
        if untrans_w == 0 and (trans_w + appr_w + draft_w + rej_w) < total_words:
            untrans_w = max(0, total_words - (trans_w + appr_w + draft_w + rej_w))

        trans_s = sum(f.translated_count for f in proj.files)
        appr_s = sum(f.approved_count for f in proj.files)
        draft_s = sum(f.draft_count for f in proj.files)
        rej_s = sum(f.rejected_count for f in proj.files)
        untrans_s = sum(f.untranslated_count for f in proj.files)
        if untrans_s == 0 and (trans_s + appr_s + draft_s + rej_s) < total_segs:
            untrans_s = max(0, total_segs - (trans_s + appr_s + draft_s + rej_s))

        stats_rows = [
            ("Not Translated", str(untrans_s), str(untrans_w), f"{(untrans_w / w_base * 100):.1f}%"),
            ("Draft", str(draft_s), str(draft_w), f"{(draft_w / w_base * 100):.1f}%"),
            ("Translated", str(trans_s), str(trans_w), f"{(trans_w / w_base * 100):.1f}%"),
            ("Translation Approved", str(appr_s), str(appr_w), f"{(appr_w / w_base * 100):.1f}%"),
            ("Translation Rejected", str(rej_s), str(rej_w), f"{(rej_w / w_base * 100):.1f}%"),
            ("Total", str(total_segs), str(total_words), "100.0%"),
        ]
        self.table_confirm_stats.setRowCount(len(stats_rows))
        for r, row_data in enumerate(stats_rows):
            for c, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                if r == len(stats_rows) - 1:
                    item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                self.table_confirm_stats.setItem(r, c, item)

        # ---------------- Aba 3: Analysis Statistics
        ctx_s = sum(f.match_context_segs for f in proj.files)
        ctx_w = sum(f.match_context_words for f in proj.files)
        rep_s = sum(f.match_repetitions_segs for f in proj.files)
        rep_w = sum(f.match_repetitions_words for f in proj.files)
        m100_s = sum(f.match_100_segs for f in proj.files)
        m100_w = sum(f.match_100_words for f in proj.files)
        if m100_w == 0 and (ctx_w + rep_w == 0) and (trans_w + appr_w > 0):
            m100_w = trans_w + appr_w
            m100_s = trans_s + appr_s
        m95_s = sum(f.match_95_99_segs for f in proj.files)
        m95_w = sum(f.match_95_99_words for f in proj.files)
        m85_s = sum(f.match_85_94_segs for f in proj.files)
        m85_w = sum(f.match_85_94_words for f in proj.files)
        m75_s = sum(f.match_75_84_segs for f in proj.files)
        m75_w = sum(f.match_75_84_words for f in proj.files)
        m50_s = sum(f.match_50_74_segs for f in proj.files)
        m50_w = sum(f.match_50_74_words for f in proj.files)
        new_s = sum(f.match_new_segs for f in proj.files)
        new_w = sum(f.match_new_words for f in proj.files)
        if new_w == 0 and untrans_w > 0:
            new_w = untrans_w
            new_s = untrans_s

        analysis_rows = [
            ("Context Match", str(ctx_s), str(ctx_w), f"{(ctx_w / w_base * 100):.1f}%"),
            ("Repetitions", str(rep_s), str(rep_w), f"{(rep_w / w_base * 100):.1f}%"),
            ("100%", str(m100_s), str(m100_w), f"{(m100_w / w_base * 100):.1f}%"),
            ("95% - 99%", str(m95_s), str(m95_w), f"{(m95_w / w_base * 100):.1f}%"),
            ("85% - 94%", str(m85_s), str(m85_w), f"{(m85_w / w_base * 100):.1f}%"),
            ("75% - 84%", str(m75_s), str(m75_w), f"{(m75_w / w_base * 100):.1f}%"),
            ("50% - 74%", str(m50_s), str(m50_w), f"{(m50_w / w_base * 100):.1f}%"),
            ("New", str(new_s), str(new_w), f"{(new_w / w_base * 100):.1f}%"),
            ("Total", str(total_segs), str(total_words), "100.0%"),
        ]
        self.table_analysis_stats.setRowCount(len(analysis_rows))
        for r, row_data in enumerate(analysis_rows):
            for c, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                if r == len(analysis_rows) - 1:
                    item.setFont(QFont("Segoe UI", 9, QFont.Bold))
                self.table_analysis_stats.setItem(r, c, item)

        # ---------------- Aba 4: Task History
        tasks = [
            ("Prepare Without Project TM", "Completed", proj.created[:19].replace("T", " "), "Auto"),
            ("Analyze Files", "Completed", proj.created[:19].replace("T", " "), "Auto"),
            ("Pre-translate Files", "Completed", proj.modified[:19].replace("T", " "), "User"),
        ]
        self.table_task_history.setRowCount(len(tasks))
        for r, (t_name, t_stat, t_date, t_user) in enumerate(tasks):
            self.table_task_history.setItem(r, 0, QTableWidgetItem(t_name))
            st_item = QTableWidgetItem(t_stat)
            st_item.setForeground(QColor(46, 204, 113))
            self.table_task_history.setItem(r, 1, st_item)
            self.table_task_history.setItem(r, 2, QTableWidgetItem(t_date))
            self.table_task_history.setItem(r, 3, QTableWidgetItem(t_user))

        # ---------------- Aba 5: Project Attributes
        attrs = [
            ("Customer", proj.customer or "Default"),
            ("Project Manager", getattr(proj, "created_by", "Icaro")),
            ("Source Culture", proj.source_lang),
            ("Target Culture", proj.target_lang),
            ("File Count", str(len(proj.files))),
            ("Attached TMs", str(len(proj.tm_paths))),
        ]
        self.table_attributes.setRowCount(len(attrs))
        for r, (k, v) in enumerate(attrs):
            self.table_attributes.setItem(r, 0, QTableWidgetItem(k))
            self.table_attributes.setItem(r, 1, QTableWidgetItem(str(v)))

    # =========================================================================
    # AÇÕES DO PROJETO (Abrir, Criar, Context Menu)
    # =========================================================================
    def _open_selected_project(self) -> None:
        """Abre o projeto selecionado na lista."""
        row = self.table_projects.currentRow()
        if row < 0:
            QMessageBox.information(self, "Projetos", "Selecione um projeto na lista para abrir.")
            return

        item = self.table_projects.item(row, 0)
        if not item:
            return

        proj_path = item.data(Qt.UserRole)
        proj = self._get_or_load_project(proj_path)
        if not proj:
            QMessageBox.warning(self, "Aviso", f"Não foi possível carregar o projeto:\n{proj_path}")
            return

        self._current_project = proj
        self.project_opened.emit(proj)

    def _open_project_dialog(self) -> None:
        """Abre diálogo para selecionar arquivo de projeto do Trados (.sdlproj) ou .catproj."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Projeto", "",
            "Projetos de Tradução (*.sdlproj *.catproj);;Todos os Ficheiros (*.*)"
        )
        if path:
            proj = self._get_or_load_project(path)
            if proj:
                self._current_project = proj
                # Adiciona aos recentes
                if path not in self._config.recent_projects:
                    self._config.recent_projects.insert(0, path)
                    self._config.recent_projects = self._config.recent_projects[:15]
                    save_config(self._config)
                self._load_projects()
                self.project_opened.emit(proj)

    def _new_project(self) -> None:
        """Cria um novo projeto."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Criar Novo Projeto", "Novo_Projeto.catproj",
            "CAT Project (*.catproj)"
        )
        if not path:
            return

        proj = Project(
            name=Path(path).stem,
            path=path,
            source_lang="en-US",
            target_lang="pt-BR"
        )
        proj.save(path)

        if path not in self._config.recent_projects:
            self._config.recent_projects.insert(0, path)
            save_config(self._config)

        self._load_projects()
        self.project_opened.emit(proj)

    def _show_context_menu(self, pos) -> None:
        row = self.table_projects.rowAt(pos.y())
        if row < 0:
            return
        self.table_projects.selectRow(row)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #252526; color: #e0e0e0; border: 1px solid #3e3e42; padding: 4px;
            }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #007acc; color: white; }
        """)

        act_open_files = menu.addAction("▶ Open Project (Files View)")
        act_open_files.triggered.connect(self._open_selected_project)

        act_settings = menu.addAction("📁⚙ Project Settings (Alt+F8)...")
        act_settings.triggered.connect(self._open_project_settings)

        menu.addSeparator()

        act_explore = menu.addAction("📂 Explore Folder")
        act_explore.triggered.connect(self._explore_selected_folder)

        menu.exec(self.table_projects.viewport().mapToGlobal(pos))

    def _open_project_settings(self) -> None:
        if self._current_project:
            from ui.project_settings_dialog import ProjectSettingsDialog
            from core.attached_tm import AttachedTMConfig
            tms = [AttachedTMConfig(path=p) for p in self._current_project.tm_paths]
            dlg = ProjectSettingsDialog(
                current_tms=tms,
                src_lang=self._current_project.source_lang,
                tgt_lang=self._current_project.target_lang,
                project_name=self._current_project.name,
                parent=self
            )
            dlg.tms_updated.connect(self._on_tms_updated)
            dlg.exec()

    def _on_tms_updated(self, new_tms) -> None:
        if self._current_project:
            self._current_project.tm_paths = [t.path for t in new_tms if t.enabled]
            self._update_details_panel(self._current_project)

    def _explore_selected_folder(self) -> None:
        if not self._current_project:
            return
        folder = self._current_project.location or os.path.dirname(self._current_project.path)
        if os.path.exists(folder):
            os.startfile(folder)
