"""
ui.ribbon - Ribbon Bar dinâmico e contextual estilo SDL Trados Studio 2021 / 2024.

O Ribbon adapta-se dinamicamente conforme a visão ativa:
- Visão Projetos: Ações de projeto, pacotes RWS (.sdlppx / .sdlrpx), gestão de ficheiros e QA Xbench
- Visão Ficheiros: Ações de ficheiro, abrir para tradução, tarefas em lote
- Visão Editor: Ações de tradução (Confirm & Next), navegação, localizar/substituir, revisão, ApSIC Xbench QA
- Visão Memórias (TM): Trados Translation Memory Management Utility (Vacuum, Deduplicação, FTS, Integridade)
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabBar, QStackedWidget, QFrame, QToolButton, QSizePolicy,
    QComboBox, QLineEdit, QCheckBox, QMenu, QScrollArea
)


class RibbonButton(QPushButton):
    """Botão grande de Ribbon com ícone superior e rótulo inferior."""

    def __init__(self, icon_text: str, label_text: str, tooltip: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setToolTip(tooltip)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(72)
        self.setText(f"{icon_text}\n{label_text}")
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #e0e0e0;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                line-height: 1.2;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #383838;
                border: 1px solid #505050;
            }
            QPushButton:pressed {
                background-color: #007acc;
                color: #ffffff;
            }
        """)


class RibbonSmallButton(QPushButton):
    """Botão compacto horizontal para agrupar em colunas duplas."""

    def __init__(self, icon_text: str, label_text: str, tooltip: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setToolTip(tooltip)
        self.setText(f"{icon_text} {label_text}")
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #dcdcdc;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 11px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #383838;
                border: 1px solid #505050;
            }
        """)


class RibbonGroup(QFrame):
    """Grupo de comandos dentro de uma aba do Ribbon com divisor e título embaixo."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        self.setStyleSheet("""
            #RibbonGroup {
                border-right: 1px solid #333333;
                background-color: transparent;
            }
            QLabel#GroupTitle {
                color: #888888;
                font-size: 9px;
                font-weight: bold;
                text-align: center;
                margin-top: 2px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        self.content_layout = QHBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        layout.addLayout(self.content_layout)

        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("GroupTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def add_layout(self, layout: QHBoxLayout | QVBoxLayout) -> None:
        self.content_layout.addLayout(layout)


class RibbonBar(QWidget):
    """Barra Ribbon principal contextual estilo Trados Studio."""

    # Sinais disparados pelas ações do Ribbon
    open_file_requested = Signal()
    save_file_requested = Signal()
    new_project_requested = Signal()
    open_project_requested = Signal()
    open_editor_requested = Signal()
    open_files_view_requested = Signal()
    
    confirm_and_next_requested = Signal()
    copy_source_requested = Signal()
    clear_target_requested = Signal()
    prev_segment_requested = Signal()
    next_segment_requested = Signal()
    next_untranslated_requested = Signal()
    find_requested = Signal()
    replace_requested = Signal()
    approve_requested = Signal()
    reject_requested = Signal()
    draft_requested = Signal()
    spellcheck_requested = Signal()
    concordance_requested = Signal()
    merge_segment_requested = Signal()
    split_segment_requested = Signal()
    heal_segmentation_requested = Signal()
    
    # QA & Utilitários Trados
    xbench_qa_requested = Signal()
    verify_qa_requested = Signal()
    display_filter_changed = Signal(str, str, str, bool) # query, field, status, case
    display_filter_reset = Signal()
    tm_utility_requested = Signal()
    tm_editor_requested = Signal()
    advanced_filter_requested = Signal()
    batch_tasks_requested = Signal(str) # "wizard", "analyze", "pretranslate", "verify", "update_tm"
    explore_folder_requested = Signal()
    project_settings_requested = Signal()
    
    # RWS Pacotes e Projetos
    open_sdlproj_requested = Signal()
    open_sdlpackage_requested = Signal()
    export_sdltm_requested = Signal()
    export_sdlxliff_requested = Signal()
    export_tmx_requested = Signal()
    export_return_package_requested = Signal()
    switch_view_requested = Signal(str)

    # SLM (Small Language Model) & IA Local
    slm_studio_requested = Signal()
    slm_translate_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("RibbonBar")
        self.setFixedHeight(125)
        self.setStyleSheet("""
            #RibbonBar {
                background-color: #252526;
                border-bottom: 2px solid #007acc;
            }
            QTabBar::tab {
                background: #2d2d30;
                color: #cccccc;
                padding: 6px 16px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                font-weight: bold;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1e1e1e;
                color: #8eb4f3;
                border-bottom: 2px solid #007acc;
            }
            QTabBar::tab:hover {
                color: #ffffff;
                background: #383838;
            }
        """)

        self._current_view = "welcome"
        self._tabs_data = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.tab_bar = QTabBar()
        self.tab_bar.setDrawBase(False)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.main_layout.addWidget(self.tab_bar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #1e1e1e;")
        self.main_layout.addWidget(self.stack)

        self.set_view_context("welcome")

    def minimumSizeHint(self) -> QSize:
        return QSize(300, 125)

    def _add_tab(self, label: str, tab_widget: QWidget) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        scroll.setWidget(tab_widget)
        self.tab_bar.addTab(label)
        self.stack.addWidget(scroll)

    def count(self) -> int:
        return self.tab_bar.count()

    def tabText(self, index: int) -> str:
        return self.tab_bar.tabText(index)

    def _on_tab_changed(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)

    def _on_display_filter_trigger(self) -> None:
        query = self.df_search_input.text() if hasattr(self, "df_search_input") else ""
        field = self.df_combo_field.currentText() if hasattr(self, "df_combo_field") else "In Both"
        status = self.df_combo_status.currentText() if hasattr(self, "df_combo_status") else "All segments"
        case_sensitive = self.df_chk_case.isChecked() if hasattr(self, "df_chk_case") else False
        self.display_filter_changed.emit(query, field, status, case_sensitive)

    def _on_display_filter_reset(self) -> None:
        if hasattr(self, "df_search_input"):
            self.df_search_input.blockSignals(True)
            self.df_search_input.clear()
            self.df_search_input.blockSignals(False)
        if hasattr(self, "df_combo_status"):
            self.df_combo_status.blockSignals(True)
            self.df_combo_status.setCurrentIndex(0)
            self.df_combo_status.blockSignals(False)
        if hasattr(self, "df_combo_field"):
            self.df_combo_field.blockSignals(True)
            self.df_combo_field.setCurrentIndex(0)
            self.df_combo_field.blockSignals(False)
        if hasattr(self, "df_chk_case"):
            self.df_chk_case.blockSignals(True)
            self.df_chk_case.setChecked(False)
            self.df_chk_case.blockSignals(False)
        self.display_filter_reset.emit()

    def set_view_context(self, view: str) -> None:
        """Adapta as abas e comandos do Ribbon de acordo com a tela ativa (Projects, Files, Editor, TM, Welcome)."""
        self._current_view = view
        self.tab_bar.blockSignals(True)

        # Limpar abas existentes
        while self.tab_bar.count() > 0:
            self.tab_bar.removeTab(0)
        while self.stack.count() > 0:
            w = self.stack.widget(0)
            self.stack.removeWidget(w)
            w.deleteLater()

        if view == "projects":
            self._setup_projects_ribbon()
        elif view == "files":
            self._setup_files_ribbon()
        elif view == "editor":
            self._setup_editor_ribbon()
        elif view == "tm":
            self._setup_tm_ribbon()
        else: # welcome ou padrão
            self._setup_welcome_ribbon()

        self.tab_bar.blockSignals(False)
        self.tab_bar.setCurrentIndex(0)
        self.stack.setCurrentIndex(0)

    def _create_batch_tasks_button(self) -> RibbonButton:
        btn_batch = RibbonButton("⚙", "Batch\nTasks ▾", "Tarefas em Lote do Trados Studio (Análise, Pré-tradução, QA, TMs)")
        btn_batch.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #8eb4f3;
                border: 1px solid #007acc;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: white;
            }
        """)
        menu = QMenu(btn_batch)
        menu.setStyleSheet("""
            QMenu {
                background-color: #252526;
                color: #e0e0e0;
                border: 1px solid #3e3e42;
                padding: 4px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QMenu::item {
                padding: 6px 20px 6px 20px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #007acc;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #3e3e42;
                margin: 4px 0px;
            }
        """)
        act_wiz = menu.addAction("▶ Abrir Assistente de Tarefas em Lote...")
        act_wiz.triggered.connect(lambda: self.batch_tasks_requested.emit("wizard"))
        menu.addSeparator()
        act_ana = menu.addAction("📊 Analyze Files (Contagem de Palavras & TM)")
        act_ana.triggered.connect(lambda: self.batch_tasks_requested.emit("analyze"))
        act_pre = menu.addAction("⚡ Pre-translate Files (Pré-tradução Automática)")
        act_pre.triggered.connect(lambda: self.batch_tasks_requested.emit("pretranslate"))
        act_ver = menu.addAction("🔎 Verify Files (Auditoria de QA em Lote - F8)")
        act_ver.triggered.connect(lambda: self.batch_tasks_requested.emit("verify"))
        act_upd = menu.addAction("💾 Update Main Translation Memories (.sdltm)")
        act_upd.triggered.connect(lambda: self.batch_tasks_requested.emit("update_tm"))
        act_exp = menu.addAction("📄 Generate Target Translations (Exportar Finais)")
        act_exp.triggered.connect(self.export_sdlxliff_requested.emit)

        btn_batch.clicked.connect(lambda: menu.exec(btn_batch.mapToGlobal(btn_batch.rect().bottomLeft())))
        return btn_batch

    # ------------------------------------------------------------- Visão: PROJETOS
    def _setup_projects_ribbon(self) -> None:
        # Aba 1: Início (Projetos)
        tab_home = QWidget()
        lh = QHBoxLayout(tab_home)
        lh.setContentsMargins(4, 2, 4, 2)
        lh.setSpacing(0)

        # Grupo: Projeto
        grp_proj = RibbonGroup("Projeto")
        btn_new_proj = RibbonButton("✨", "Novo\nProjeto", "Criar um novo projeto de tradução")
        btn_new_proj.clicked.connect(self.new_project_requested.emit)
        grp_proj.add_widget(btn_new_proj)

        btn_open_proj = RibbonButton("📁", "Abrir\nProjeto", "Abrir projeto CAT ou SDL Trados (.sdlproj)")
        btn_open_proj.clicked.connect(self.open_project_requested.emit)
        grp_proj.add_widget(btn_open_proj)
        lh.addWidget(grp_proj)

        # Grupo: Pacotes Trados RWS
        grp_pkg = RibbonGroup("Pacotes Trados RWS")
        btn_pkg = RibbonButton("📦", "Abrir Pacote\n(.sdlppx)", "Descompactar pacote de projeto Trados")
        btn_pkg.clicked.connect(self.open_sdlpackage_requested.emit)
        grp_pkg.add_widget(btn_pkg)

        btn_ret = RibbonButton("📤", "Pacote Retorno\n(.sdlrpx)", "Gerar pacote de retorno com ficheiros traduzidos")
        btn_ret.clicked.connect(self.export_return_package_requested.emit)
        grp_pkg.add_widget(btn_ret)
        lh.addWidget(grp_pkg)

        # Grupo: Abrir para Edição
        grp_open = RibbonGroup("Tradução")
        btn_edit = RibbonButton("▶", "Abrir no\nEditor", "Abrir o projeto ativo para tradução no Editor")
        btn_edit.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #1c97ea;
            }
        """)
        btn_edit.clicked.connect(self.open_editor_requested.emit)
        grp_open.add_widget(btn_edit)

        btn_files_v = RibbonButton("📑", "Ver Ficheiros\n(Files View)", "Alternar para a visualização detalhada de ficheiros")
        btn_files_v.clicked.connect(self.open_files_view_requested.emit)
        grp_open.add_widget(btn_files_v)
        lh.addWidget(grp_open)

        # Grupo: Batch Tasks (Trados Studio)
        grp_batch_proj = RibbonGroup("Batch Tasks")
        btn_batch_proj = self._create_batch_tasks_button()
        grp_batch_proj.add_widget(btn_batch_proj)
        lh.addWidget(grp_batch_proj)

        # Grupo: Ferramentas & QA
        grp_qa = RibbonGroup("Qualidade & QA")
        btn_xbench = RibbonButton("🔎", "ApSIC Xbench\nQA", "Executar verificação de qualidade completa estilo Xbench")
        btn_xbench.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #f39c12;
                border: 1px solid #f39c12;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f39c12;
                color: black;
            }
        """)
        btn_xbench.clicked.connect(self.xbench_qa_requested.emit)
        grp_qa.add_widget(btn_xbench)

        btn_tm_util = RibbonButton("🛠", "Utilitário TM\nManagement", "Abrir o Trados Translation Memory Management Utility")
        btn_tm_util.clicked.connect(self.tm_utility_requested.emit)
        grp_qa.add_widget(btn_tm_util)

        btn_slm_studio = RibbonButton("🤖", "SLM\nStudio", "Criar e treinar SLMs locais a partir de memórias .sdltm")
        btn_slm_studio.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #a29bfe;
                border: 1px solid #6c5ce7;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6c5ce7;
                color: white;
            }
        """)
        btn_slm_studio.clicked.connect(self.slm_studio_requested.emit)
        grp_qa.add_widget(btn_slm_studio)
        lh.addWidget(grp_qa)

        lh.addStretch()
        self._add_tab("Início (Projetos)", tab_home)

        # Aba 2: Exportações & Pacotes
        tab_exp = QWidget()
        le = QHBoxLayout(tab_exp)
        le.setContentsMargins(4, 2, 4, 2)
        le.setSpacing(0)

        grp_exp = RibbonGroup("Exportar Dados")
        btn_sdltm = RibbonButton("💾", "Exportar\n.sdltm", "Exportar memória nativa SDLTM")
        btn_sdltm.clicked.connect(self.export_sdltm_requested.emit)
        grp_exp.add_widget(btn_sdltm)

        btn_sdlxliff = RibbonButton("📄", "Exportar\n.sdlxliff", "Exportar ficheiro bilingue SDLXLIFF")
        btn_sdlxliff.clicked.connect(self.export_sdlxliff_requested.emit)
        grp_exp.add_widget(btn_sdlxliff)

        btn_tmx = RibbonButton("🌐", "Exportar\nTMX", "Exportar formato padrão TMX")
        btn_tmx.clicked.connect(self.export_tmx_requested.emit)
        grp_exp.add_widget(btn_tmx)
        le.addWidget(grp_exp)

        le.addStretch()
        self._add_tab("Exportações & Utilitários", tab_exp)

    # ------------------------------------------------------------- Visão: FICHEIROS
    def _setup_files_ribbon(self) -> None:
        tab_files = QWidget()
        lf = QHBoxLayout(tab_files)
        lf.setContentsMargins(4, 2, 4, 2)
        lf.setSpacing(0)

        # Grupo 1: Configuration (Trados Studio)
        grp_config = RibbonGroup("Configuration")
        btn_proj_settings = RibbonButton("📁✏", "Project\nSettings", "Configurações do Projeto e Memórias Anexadas")
        btn_proj_settings.clicked.connect(self.project_settings_requested.emit)
        grp_config.add_widget(btn_proj_settings)
        lf.addWidget(grp_config)

        # Grupo 2: Open (Trados Studio)
        grp_open = RibbonGroup("Open")
        btn_trans = RibbonButton("✏", "Open For\nTranslation", "Abrir o ficheiro selecionado no Editor de Tradução")
        btn_trans.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        btn_trans.clicked.connect(self.open_editor_requested.emit)
        grp_open.add_widget(btn_trans)

        col_open = QVBoxLayout()
        col_open.setSpacing(2)
        btn_rev = RibbonSmallButton("🔍", "Open For Review", "Abrir no modo de revisão")
        btn_rev.clicked.connect(self.open_editor_requested.emit)
        btn_sign = RibbonSmallButton("✍", "Open For Sign-off", "Abrir no modo de aprovação final")
        btn_sign.clicked.connect(self.open_editor_requested.emit)
        col_open.addWidget(btn_rev)
        col_open.addWidget(btn_sign)
        grp_open.add_layout(col_open)
        lf.addWidget(grp_open)

        # Grupo 3: Batch Tasks (Trados Studio)
        grp_batch = RibbonGroup("Batch Tasks")
        btn_batch = self._create_batch_tasks_button()
        grp_batch.add_widget(btn_batch)
        lf.addWidget(grp_batch)

        # Grupo 4: File Actions (Trados Studio)
        grp_file_act = RibbonGroup("File Actions")
        btn_explore = RibbonButton("📂", "Explore\nFolder", "Abrir a pasta que contém os ficheiros no Explorador do Windows")
        btn_explore.clicked.connect(self.explore_folder_requested.emit)
        grp_file_act.add_widget(btn_explore)

        col_file_acts = QVBoxLayout()
        col_file_acts.setSpacing(2)
        btn_add = RibbonSmallButton("➕", "Add Files...", "Adicionar ficheiros bilingues ao projeto")
        btn_add.clicked.connect(self.open_file_requested.emit)
        btn_qa_quick = RibbonSmallButton("🔎", "Verify QA (F8)", "Executar auditoria de QA em lote")
        btn_qa_quick.clicked.connect(self.verify_qa_requested.emit)
        col_file_acts.addWidget(btn_add)
        col_file_acts.addWidget(btn_qa_quick)
        grp_file_act.add_layout(col_file_acts)
        lf.addWidget(grp_file_act)

        lf.addStretch()
        self._add_tab("Home", tab_files)

    # ------------------------------------------------------------- Visão: EDITOR
    def _setup_editor_ribbon(self) -> None:
        # Aba 1: Início (Editor)
        tab_home = QWidget()
        lh = QHBoxLayout(tab_home)
        lh.setContentsMargins(4, 2, 4, 2)
        lh.setSpacing(0)

        # Grupo: Segmento
        grp_seg = RibbonGroup("Segmento")
        btn_confirm = RibbonButton("✓", "Confirmar\n(Ctrl+Enter)", "Grava e avança para o próximo segmento")
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        btn_confirm.clicked.connect(self.confirm_and_next_requested.emit)
        grp_seg.add_widget(btn_confirm)

        col_tools = QVBoxLayout()
        col_tools.setSpacing(2)
        btn_copy = RibbonSmallButton("📋", "Copiar Fonte (Ctrl+Ins)", "Copia o texto fonte para a tradução")
        btn_copy.clicked.connect(self.copy_source_requested.emit)
        btn_clear = RibbonSmallButton("⌫", "Limpar Alvo", "Limpa o texto da tradução")
        btn_clear.clicked.connect(self.clear_target_requested.emit)
        col_tools.addWidget(btn_copy)
        col_tools.addWidget(btn_clear)
        grp_seg.add_layout(col_tools)

        col_seg_actions = QVBoxLayout()
        col_seg_actions.setSpacing(2)
        btn_merge = RibbonSmallButton("⇥⇤", "Mesclar (Ctrl+Alt+M)", "Mesclar com o próximo segmento")
        btn_merge.clicked.connect(self.merge_segment_requested.emit)
        btn_split = RibbonSmallButton("✂", "Dividir (Ctrl+Alt+S)", "Dividir segmento no cursor")
        btn_split.clicked.connect(self.split_segment_requested.emit)
        col_seg_actions.addWidget(btn_merge)
        col_seg_actions.addWidget(btn_split)
        grp_seg.add_layout(col_seg_actions)
        lh.addWidget(grp_seg)

        # Grupo: Navegação
        grp_nav = RibbonGroup("Navegação")
        col_nav1 = QVBoxLayout()
        btn_prev = RibbonSmallButton("▲", "Anterior (Ctrl+Up)", "Segmento anterior")
        btn_prev.clicked.connect(self.prev_segment_requested.emit)
        btn_next = RibbonSmallButton("▼", "Próximo (Ctrl+Down)", "Próximo segmento")
        btn_next.clicked.connect(self.next_segment_requested.emit)
        col_nav1.addWidget(btn_prev)
        col_nav1.addWidget(btn_next)
        grp_nav.add_layout(col_nav1)

        btn_next_un = RibbonButton("⏭", "Próximo\nPendente", "Ir para o próximo não traduzido (Ctrl+Alt+Down)")
        btn_next_un.clicked.connect(self.next_untranslated_requested.emit)
        grp_nav.add_widget(btn_next_un)
        lh.addWidget(grp_nav)

        # Grupo: Localizar
        grp_find = RibbonGroup("Localizar & Substituir")
        btn_find = RibbonButton("🔍", "Localizar\n(Ctrl+F)", "Abrir barra de pesquisa")
        btn_find.clicked.connect(self.find_requested.emit)
        btn_replace = RibbonButton("⇄", "Substituir\n(Ctrl+H)", "Abrir barra de substituir")
        btn_replace.clicked.connect(self.replace_requested.emit)
        grp_find.add_widget(btn_find)
        grp_find.add_widget(btn_replace)
        lh.addWidget(grp_find)

        # Grupo: Memória de Tradução (Translation Memory)
        grp_tm = RibbonGroup("Translation Memory")
        btn_proj_settings = RibbonButton("📁⚙", "Project\nSettings", "Configurações do Projeto e Memórias de Tradução (Alt+F8)")
        btn_proj_settings.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f;
                color: #93c5fd;
                border: 1px solid #3b82f6;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
                color: #ffffff;
            }
        """)
        btn_proj_settings.clicked.connect(self.project_settings_requested.emit)
        grp_tm.add_widget(btn_proj_settings)

        col_tm = QVBoxLayout()
        col_tm.setSpacing(2)
        btn_concordance = RibbonSmallButton("📖", "Concordância (F3)", "Pesquisa profunda na base da TM")
        btn_concordance.clicked.connect(self.concordance_requested.emit)
        btn_save = RibbonSmallButton("💾", "Gravar (Ctrl+S)", "Grava e atualiza a TM")
        btn_save.clicked.connect(self.save_file_requested.emit)
        col_tm.addWidget(btn_concordance)
        col_tm.addWidget(btn_save)
        grp_tm.add_layout(col_tm)

        btn_slm = RibbonButton("🤖", "SLM\n(Ctrl+G)", "Traduzir segmento com SLM Neural especializada (Ctrl+G)")
        btn_slm.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #00a4e4;
                border: 1px solid #00a4e4;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00a4e4;
                color: white;
            }
        """)
        btn_slm.clicked.connect(self.slm_translate_requested.emit)
        grp_tm.add_widget(btn_slm)
        lh.addWidget(grp_tm)

        # Grupo: Filtro & QA Trados
        grp_filter = RibbonGroup("Filtro & QA")
        btn_adf = RibbonButton("🔻", "Advanced Display\nFilter 2.0 (F6)", "Abrir o Advanced Display Filter 2.0 do Trados Studio (F6)")
        btn_adf.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #8eb4f3;
                border: 1px solid #007acc;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: white;
            }
        """)
        btn_adf.clicked.connect(self.advanced_filter_requested.emit)
        grp_filter.add_widget(btn_adf)

        btn_verify_h = RibbonButton("📄✓", "Verify\nQA (F8)", "Executar verificação de QA Completa (F8) - ApSIC Xbench QA")
        btn_verify_h.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #2ecc71;
                border: 1px solid #27ae60;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #27ae60;
                color: white;
            }
        """)
        btn_verify_h.clicked.connect(self.verify_qa_requested.emit)
        grp_filter.add_widget(btn_verify_h)
        lh.addWidget(grp_filter)

        lh.addStretch()
        self._add_tab("Home", tab_home)

        # Aba 2: Review (Revisão Trados Studio)
        tab_rev = QWidget()
        lr = QHBoxLayout(tab_rev)
        lr.setContentsMargins(4, 2, 4, 2)
        lr.setSpacing(0)

        # Grupo 1: File Actions
        grp_file_act = RibbonGroup("File Actions")
        btn_exp_bilingual = RibbonButton("📤", "Export for\nBilingual Review", "Exportar ficheiro bilingue para revisão externa")
        btn_exp_bilingual.clicked.connect(self.export_sdlxliff_requested.emit)
        grp_file_act.add_widget(btn_exp_bilingual)

        btn_upd_bilingual = RibbonButton("📥", "Update from\nBilingual Review", "Atualizar o ficheiro após revisão externa")
        btn_upd_bilingual.clicked.connect(self.open_file_requested.emit)
        grp_file_act.add_widget(btn_upd_bilingual)
        lr.addWidget(grp_file_act)

        # Grupo 2: Segment Actions
        grp_seg_status = RibbonGroup("Segment Actions")
        btn_confirm_r = RibbonButton("✓", "Confirm & Next\n(Ctrl+Enter)", "Grava e avança para o próximo segmento")
        btn_confirm_r.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        btn_confirm_r.clicked.connect(self.confirm_and_next_requested.emit)
        grp_seg_status.add_widget(btn_confirm_r)

        col_status = QVBoxLayout()
        col_status.setSpacing(2)
        btn_appr = RibbonSmallButton("🔒", "Approve (Ctrl+Shift+A)", "Marca como tradução aprovada")
        btn_appr.clicked.connect(self.approve_requested.emit)
        btn_rej = RibbonSmallButton("✗", "Reject (Ctrl+Shift+R)", "Marca como rejeitado para correção")
        btn_rej.clicked.connect(self.reject_requested.emit)
        btn_draft = RibbonSmallButton("✎", "Draft", "Marca como rascunho de tradução")
        btn_draft.clicked.connect(self.draft_requested.emit)
        col_status.addWidget(btn_appr)
        col_status.addWidget(btn_rej)
        col_status.addWidget(btn_draft)
        grp_seg_status.add_layout(col_status)

        col_merge_split = QVBoxLayout()
        col_merge_split.setSpacing(2)
        btn_merge_r = RibbonSmallButton("⇥⇤", "Merge (Ctrl+Alt+M)", "Mesclar com próximo")
        btn_merge_r.clicked.connect(self.merge_segment_requested.emit)
        btn_split_r = RibbonSmallButton("✂", "Split (Ctrl+Alt+S)", "Dividir segmento")
        btn_split_r.clicked.connect(self.split_segment_requested.emit)
        col_merge_split.addWidget(btn_merge_r)
        col_merge_split.addWidget(btn_split_r)
        grp_seg_status.add_layout(col_merge_split)
        lr.addWidget(grp_seg_status)

        # Grupo 3: Display Filter (SDL Trados Studio)
        grp_df = RibbonGroup("Display Filter")

        df_container = QWidget()
        df_vbox = QVBoxLayout(df_container)
        df_vbox.setContentsMargins(2, 2, 2, 2)
        df_vbox.setSpacing(3)

        df_top = QHBoxLayout()
        df_top.setContentsMargins(0, 0, 0, 0)
        df_top.setSpacing(4)

        self.df_combo_status = QComboBox()
        self.df_combo_status.setToolTip("Filtrar por estado de confirmação do segmento")
        self.df_combo_status.addItems([
            "All segments",
            "Not Translated",
            "Draft",
            "Translated",
            "Translation Approved",
            "Translation Rejected"
        ])
        self.df_combo_status.setStyleSheet("""
            QComboBox {
                background-color: #252526;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
                min-width: 130px;
                height: 22px;
            }
            QComboBox:hover { border-color: #007acc; }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 18px;
                border-left: 1px solid #3e3e42;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: #ffffff;
                selection-background-color: #007acc;
                border: 1px solid #3e3e42;
            }
        """)
        self.df_combo_status.currentIndexChanged.connect(self._on_display_filter_trigger)
        df_top.addWidget(self.df_combo_status)

        self.df_combo_field = QComboBox()
        self.df_combo_field.setToolTip("Onde pesquisar no segmento")
        self.df_combo_field.addItems([
            "In Source",
            "In Target",
            "In Both"
        ])
        self.df_combo_field.setStyleSheet("""
            QComboBox {
                background-color: #252526;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
                min-width: 85px;
                height: 22px;
            }
            QComboBox:hover { border-color: #007acc; }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 18px;
                border-left: 1px solid #3e3e42;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: #ffffff;
                selection-background-color: #007acc;
                border: 1px solid #3e3e42;
            }
        """)
        self.df_combo_field.currentIndexChanged.connect(self._on_display_filter_trigger)
        df_top.addWidget(self.df_combo_field)

        self.df_search_input = QLineEdit()
        self.df_search_input.setPlaceholderText("Search...")
        self.df_search_input.setClearButtonEnabled(True)
        self.df_search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #f1f1f1;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 11px;
                font-family: 'Segoe UI', sans-serif;
                min-width: 140px;
                height: 22px;
            }
            QLineEdit:focus { border: 1px solid #007acc; }
        """)
        self.df_search_input.returnPressed.connect(self._on_display_filter_trigger)
        df_top.addWidget(self.df_search_input)
        df_vbox.addLayout(df_top)

        df_bottom = QHBoxLayout()
        df_bottom.setContentsMargins(0, 0, 0, 0)
        df_bottom.setSpacing(6)

        self.df_chk_case = QCheckBox("aA Case Sensitive")
        self.df_chk_case.setToolTip("Diferenciar maiúsculas e minúsculas")
        self.df_chk_case.setStyleSheet("""
            QCheckBox {
                color: #cccccc;
                font-size: 10px;
                font-family: 'Segoe UI', sans-serif;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 12px;
                height: 12px;
            }
        """)
        self.df_chk_case.toggled.connect(self._on_display_filter_trigger)
        df_bottom.addWidget(self.df_chk_case)

        self.df_btn_refresh = QPushButton("⚚ Refresh Filters")
        self.df_btn_refresh.setToolTip("Atualiza a filtragem dos segmentos")
        self.df_btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #484848;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-family: 'Segoe UI', sans-serif;
                height: 20px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #007acc;
                color: #ffffff;
            }
        """)
        self.df_btn_refresh.clicked.connect(self._on_display_filter_trigger)
        df_bottom.addWidget(self.df_btn_refresh)

        self.df_btn_reset = QPushButton("✕ Reset Filters")
        self.df_btn_reset.setToolTip("Limpa todos os filtros e exibe todos os segmentos")
        self.df_btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #484848;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-family: 'Segoe UI', sans-serif;
                height: 20px;
            }
            QPushButton:hover {
                background-color: #444444;
                border-color: #c0392b;
                color: #ffffff;
            }
        """)
        self.df_btn_reset.clicked.connect(self._on_display_filter_reset)
        df_bottom.addWidget(self.df_btn_reset)

        self.df_btn_adf = QPushButton("🔻 Advanced Filter (F6)")
        self.df_btn_adf.setToolTip("Abrir painel Advanced Display Filter 2.0 (F6)")
        self.df_btn_adf.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #8eb4f3;
                border: 1px solid #007acc;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                height: 20px;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: #ffffff;
            }
        """)
        self.df_btn_adf.clicked.connect(self.advanced_filter_requested.emit)
        df_bottom.addWidget(self.df_btn_adf)

        df_vbox.addLayout(df_bottom)
        grp_df.add_widget(df_container)
        lr.addWidget(grp_df)

        # Grupo 4: Quality Assurance (Trados Studio QA)
        grp_qa = RibbonGroup("Quality Assurance")
        btn_spell = RibbonButton("✓abc", "Check\nSpelling (F7)", "Verificação ortográfica nativa do Windows (F7)")
        btn_spell.clicked.connect(self.spellcheck_requested.emit)
        grp_qa.add_widget(btn_spell)

        btn_verify = RibbonButton("📄✓", "Verify\n(F8)", "Executar verificação de QA Completa (F8) - ApSIC Xbench QA")
        btn_verify.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #2ecc71;
                border: 1px solid #27ae60;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #27ae60;
                color: white;
            }
        """)
        btn_verify.clicked.connect(self.verify_qa_requested.emit)
        grp_qa.add_widget(btn_verify)
        lr.addWidget(grp_qa)

        # Grupo 5: Batch Tasks (Trados Studio)
        grp_batch_rev = RibbonGroup("Batch Tasks")
        btn_batch_rev = self._create_batch_tasks_button()
        grp_batch_rev.add_widget(btn_batch_rev)
        lr.addWidget(grp_batch_rev)

        lr.addStretch()
        self._add_tab("Review", tab_rev)

        # Aba 3: Memórias & Ferramentas
        tab_tm = QWidget()
        lt = QHBoxLayout(tab_tm)
        lt.setContentsMargins(4, 2, 4, 2)
        lt.setSpacing(0)

        grp_tm_maint = RibbonGroup("Trados TM Management Utility")
        btn_tm_util = RibbonButton("🛠", "Utilitário\nTM", "Compactar, desduplicar e manter TMs (.sdltm)")
        btn_tm_util.clicked.connect(self.tm_utility_requested.emit)
        grp_tm_maint.add_widget(btn_tm_util)

        btn_tmed = RibbonButton("⚙", "Editor TM\n(Ctrl+M)", "Abrir visualizador completo de TM")
        btn_tmed.clicked.connect(self.tm_editor_requested.emit)
        grp_tm_maint.add_widget(btn_tmed)
        lt.addWidget(grp_tm_maint)

        grp_exp = RibbonGroup("Exportar")
        btn_sdltm = RibbonButton("💾", "Exportar\n.sdltm", "Exportar como RWS SDLTM")
        btn_sdltm.clicked.connect(self.export_sdltm_requested.emit)
        grp_exp.add_widget(btn_sdltm)

        btn_sdlxliff = RibbonButton("📄", "Exportar\n.sdlxliff", "Exportar bilingue SDLXLIFF")
        btn_sdlxliff.clicked.connect(self.export_sdlxliff_requested.emit)
        grp_exp.add_widget(btn_sdlxliff)

        btn_tmx = RibbonButton("🌐", "Exportar\nTMX", "Exportar base TMX")
        btn_tmx.clicked.connect(self.export_tmx_requested.emit)
        grp_exp.add_widget(btn_tmx)
        lt.addWidget(grp_exp)

        grp_slm = RibbonGroup("Small Language Model")
        btn_slm_studio_tm = RibbonButton("🤖", "SLM\nStudio", "Criar e treinar SLMs locais a partir de memórias .sdltm")
        btn_slm_studio_tm.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #a29bfe;
                border: 1px solid #6c5ce7;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6c5ce7;
                color: white;
            }
        """)
        btn_slm_studio_tm.clicked.connect(self.slm_studio_requested.emit)
        grp_slm.add_widget(btn_slm_studio_tm)
        lt.addWidget(grp_slm)

        lt.addStretch()
        self._add_tab("View & TMs", tab_tm)

    # ------------------------------------------------------------- Visão: TM
    def _setup_tm_ribbon(self) -> None:
        tab_tm = QWidget()
        lt = QHBoxLayout(tab_tm)
        lt.setContentsMargins(4, 2, 4, 2)
        lt.setSpacing(0)

        grp_tm_ops = RibbonGroup("Base de Dados SDLTM")
        btn_open_sdltm = RibbonButton("📂", "Abrir .sdltm\n(Trados TM)", "Carregar memória nativa do RWS Trados")
        btn_open_sdltm.clicked.connect(self.open_file_requested.emit)
        grp_tm_ops.add_widget(btn_open_sdltm)

        btn_exp_sdltm = RibbonButton("💾", "Exportar\n.sdltm", "Exportar como memória nativa do SDL Trados Studio")
        btn_exp_sdltm.clicked.connect(self.export_sdltm_requested.emit)
        grp_tm_ops.add_widget(btn_exp_sdltm)
        lt.addWidget(grp_tm_ops)

        grp_maint = RibbonGroup("Trados TM Management Utility")
        btn_util = RibbonButton("🛠", "Utilitário de\nManutenção", "Limpeza, Vacuum, Deduplicação e Integridade")
        btn_util.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        btn_util.clicked.connect(self.tm_utility_requested.emit)
        grp_maint.add_widget(btn_util)
        lt.addWidget(grp_maint)

        grp_slm_tm = RibbonGroup("SLM Neural")
        btn_slm_studio_nav = RibbonButton("🤖", "SLM\nStudio", "Criar e treinar SLMs locais a partir de memórias .sdltm")
        btn_slm_studio_nav.clicked.connect(self.slm_studio_requested.emit)
        grp_slm_tm.add_widget(btn_slm_studio_nav)
        lt.addWidget(grp_slm_tm)

        grp_interop = RibbonGroup("Interoperabilidade")
        btn_exp_tmx = RibbonButton("🌐", "Exportar\nTMX", "Exportar base em formato TMX")
        btn_exp_tmx.clicked.connect(self.export_tmx_requested.emit)
        grp_interop.add_widget(btn_exp_tmx)

        btn_exp_sdl = RibbonButton("📄", "Exportar\nSDLXLIFF", "Exportar bilingue SDLXLIFF")
        btn_exp_sdl.clicked.connect(self.export_sdlxliff_requested.emit)
        grp_interop.add_widget(btn_exp_sdl)
        lt.addWidget(grp_interop)

        lt.addStretch()
        self._add_tab("Memórias de Tradução", tab_tm)

    # ------------------------------------------------------------- Visão: BEM-VINDO (Welcome)
    def _setup_welcome_ribbon(self) -> None:
        tab_w = QWidget()
        lw = QHBoxLayout(tab_w)
        lw.setContentsMargins(4, 2, 4, 2)
        lw.setSpacing(0)

        grp_start = RibbonGroup("Começar")
        btn_new = RibbonButton("✨", "Novo\nProjeto", "Criar um novo projeto de tradução")
        btn_new.clicked.connect(self.new_project_requested.emit)
        grp_start.add_widget(btn_new)

        btn_open = RibbonButton("📂", "Abrir...\n(Ctrl+O)", "Abrir ficheiro de tradução bilingue")
        btn_open.clicked.connect(self.open_file_requested.emit)
        grp_start.add_widget(btn_open)

        btn_proj = RibbonButton("📋", "Projeto SDL\n(.sdlproj)", "Abrir projeto completo do Trados")
        btn_proj.clicked.connect(self.open_sdlproj_requested.emit)
        grp_start.add_widget(btn_proj)
        lw.addWidget(grp_start)

        grp_tools = RibbonGroup("Ferramentas Integradas")
        btn_xbench = RibbonButton("🔎", "ApSIC Xbench\nQA", "Executar verificação de qualidade QA")
        btn_xbench.setStyleSheet("color: #f39c12; font-weight: bold;")
        btn_xbench.clicked.connect(self.xbench_qa_requested.emit)
        grp_tools.add_widget(btn_xbench)

        btn_tm_util = RibbonButton("🛠", "Utilitário TM\nManagement", "Manutenção e limpeza de memórias .sdltm")
        btn_tm_util.clicked.connect(self.tm_utility_requested.emit)
        grp_tools.add_widget(btn_tm_util)
        lw.addWidget(grp_tools)

        lw.addStretch()
        self._add_tab("Início", tab_w)
