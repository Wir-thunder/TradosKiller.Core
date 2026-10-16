"""
ui.screens.editor_screen - Editor screen for translation files with Trados Review & Find/Replace bars.

Features:
- Integrated Trados Ribbon actions
- Inline Find & Replace bar (Ctrl+F / Ctrl+H)
- Review Bar with live status counters (Untranslated, Draft, Translated, Approved, Rejected)
- Confirm & Next workflow (Ctrl+Enter)
- Concordance search (F3) and Spell Check (F7)
- Virtualized & filterable bilingual segments table
"""
from __future__ import annotations

import os
import re
import uuid
import tempfile
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QItemSelectionModel
from PySide6.QtGui import QColor, QPalette, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QTableView, QProgressBar, QFrame, QMessageBox,
    QTextEdit, QAbstractItemView, QSplitter, QHeaderView
)

from core.tm import TranslationMemory
from core.segment import display_text, SegState, SegOrigin
from ui.segments_model import SegmentsModel
from ui.find_replace_bar import FindReplaceBar
from ui.review_bar import ReviewBar
from io_layer.tmx import iter_tmx, detect_tmx_langs
from io_layer.sdlxliff import iter_sdlxliff, detect_sdlxliff_langs
from io_layer.sdltm import iter_sdltm, detect_sdltm_langs, write_sdltm
from io_layer.tmx_writer import write_tmx
from io_layer.sdlxliff_writer import write_sdlxliff
from core.spellcheck import WindowsSpellChecker
from core.project import Project
from ui.advanced_display_filter import AdvancedDisplayFilterPanel
from core.advanced_filter import AdvancedFilterCriteria
from core.attached_tm import AttachedTMConfig, AttachedTMManager, TMMatch
from core.slm import OllamaClient
from core.config import load_config, save_config


class SLMTranslateWorker(QThread):
    """Thread em segundo plano para traduzir segmento com SLM sem travar a interface."""
    finished = Signal(str, int, int)  # translation, row_id, row_index
    error = Signal(str)

    def __init__(self, prompt: str, model: str, row_id: int, row_index: int,
                 context_terms: list = None, temperature: float = 0.1) -> None:
        super().__init__()
        self.prompt = prompt
        self.model = model
        self.row_id = row_id
        self.row_index = row_index
        self.context_terms = context_terms or []
        self.temperature = temperature

    def run(self) -> None:
        client = OllamaClient()
        try:
            res = client.translate(
                self.prompt,
                model=self.model,
                context_terms=self.context_terms,
                temperature=self.temperature
            )
            self.finished.emit(res, self.row_id, self.row_index)
        except Exception as e:
            self.error.emit(str(e))


class SLMSuggestionWorker(QThread):
    """Thread assíncrona para buscar sugestão preditiva da SLM para o painel de correspondências."""
    ready = Signal(str, int)  # translation, row_id

    def __init__(self, prompt: str, model: str, row_id: int,
                 context_terms: list = None, temperature: float = 0.1) -> None:
        super().__init__()
        self.prompt = prompt
        self.model = model
        self.row_id = row_id
        self.context_terms = context_terms or []
        self.temperature = temperature

    def run(self) -> None:
        client = OllamaClient()
        try:
            res = client.translate(
                self.prompt,
                model=self.model,
                context_terms=self.context_terms,
                temperature=self.temperature
            )
            if res and not res.startswith("[Erro"):
                self.ready.emit(res, self.row_id)
        except Exception:
            pass


class FileLoaderThread(QThread):
    """Background thread for loading large files without freezing UI."""
    finished = Signal(object, str, str, int)  # tm, src_lang, tgt_lang, count
    progress = Signal(int, str)               # count, status_message
    error = Signal(str)
    
    def __init__(self, path: str, ext: str) -> None:
        super().__init__()
        self.path = path
        self.ext = ext
        self.tm = None
    
    def run(self) -> None:
        try:
            # 1. Detecção ultra-rápida de idiomas no cabeçalho
            src, tgt = None, None
            if self.ext in (".sdlxliff", ".xlf", ".xliff"):
                src, tgt = detect_sdlxliff_langs(self.path)
            elif self.ext == ".tmx":
                src, tgt = detect_tmx_langs(self.path)
            elif self.ext == ".sdltm":
                src, tgt = detect_sdltm_langs(self.path)

            if self.isInterruptionRequested():
                return

            # 2. Base de dados temporária segura no diretório temporário do sistema operacional
            cache_dir = os.path.join(tempfile.gettempdir(), "cat_tool_cache")
            os.makedirs(cache_dir, exist_ok=True)
            db = os.path.join(cache_dir, f"cat_cache_{uuid.uuid4().hex[:12]}.db")
            tm = TranslationMemory(db)

            # 3. Callback de progresso com verificação de interrupção
            def on_progress(count: int):
                if self.isInterruptionRequested():
                    raise InterruptedError("Operação cancelada pelo utilizador.")
                self.progress.emit(count, f"A processar segmentos: {count:,}...")

            # 4. Inserção em streaming
            if self.ext == ".tmx":
                n = tm.add_many(iter_tmx(self.path, src, tgt), src or "", tgt or "", progress_callback=on_progress)
            elif self.ext == ".sdltm":
                n = tm.add_many(iter_sdltm(self.path, src, tgt), src or "", tgt or "", progress_callback=on_progress)
            else:
                n = tm.add_many(iter_sdlxliff(self.path), src or "", tgt or "", progress_callback=on_progress)

            if self.isInterruptionRequested():
                return

            # Para arquivos pequenos/médios (<50k), reconstrói o índice FTS imediatamente
            if n <= 50000:
                tm.rebuild_fts()

            self.tm = tm
            self.finished.emit(tm, src or "en-US", tgt or "pt-BR", n)
        except InterruptedError:
            pass
        except Exception as e:
            self.error.emit(str(e))



class EditorScreen(QWidget):
    """Main editor screen for translation work with Trados review facade."""
    
    file_loaded = Signal()
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tm: TranslationMemory | None = None
        self.model: SegmentsModel | None = None
        self._current_row = -1
        self._current_filter_state = "all"
        self._src_lang = "en-US"
        self._tgt_lang = "pt-BR"
        self._spell_checker = WindowsSpellChecker("pt-PT")
        self._current_project: Optional[Project] = None
        self._current_file_index = 0
        self.loader: Optional[FileLoaderThread] = None
        self.attached_tms: list[AttachedTMConfig] = []
        self._slm_client = OllamaClient()
        cfg = load_config()
        configured_model = getattr(cfg, "ollama_model", "toyotao:latest")
        if configured_model in ("llama3.2", "llama3"):
            configured_model = "toyotao:latest"
        self._active_slm_model = configured_model
        self._auto_slm_suggest = True
        self._slm_worker: Optional[SLMTranslateWorker] = None
        self._slm_lookup_worker: Optional[SLMSuggestionWorker] = None
        
        self._apply_dark_theme()
        self._build_ui()
        self._setup_shortcuts()

    def _apply_dark_theme(self) -> None:
        """Apply dark theme consistent with Trados Studio."""
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(35, 35, 35))
        palette.setColor(QPalette.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.Button, QColor(30, 30, 30))
        palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.Highlight, QColor(0, 122, 204))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        self.setPalette(palette)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ---------------- Navegação de ficheiros do projeto
        self.nav_frame = QFrame()
        self.nav_frame.setStyleSheet("background-color: #252526; border-radius: 4px;")
        nav_layout = QHBoxLayout(self.nav_frame)
        nav_layout.setContentsMargins(8, 4, 8, 4)

        nav_layout.addWidget(QLabel("Ficheiro:"))
        self.file_label = QLabel("Nenhum ficheiro aberto")
        self.file_label.setStyleSheet("color: #8eb4f3; font-weight: bold;")
        nav_layout.addWidget(self.file_label)

        nav_layout.addStretch()

        self.btn_prev = QPushButton("◀ Ficheiro Anterior")
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background-color: #333; color: #ddd; border: 1px solid #444;
                border-radius: 3px; padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { background-color: #444; }
        """)
        self.btn_prev.clicked.connect(self._prev_file)
        self.btn_prev.setEnabled(False)
        nav_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Próximo Ficheiro ▶")
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #333; color: #ddd; border: 1px solid #444;
                border-radius: 3px; padding: 3px 8px; font-size: 11px;
            }
            QPushButton:hover { background-color: #444; }
        """)
        self.btn_next.clicked.connect(self._next_file)
        self.btn_next.setEnabled(False)
        nav_layout.addWidget(self.btn_next)

        layout.addWidget(self.nav_frame)

        # ---------------- Review Bar (Workflow e Filtro de Estado)
        self.review_bar = ReviewBar(self)
        self.review_bar.confirm_and_next_requested.connect(self.confirm_and_next)
        self.review_bar.status_change_requested.connect(self.set_current_status)
        self.review_bar.filter_changed.connect(self._on_filter_changed)
        self.review_bar.next_untranslated_requested.connect(self.next_untranslated)
        self.review_bar.concordance_requested.connect(self.show_concordance)
        self.review_bar.xbench_qa_requested.connect(self.show_xbench_qa)
        self.review_bar.advanced_filter_requested.connect(self.toggle_advanced_filter)
        self.review_bar.project_settings_requested.connect(self.show_project_settings)
        self.review_bar.slm_requested.connect(self.translate_current_with_slm)
        self.review_bar.slm_studio_requested.connect(self.show_slm_studio)
        layout.addWidget(self.review_bar)

        # ---------------- Find & Replace Bar (Ctrl+F / Ctrl+H)
        self.find_replace_bar = FindReplaceBar(self)
        self.find_replace_bar.find_next_signal.connect(self._find_next)
        self.find_replace_bar.find_prev_signal.connect(self._find_prev)
        self.find_replace_bar.replace_signal.connect(self._replace_current)
        self.find_replace_bar.replace_all_signal.connect(self._replace_all)
        self.find_replace_bar.filter_signal.connect(self._live_search_filter)
        layout.addWidget(self.find_replace_bar)

        # ---------------- Statistics & Progress dashboard
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background-color: #202022; border-radius: 4px; padding: 2px;")
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(8, 4, 8, 4)
        stats_layout.setSpacing(2)

        self._stats_label = QLabel("Nenhum ficheiro carregado")
        self._stats_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        stats_layout.addWidget(self._stats_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 3px;
                background-color: #333333;
            }
            QProgressBar::chunk {
                background-color: #27ae60;
                border-radius: 3px;
            }
        """)
        stats_layout.addWidget(self._progress_bar)
        self.stats_frame = stats_frame
        self.stats_frame.setVisible(False)
        layout.addWidget(stats_frame)

        # ---------------- Advanced Display Filter 2.0 (Trados Studio ADF)
        self.adv_filter = AdvancedDisplayFilterPanel(self)
        self.adv_filter.filter_applied.connect(self._on_advanced_filter_applied)
        self.adv_filter.filter_reversed.connect(self._on_advanced_filter_applied)
        self.adv_filter.filter_cleared.connect(self._on_advanced_filter_cleared)
        self.adv_filter.generate_requested.connect(self._on_generate_filtered)
        self.adv_filter.setVisible(False)
        layout.addWidget(self.adv_filter)

        # ---------------- Splitter principal Vertical (Layout Oficial Trados Studio)
        self.main_splitter = QSplitter(Qt.Vertical)
        splitter = self.main_splitter

        # 1. Painel Superior: Translation Results (TM Matches, Concordância, SLM Neural)
        self.results_panel = QFrame()
        results_panel = self.results_panel
        results_panel.setStyleSheet("background-color: #202022; border: 1px solid #333333; border-radius: 4px;")
        rf_layout = QVBoxLayout(results_panel)
        rf_layout.setContentsMargins(8, 4, 8, 4)
        rf_layout.setSpacing(4)

        rf_header = QHBoxLayout()
        rf_header.setSpacing(8)

        icon_res = QLabel("📋")
        rf_header.addWidget(icon_res)

        title_res = QLabel("Translation Results")
        title_res.setStyleSheet("color: #8eb4f3; font-weight: bold; font-size: 11px;")
        rf_header.addWidget(title_res)

        self.lbl_attached_tm = QLabel("[Nenhuma TM associada]")
        self.lbl_attached_tm.setStyleSheet("color: #e67e22; font-size: 10px; background-color: #2b2210; border: 1px solid #7d4806; border-radius: 3px; padding: 1px 6px;")
        rf_header.addWidget(self.lbl_attached_tm)

        rf_header.addStretch()

        self.btn_toggle_results = QPushButton("▲ Ocultar Painel (Alt+1)")
        self.btn_toggle_results.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #888888; border: 1px solid #444;
                border-radius: 3px; padding: 2px 8px; font-size: 10px;
            }
            QPushButton:hover { background-color: #333; color: white; }
        """)
        self.btn_toggle_results.clicked.connect(self.toggle_results_panel)
        rf_header.addWidget(self.btn_toggle_results)

        btn_apply_match = QPushButton("Aplicar Tradução (Ctrl+T)")
        btn_apply_match.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f; color: #93c5fd; border: 1px solid #3b82f6;
                border-radius: 3px; padding: 2px 10px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb; color: #ffffff; }
        """)
        btn_apply_match.clicked.connect(self._apply_best_match)
        rf_header.addWidget(btn_apply_match)

        btn_copy_src = QPushButton("Copiar Fonte (Ctrl+Ins)")
        btn_copy_src.setStyleSheet("""
            QPushButton {
                background-color: #333; color: #ddd; border: 1px solid #444;
                border-radius: 3px; padding: 2px 8px; font-size: 10px;
            }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        btn_copy_src.clicked.connect(self.copy_source_to_target)
        rf_header.addWidget(btn_copy_src)

        self.btn_settings_tm = QPushButton("⚙ Associar TM (Alt+F8)")
        self.btn_settings_tm.setStyleSheet("""
            QPushButton {
                background-color: #333; color: #aaa; border: 1px solid #444;
                border-radius: 3px; padding: 2px 8px; font-size: 10px;
            }
            QPushButton:hover { background-color: #444; color: white; }
        """)
        self.btn_settings_tm.clicked.connect(self.show_project_settings)
        rf_header.addWidget(self.btn_settings_tm)
        rf_layout.addLayout(rf_header)

        self.fuzzy_edit = QTextEdit()
        self.fuzzy_edit.setReadOnly(True)
        self.fuzzy_edit.setStyleSheet("""
            QTextEdit {
                background-color: #181818;
                color: #e0e0e0;
                border: 1px solid #2d2d30;
                border-radius: 3px;
                padding: 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                line-height: 1.4;
            }
        """)
        rf_layout.addWidget(self.fuzzy_edit)
        splitter.addWidget(results_panel)

        # 2. Painel Central: Grelha Bilingue de Edição (Tabela Virtualizada com In-Cell Editing)
        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setMinimumSectionSize(26)
        self.table.setStyleSheet("""
            QTableView {
                background-color: #1e1e1e;
                gridline-color: #2d2d30;
                selection-background-color: #094771;
                selection-color: white;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QTableView::item {
                padding: 4px 6px;
            }
            QTableView::item:selected {
                background-color: #094771;
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
        """)
        splitter.addWidget(self.table)

        # 3. Painel Inferior: Editor Focado do Segmento Ativo (Sincronizado)
        edit_panel = QFrame()
        edit_panel.setStyleSheet("background-color: #202022; border: 1px solid #333333; border-radius: 4px;")
        ev = QVBoxLayout(edit_panel)
        ev.setContentsMargins(8, 4, 8, 4)
        ev.setSpacing(4)

        sub_splitter = QSplitter(Qt.Horizontal)

        # Coluna Fonte
        src_box = QWidget()
        src_v = QVBoxLayout(src_box)
        src_v.setContentsMargins(0, 0, 0, 0)
        src_lbl = QLabel("Segmento Fonte:")
        src_lbl.setStyleSheet("color: #8eb4f3; font-weight: bold; font-size: 11px;")
        src_v.addWidget(src_lbl)
        self.src_edit = QPlainTextEdit()
        self.src_edit.setReadOnly(True)
        self.src_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1a1a1a;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
        """)
        src_v.addWidget(self.src_edit)
        sub_splitter.addWidget(src_box)

        # Coluna Tradução
        tgt_box = QWidget()
        tgt_v = QVBoxLayout(tgt_box)
        tgt_v.setContentsMargins(0, 0, 0, 0)
        tgt_header = QHBoxLayout()
        tgt_lbl = QLabel("Tradução Ativa (Ctrl+Enter para Confirmar):")
        tgt_lbl.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 11px;")
        tgt_header.addWidget(tgt_lbl)
        tgt_header.addStretch()

        btn_confirm = QPushButton("✓ Confirmar & Próximo (Ctrl+Enter)")
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white; border: none;
                border-radius: 3px; padding: 2px 10px; font-weight: bold; font-size: 10px;
            }
            QPushButton:hover { background-color: #2ecc71; }
        """)
        btn_confirm.clicked.connect(self.confirm_and_next)
        tgt_header.addWidget(btn_confirm)
        tgt_v.addLayout(tgt_header)

        self.tgt_edit = QPlainTextEdit()
        self.tgt_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 1px solid #27ae60;
                border-radius: 4px;
                padding: 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QPlainTextEdit:focus {
                border: 2px solid #2ecc71;
            }
        """)
        self.tgt_edit.textChanged.connect(self._on_tgt_text_changed)
        tgt_v.addWidget(self.tgt_edit)
        sub_splitter.addWidget(tgt_box)

        sub_splitter.setSizes([380, 500])
        ev.addWidget(sub_splitter)
        splitter.addWidget(edit_panel)

        splitter.setSizes([100, 480, 140])
        layout.addWidget(splitter)

    def _setup_shortcuts(self) -> None:
        """Instala os atalhos de teclado padrão Trados Studio."""
        QShortcut(QKeySequence("Ctrl+F"), self, self.show_find)
        QShortcut(QKeySequence("Ctrl+H"), self, self.show_replace)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.confirm_and_next)
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, lambda: self.set_current_status(SegState.APPROVED))
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, lambda: self.set_current_status(SegState.REJECTED))
        QShortcut(QKeySequence("Ctrl+Alt+Down"), self, self.next_untranslated)
        QShortcut(QKeySequence("Ctrl+Up"), self, self.prev_segment)
        QShortcut(QKeySequence("Ctrl+Down"), self, self.next_segment)
        QShortcut(QKeySequence("Ctrl+Insert"), self, self.copy_source_to_target)
        QShortcut(QKeySequence("F3"), self, self.show_concordance)
        QShortcut(QKeySequence("F6"), self, self.toggle_advanced_filter)
        QShortcut(QKeySequence("F7"), self, self._check_spelling)
        QShortcut(QKeySequence("F8"), self, self.show_xbench_qa)
        QShortcut(QKeySequence("Ctrl+Alt+M"), self, self.merge_with_next_segment)
        QShortcut(QKeySequence("Ctrl+Alt+S"), self, self.split_current_segment)
        QShortcut(QKeySequence("Alt+F8"), self, self.show_project_settings)
        QShortcut(QKeySequence("Ctrl+T"), self, self._apply_best_match)
        QShortcut(QKeySequence("Ctrl+G"), self, self.translate_current_with_slm)
        QShortcut(QKeySequence("Alt+1"), self, self.toggle_results_panel)

    def toggle_results_panel(self) -> None:
        """Alterna a visibilidade do painel de Resultados de Tradução para despoluir a tela (Alt+1)."""
        vis = not self.results_panel.isVisible()
        self.results_panel.setVisible(vis)
        self.btn_toggle_results.setText("▲ Ocultar Painel (Alt+1)" if vis else "▼ Mostrar Resultados (Alt+1)")
        if vis:
            self.main_splitter.setSizes([90, 520, 140])
        else:
            self.main_splitter.setSizes([0, 620, 140])

    # ------------------------------------------------------------- Localizar & Substituir
    def show_find(self) -> None:
        selected_text = self.src_edit.textCursor().selectedText() or self.tgt_edit.textCursor().selectedText()
        self.find_replace_bar.show_find(selected_text)

    def show_replace(self) -> None:
        selected_text = self.src_edit.textCursor().selectedText() or self.tgt_edit.textCursor().selectedText()
        self.find_replace_bar.show_replace(selected_text)

    def _live_search_filter(self, query: str, field: str) -> None:
        """Filtro dinâmico na tabela conforme o usuário digita no Find."""
        if not self.model or not self.tm:
            return
        if query.strip():
            count = self.model.apply_filter(query=query, field=field, state=self._current_filter_state)
            self.find_replace_bar.update_match_count(1 if count > 0 else 0, count)
            if count > 0:
                self._select_row(0)
        else:
            self.model.apply_filter(query="", field="both", state=self._current_filter_state)
            self.find_replace_bar.update_match_count(0, 0)

    def _find_next(self, text: str, field: str, case: bool, whole: bool, regex: bool) -> None:
        if not self.model or self.model.rowCount() == 0:
            return
        start_row = self._current_row + 1
        total = self.model.rowCount()
        for r in range(start_row, total):
            if self._row_matches(r, text, field, case, regex):
                self._select_row(r)
                self.find_replace_bar.update_match_count(r + 1, total)
                return
        # Loop para o início
        for r in range(0, start_row):
            if self._row_matches(r, text, field, case, regex):
                self._select_row(r)
                self.find_replace_bar.update_match_count(r + 1, total)
                return

    def _find_prev(self, text: str, field: str, case: bool, whole: bool, regex: bool) -> None:
        if not self.model or self.model.rowCount() == 0:
            return
        start_row = self._current_row - 1
        total = self.model.rowCount()
        for r in range(start_row, -1, -1):
            if self._row_matches(r, text, field, case, regex):
                self._select_row(r)
                self.find_replace_bar.update_match_count(r + 1, total)
                return
        for r in range(total - 1, start_row, -1):
            if self._row_matches(r, text, field, case, regex):
                self._select_row(r)
                self.find_replace_bar.update_match_count(r + 1, total)
                return

    def _row_matches(self, row: int, query: str, field: str, case: bool, use_regex: bool) -> bool:
        seg = self.model.segment_at(row)
        if not seg:
            return False
        src = display_text(seg.source)
        tgt = display_text(seg.target)
        targets = []
        if field in ("source", "both"):
            targets.append(src)
        if field in ("target", "both"):
            targets.append(tgt)

        for t in targets:
            if use_regex:
                flags = 0 if case else re.IGNORECASE
                if re.search(query, t, flags):
                    return True
            else:
                if case:
                    if query in t:
                        return True
                else:
                    if query.lower() in t.lower():
                        return True
        return False

    def _replace_current(self, find_text: str, repl_text: str, field: str, case: bool, use_regex: bool) -> None:
        if self._current_row < 0 or not self.model:
            return
        curr_text = self.tgt_edit.toPlainText()
        if use_regex:
            flags = 0 if case else re.IGNORECASE
            new_text = re.sub(find_text, repl_text, curr_text, flags=flags)
        else:
            if case:
                new_text = curr_text.replace(find_text, repl_text)
            else:
                pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                new_text = pattern.sub(repl_text, curr_text)
        if new_text != curr_text:
            self.tgt_edit.setPlainText(new_text)
            self.save_current()

    def _replace_all(self, find_text: str, repl_text: str, field: str, case: bool, use_regex: bool) -> None:
        if not self.tm:
            return
        scope_field = "target" if field == "target" else ("source" if field == "source" else "target")
        n = self.tm.bulk_replace(find=find_text, repl=repl_text, field=scope_field,
                                 case_sensitive=case, use_regex=use_regex)
        self.model.refresh()
        self._update_stats()
        QMessageBox.information(self, "Substituir Todos", f"{n} ocorrência(s) substituída(s) com sucesso.")

    # ------------------------------------------------------------- Review Bar Workflow
    def confirm_and_next(self) -> None:
        """Workflow clássico do Trados Studio: grava, marca Traduzido e pula para o próximo."""
        if not self.model or self._current_row < 0:
            return
        self.save_current()
        self.set_current_status(SegState.TRANSLATED)
        self.next_segment()

    def set_current_status(self, state: SegState) -> None:
        """Altera o estado do segmento atual (Draft, Translated, Approved, Rejected)."""
        if not self.model or self._current_row < 0 or not self.tm:
            return
        seg = self.model.segment_at(self._current_row)
        if not seg or seg.row_id < 0:
            return
        new_tgt = self.tgt_edit.toPlainText()
        self.tm.update_target(seg.row_id, new_tgt, state=state)
        seg.state = state
        seg.target = new_tgt
        idx = self.model.index(self._current_row, 2)
        self.model.dataChanged.emit(idx, idx, [Qt.DisplayRole, Qt.ForegroundRole])
        self._update_stats()

    def _on_filter_changed(self, state_key: str) -> None:
        """Filtra os segmentos visíveis pelas abas do ReviewBar."""
        self._current_filter_state = state_key
        if self.model:
            self.model.apply_filter(query=self.find_replace_bar.find_edit.text(),
                                    field="both", state=state_key)
            if self.model.rowCount() > 0:
                self._select_row(0)

    def apply_display_filter(self, query: str = "", field: str = "In Both",
                             status_str: str = "All segments", case_sensitive: bool = False) -> int:
        """Aplica o filtro da barra de Display Filter (Trados Review Ribbon)."""
        if not self.model or not self.tm:
            return 0

        status_map = {
            "all segments": "all",
            "all": "all",
            "not translated": "untranslated",
            "untranslated": "untranslated",
            "draft": "draft",
            "translated": "translated",
            "translation approved": "approved",
            "approved": "approved",
            "translation rejected": "rejected",
            "rejected": "rejected"
        }
        st = status_map.get(status_str.strip().lower(), "all")
        self._current_filter_state = st

        field_map = {
            "in source": "source",
            "source": "source",
            "in target": "target",
            "target": "target",
            "in both": "both",
            "both": "both"
        }
        fd = field_map.get(field.strip().lower(), "both")

        count = self.model.apply_filter(query=query, field=fd, state=st, case_sensitive=case_sensitive)
        self._update_stats()
        if hasattr(self, "review_bar") and hasattr(self.review_bar, "_pills"):
            if st in self.review_bar._pills:
                self.review_bar._pills[st].setChecked(True)
                for k, p in self.review_bar._pills.items():
                    p._update_appearance()
        if count > 0:
            self._select_row(0)
        return count

    def reset_display_filter(self) -> None:
        """Reseta os filtros de exibição para mostrar todos os segmentos."""
        if not self.model or not self.tm:
            return
        self._current_filter_state = "all"
        self.model.clear_filter()
        self._update_stats()
        if hasattr(self, "review_bar") and hasattr(self.review_bar, "_pills"):
            self.review_bar._pills["all"].setChecked(True)
            for k, p in self.review_bar._pills.items():
                p._update_appearance()
        if self.model.rowCount() > 0:
            self._select_row(0)

    # ------------------------------------------------------------- Advanced Display Filter 2.0
    def _on_advanced_filter_applied(self, criteria: AdvancedFilterCriteria) -> None:
        """Aplica os filtros avançados definidos no Advanced Display Filter 2.0."""
        if not self.model or not self.tm:
            return
        count = self.model.apply_advanced_filter(criteria)
        total = self.tm.count()
        self.adv_filter.update_match_count(count, total)
        if count > 0:
            self._select_row(0)

    def _on_advanced_filter_cleared(self) -> None:
        """Restaura a lista completa de segmentos."""
        if not self.model or not self.tm:
            return
        self.model.clear_filter()
        total = self.tm.count()
        self.adv_filter.update_match_count(total, total)
        if total > 0:
            self._select_row(0)

    def _on_generate_filtered(self) -> None:
        """Abre o diálogo de geração de ficheiro com base nos segmentos filtrados (ADF 2.0 Generate)."""
        if not self.model or not self.tm:
            QMessageBox.warning(self, "Gerar Ficheiro", "Nenhum documento ou memória carregada.")
            return

        filtered_segs = self.model.get_current_segments()
        total = self.tm.count()
        filter_summary = self.adv_filter.txt_filters_applied.text()

        from ui.generate_filtered_dialog import GenerateFilteredDialog
        dialog = GenerateFilteredDialog(
            segments=filtered_segs,
            total_segments_count=total,
            filter_summary=filter_summary,
            src_lang=self._src_lang,
            tgt_lang=self._tgt_lang,
            source_file_name=getattr(self.tm, "db_path", "Document"),
            parent=self
        )
        dialog.exec()

    def toggle_advanced_filter(self) -> None:
        """Alterna a visibilidade do Advanced Display Filter 2.0 (F6)."""
        self.adv_filter.setVisible(self.adv_filter.isHidden())

    # ------------------------------------------------------------- Navegação
    def prev_segment(self) -> None:
        if self._current_row > 0:
            self._select_row(self._current_row - 1)

    def next_segment(self) -> None:
        if self.model and self._current_row < self.model.rowCount() - 1:
            self._select_row(self._current_row + 1)

    def next_untranslated(self) -> None:
        """Pula para o próximo segmento cujo estado seja untranslated ou alvo esteja vazio."""
        if not self.model:
            return
        start = self._current_row + 1
        for r in range(start, self.model.rowCount()):
            seg = self.model.segment_at(r)
            if seg and (seg.state == SegState.UNTRANSLATED or not seg.target.strip()):
                self._select_row(r)
                return
        for r in range(0, start):
            seg = self.model.segment_at(r)
            if seg and (seg.state == SegState.UNTRANSLATED or not seg.target.strip()):
                self._select_row(r)
                return
        QMessageBox.information(self, "Navegação", "Todos os segmentos disponíveis já foram traduzidos!")

    def copy_source_to_target(self) -> None:
        """Copia a fonte para a tradução."""
        self.tgt_edit.setPlainText(self.src_edit.toPlainText())
        self.tgt_edit.setFocus()

    def clear_target(self) -> None:
        """Limpa o campo de tradução."""
        self.tgt_edit.clear()
        self.tgt_edit.setFocus()

    def merge_with_next_segment(self) -> bool:
        """Mescla o segmento atual com o próximo (Ctrl+Alt+M), desfazendo quebras indevidas."""
        if not self.model or self._current_row < 0 or not self.tm:
            return False
        if self._current_row >= self.model.rowCount() - 1:
            QMessageBox.information(self, "Mesclar Segmentos", "Não há próximo segmento para mesclar.")
            return False

        seg1 = self.model.segment_at(self._current_row)
        seg2 = self.model.segment_at(self._current_row + 1)
        if not seg1 or not seg2:
            return False

        self.save_current()
        merged_id = self.tm.merge_segments(seg1.row_id, seg2.row_id)
        if merged_id:
            self.model.refresh()
            self._select_row(self._current_row)
            self._update_stats()
            updated_seg = self.model.segment_at(self._current_row)
            if updated_seg:
                self.src_edit.setPlainText(display_text(updated_seg.source))
                self.tgt_edit.setPlainText(display_text(updated_seg.target))
            return True
        return False

    def split_current_segment(self) -> bool:
        """Divide o segmento atual em dois na posição do cursor no campo Fonte (Ctrl+Alt+S)."""
        if not self.model or self._current_row < 0 or not self.tm:
            return False

        seg = self.model.segment_at(self._current_row)
        if not seg:
            return False

        pos = self.src_edit.textCursor().position()
        src_text = self.src_edit.toPlainText()

        if pos <= 0 or pos >= len(src_text):
            QMessageBox.warning(
                self, "Dividir Segmento",
                "Posicione o cursor no texto Fonte exatamente onde deseja dividir o segmento."
            )
            return False

        self.save_current()
        res = self.tm.split_segment(seg.row_id, pos)
        if res:
            self.model.refresh()
            self._select_row(self._current_row)
            self._update_stats()
            return True
        return False

    def auto_heal_segmentation(self) -> None:
        """Varre o ficheiro e cura automaticamente todas as sentenças quebradas por regras legadas."""
        if not self.tm or self.tm.count() == 0:
            return

        count = self.tm.heal_broken_segmentation()
        if count > 0:
            self.model.refresh()
            self._select_row(0)
            self._update_stats()
            QMessageBox.information(
                self, "Segmentação Inteligente",
                f"Foram identificados e reunificados com sucesso {count} segmento(s) quebrados indevidamente!"
            )
        else:
            QMessageBox.information(
                self, "Segmentação Inteligente",
                "Nenhum segmento quebrado indevidamente foi detectado. Todas as sentenças estão íntegras."
            )

    def _select_row(self, row: int) -> None:
        if not self.model or row < 0 or row >= self.model.rowCount():
            return
        idx = self.model.index(row, 0)
        self.table.setCurrentIndex(idx)
        self.table.scrollTo(idx, QAbstractItemView.PositionAtCenter)

    # ------------------------------------------------------------- Carregamento
    def load_file(self, path: str) -> None:
        """Carrega um ficheiro de tradução bilingue (.sdlxliff, .sdltm, .tmx)."""
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".tmx", ".sdlxliff", ".xlf", ".xliff", ".sdltm"):
            QMessageBox.warning(self, "Formato não suportado", "Apenas ficheiros TMX, SDLXLIFF e SDLTM são suportados.")
            return

        self._active_loading_path = path
        base_name = os.path.basename(path)
        self.file_label.setText(f"{base_name} (A carregar...)")

        if not hasattr(self, "_active_loaders"):
            self._active_loaders = []

        if self.loader is not None and self.loader.isRunning():
            self.loader.requestInterruption()
            self.loader.quit()
            self._active_loaders.append(self.loader)

        self._active_loaders = [t for t in self._active_loaders if t.isRunning()]

        self.loader = FileLoaderThread(path, ext)
        self.loader.progress.connect(self._on_load_progress)
        self.loader.finished.connect(lambda tm, src, tgt, cnt, p=path: self._on_file_loaded(tm, src, tgt, cnt, p))
        self.loader.error.connect(self._on_load_error)
        self.loader.start()

    def _on_load_progress(self, count: int, msg: str) -> None:
        base_name = os.path.basename(getattr(self, "_active_loading_path", "Ficheiro"))
        self.file_label.setText(f"{base_name} ({count:,} segmentos carregados...)")

    def load_project(self, project: Project) -> None:
        """Carrega um projeto com múltiplos ficheiros e memórias anexadas."""
        self._current_project = project
        self._current_file_index = 0
        if not project.files:
            QMessageBox.warning(self, "Projeto Vazio", "O projeto não contém ficheiros para traduzir.")
            return
        self._update_nav_buttons()
        self.load_file(project.files[0].path)

    def _on_file_loaded(self, tm: TranslationMemory, src_lang: str, tgt_lang: str, count: int, path: str = "") -> None:
        self.tm = tm
        self._src_lang = src_lang
        self._tgt_lang = tgt_lang
        base_name = os.path.basename(path) if path else self.file_label.text().split(" (")[0]
        self.file_label.setText(f"{base_name} ({count:,} segmentos)")

        # Anexa e sincroniza TMs de referência do projeto se existirem
        if self._current_project and self._current_project.tm_paths:
            self.tm._attach_reference_tms(self._current_project.tm_paths)
            for p in self._current_project.tm_paths:
                if not any(os.path.abspath(t.path) == os.path.abspath(p) for t in self.attached_tms):
                    self.attached_tms.append(AttachedTMConfig(path=p, lookup=True, concordance=True, update=True))

        self._update_tm_badge()

        self.model = SegmentsModel(tm)
        self.table.setModel(self.model)
        self.model.dataChanged.connect(self._on_model_data_changed)

        if self.table.selectionModel():
            self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        if count > 0:
            self._select_row(0)

        self._update_stats()
        self.file_loaded.emit()

    def closeEvent(self, event) -> None:
        if self.loader is not None and self.loader.isRunning():
            self.loader.requestInterruption()
            self.loader.quit()
            self.loader.wait(1000)
        super().closeEvent(event)

    def _on_load_error(self, error: str) -> None:
        QMessageBox.critical(self, "Erro", f"Falha ao carregar ficheiro:\n{error}")

    def _on_selection_changed(self) -> None:
        if not self.model or not self.table.selectionModel():
            return
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return

        row = indexes[0].row()
        self._current_row = row
        seg = self.model.segment_at(row)
        if seg:
            self.src_edit.setPlainText(display_text(seg.source))
            self._is_syncing = True
            self.tgt_edit.setPlainText(display_text(seg.target))
            self._is_syncing = False
            self._lookup_matches(seg)

    def _on_model_data_changed(self, top_left, bottom_right, roles=None) -> None:
        """Sincroniza o editor de texto inferior quando uma célula é editada na tabela."""
        if getattr(self, "_is_syncing", False):
            return
        if self._current_row >= top_left.row() and self._current_row <= bottom_right.row():
            seg = self.model.segment_at(self._current_row)
            if seg:
                self._is_syncing = True
                self.tgt_edit.blockSignals(True)
                self.tgt_edit.setPlainText(display_text(seg.target))
                self.tgt_edit.blockSignals(False)
                self._is_syncing = False
        self._update_stats()

    def _on_tgt_text_changed(self) -> None:
        """Sincroniza a célula da tabela em tempo real enquanto o utilizador escreve no editor."""
        if getattr(self, "_is_syncing", False) or self._current_row < 0 or not self.model or not self.tm:
            return
        seg = self.model.segment_at(self._current_row)
        if not seg:
            return
        new_txt = self.tgt_edit.toPlainText()
        if new_txt != display_text(seg.target):
            self._is_syncing = True
            seg.target = new_txt
            idx = self.model.index(self._current_row, 1)
            self.model.dataChanged.emit(idx, idx, [Qt.DisplayRole])
            self._is_syncing = False

    def _lookup_matches(self, seg) -> None:
        """Busca correspondências nas memórias de tradução associadas (.sdltm, .tmx) e na TM local."""
        if not self.tm:
            return
        clean_src = display_text(seg.source).strip()
        if not clean_src:
            self.fuzzy_edit.setPlainText("Segmento fonte vazio.")
            return

        result_lines = []

        # 1. Busca em todas as memórias associadas via AttachedTMManager
        if self.attached_tms:
            matches = AttachedTMManager.query_matches(clean_src, self.attached_tms, min_match=70, limit=5)
            for m in matches:
                result_lines.append(m.display_label)

        # 2. Correspondência exata da TM local
        exact = self.tm.exact_match(clean_src)
        if exact and exact.target:
            tgt_clean = display_text(exact.target).strip()
            if not any(tgt_clean in line for line in result_lines):
                result_lines.append(f"★ [100% TM Local] {tgt_clean}")

        # 3. Correspondência em .sdltm anexado legado (se houver)
        ref_match = self.tm.get_reference_match(clean_src)
        if ref_match and not any(ref_match in line for line in result_lines):
            result_lines.append(f"★ [100% SDLTM] {ref_match}")

        # 4. Concordância contextual se não houver match direto
        if not result_lines:
            concordance = self.tm.concordance(clean_src[:30], limit=3)
            for c in concordance:
                if c.row_id != seg.row_id and c.target:
                    result_lines.append(f"· [Concordância] {display_text(c.source)} ➔ {display_text(c.target)}")

        if result_lines:
            self.fuzzy_edit.setPlainText("\n".join(result_lines))
        else:
            if not self.attached_tms:
                self.fuzzy_edit.setPlainText(
                    "Nenhuma correspondência encontrada. Nenhuma memória (.sdltm/.tmx) associada.\n"
                    "Pressione Alt+F8 ou clique em '⚙ Associar TM' para anexar a sua memória de tradução."
                )
            else:
                self.fuzzy_edit.setPlainText("Nenhuma correspondência encontrada nas memórias associadas.")

        # Busca assíncrona da SLM Neural se não houver 100% match na TM
        has_100 = any("100%" in line for line in result_lines)
        if not has_100 and getattr(self, "_auto_slm_suggest", True) and self._slm_client.is_available():
            if self._slm_lookup_worker is not None and self._slm_lookup_worker.isRunning():
                self._slm_lookup_worker.quit()

            context_terms = []
            if self.attached_tms:
                for m in AttachedTMManager.query_matches(clean_src, self.attached_tms, min_match=70, limit=3):
                    context_terms.append((m.source, m.target))

            self._slm_lookup_worker = SLMSuggestionWorker(
                prompt=clean_src,
                model=self._active_slm_model,
                row_id=seg.row_id,
                context_terms=context_terms
            )
            self._slm_lookup_worker.ready.connect(self._on_slm_suggestion_ready)
            self._slm_lookup_worker.start()

    def _on_slm_suggestion_ready(self, translation: str, row_id: int) -> None:
        """Callback acionado quando a SLM devolve uma sugestão assíncrona para o segmento ativo."""
        if not self.model or self._current_row < 0:
            return
        seg = self.model.segment_at(self._current_row)
        if seg and seg.row_id == row_id:
            txt = self.fuzzy_edit.toPlainText().strip()
            slm_line = f"🤖 [SLM: {self._active_slm_model}] {translation}"
            if "Nenhuma correspondência" in txt or not txt:
                self.fuzzy_edit.setPlainText(slm_line)
            elif slm_line not in txt:
                self.fuzzy_edit.append(f"\n{slm_line}")

    def translate_current_with_slm(self) -> None:
        """Traduz o segmento ativo com a SLM Neural especializada (Ctrl+G)."""
        if not self.model or self._current_row < 0 or not self.tm:
            return

        seg = self.model.segment_at(self._current_row)
        if not seg:
            return

        clean_src = display_text(seg.source).strip()
        if not clean_src:
            return

        if not self._slm_client.is_available():
            QMessageBox.warning(
                self, "SLM Indisponível",
                "O servidor Ollama local (http://localhost:11434) não está em execução.\n"
                "Inicie o Ollama ou verifique a conexão no SLM Studio."
            )
            return

        context_terms = []
        if self.attached_tms:
            for m in AttachedTMManager.query_matches(clean_src, self.attached_tms, min_match=70, limit=3):
                context_terms.append((m.source, m.target))

        current_tgt = self.tgt_edit.toPlainText().strip()
        if not current_tgt:
            self.tgt_edit.setPlainText("🤖 A traduzir com SLM...")

        if self._slm_worker is not None and self._slm_worker.isRunning():
            self._slm_worker.quit()
            self._slm_worker.wait(300)

        self._slm_worker = SLMTranslateWorker(
            prompt=clean_src,
            model=self._active_slm_model,
            row_id=seg.row_id,
            row_index=self._current_row,
            context_terms=context_terms
        )
        self._slm_worker.finished.connect(self._on_slm_translate_finished)
        self._slm_worker.error.connect(self._on_slm_translate_error)
        self._slm_worker.start()

    def _on_slm_translate_finished(self, translation: str, row_id: int, row_index: int) -> None:
        if translation.startswith("[Erro"):
            QMessageBox.warning(self, "Aviso SLM", translation)
            return

        if self._current_row == row_index:
            self.tgt_edit.setPlainText(translation)
            self.tgt_edit.setFocus()

        if self.tm and row_id > 0:
            self.tm.update_target(row_id, translation, state=SegState.TRANSLATED, origin=SegOrigin.MT)
            if self.model:
                seg = self.model.segment_at(row_index)
                if seg:
                    seg.target = translation
                    seg.state = SegState.TRANSLATED
                    seg.origin = SegOrigin.MT
                    idx = self.model.index(row_index, 1)
                    self.model.dataChanged.emit(idx, idx, [Qt.DisplayRole])
            self._update_stats()

    def _on_slm_translate_error(self, err_msg: str) -> None:
        QMessageBox.warning(self, "Erro SLM", f"Falha na inferência SLM:\n{err_msg}")

    def show_slm_studio(self) -> None:
        """Abre o diálogo Studio de criação e treino de SLM."""
        from ui.slm_studio_dialog import SLMStudioDialog
        dialog = SLMStudioDialog(parent=self)
        dialog.model_changed.connect(self.set_active_slm_model)
        dialog.exec()

    def set_active_slm_model(self, model_name: str) -> None:
        """Define o modelo SLM ativo para tradução e sugestões."""
        self._active_slm_model = model_name
        if hasattr(self, "review_bar") and hasattr(self.review_bar, "btn_slm"):
            self.review_bar.btn_slm.setToolTip(f"Traduzir segmento com SLM ({model_name}) (Ctrl+G)")

    def _apply_best_match(self) -> None:
        """Aplica a primeira correspondência encontrada à tradução atual (Ctrl+T)."""
        txt = self.fuzzy_edit.toPlainText().strip()
        if not txt or "Nenhuma correspondência" in txt:
            return
        first_line = txt.splitlines()[0]
        if "]" in first_line:
            match_content = first_line.split("]", 1)[-1].strip()
            if "➔" in match_content:
                match_content = match_content.split("➔", 1)[-1].strip()
            self.tgt_edit.setPlainText(match_content)
            self.tgt_edit.setFocus()

    def show_concordance(self) -> None:
        """Dispara busca de concordância (F3) no texto selecionado nas TMs associadas e locais."""
        sel = self.src_edit.textCursor().selectedText() or self.tgt_edit.textCursor().selectedText()
        if not sel and self.model and self._current_row >= 0:
            seg = self.model.segment_at(self._current_row)
            sel = display_text(seg.source) if seg else ""
        if not sel:
            return

        lines = []
        # 1. Busca nas TMs associadas (.sdltm com Concordance=True)
        if self.attached_tms:
            tm_results = AttachedTMManager.concordance_search(sel, self.attached_tms, limit=10)
            for m in tm_results:
                lines.append(f"• [{m.tm_name}] {m.source} ➔ {m.target}")

        # 2. Busca na TM local
        if self.tm:
            local_results = self.tm.concordance(sel.strip(), limit=5)
            for r in local_results:
                if r.target:
                    cand = f"• [Local] {display_text(r.source)} ➔ {display_text(r.target)}"
                    if cand not in lines:
                        lines.append(cand)

        if lines:
            self.fuzzy_edit.setPlainText("\n".join(lines))
        else:
            self.fuzzy_edit.setPlainText(f"Sem resultados de concordância para: '{sel}'")

    def save_current(self) -> None:
        """Grava a alteração da linha atual e atualiza as TMs associadas (Update=True)."""
        if not self.model or self._current_row < 0 or not self.tm:
            return
        row = self._current_row
        seg = self.model.segment_at(row)
        if seg is None or seg.row_id < 0:
            return
        new_tgt = self.tgt_edit.toPlainText()
        self.tm.update_target(seg.row_id, new_tgt, state=seg.state)
        seg.target = new_tgt
        idx = self.model.index(row, 1)
        self.model.dataChanged.emit(idx, idx, [Qt.DisplayRole])
        self._update_stats()

        # Atualização em tempo real nas bases .sdltm associadas (Trados Studio behavior)
        if new_tgt.strip() and self.attached_tms:
            AttachedTMManager.update_tms(
                source_text=seg.source,
                target_text=new_tgt,
                tms=self.attached_tms,
                src_lang=self._src_lang,
                tgt_lang=self._tgt_lang
            )

    # ------------------------------------------------------------- Gestão de Memórias Associadas (Alt+F8)
    def show_project_settings(self) -> None:
        """Abre o diálogo oficial de Project Settings / Associação de Memórias (Alt+F8)."""
        from ui.project_settings_dialog import ProjectSettingsDialog
        proj_name = self._current_project.name if self._current_project else (os.path.basename(self.file_label.text()) if self.file_label.text() else "Ficheiro Ativo")
        dialog = ProjectSettingsDialog(
            current_tms=self.attached_tms,
            src_lang=self._src_lang,
            tgt_lang=self._tgt_lang,
            project_name=proj_name,
            parent=self
        )
        dialog.tms_updated.connect(self._on_tms_updated)
        dialog.exec()

    def _on_tms_updated(self, new_tms: list[AttachedTMConfig]) -> None:
        """Callback acionado ao salvar alterações de memórias no Project Settings."""
        self.attached_tms = new_tms
        if self._current_project:
            self._current_project.tm_paths = [tm.path for tm in new_tms if tm.enabled]
        self._update_tm_badge()
        if self.model and self._current_row >= 0:
            seg = self.model.segment_at(self._current_row)
            if seg:
                self._lookup_matches(seg)

    def attach_tm(self, path: str, lookup: bool = True, concordance: bool = True,
                  update: bool = True, penalty: int = 0) -> None:
        """Associa programaticamente uma memória (.sdltm / .tmx) ao editor."""
        for tm in self.attached_tms:
            if os.path.abspath(tm.path) == os.path.abspath(path):
                tm.enabled = True
                tm.lookup = lookup
                tm.concordance = concordance
                tm.update = update
                tm.penalty = penalty
                self._update_tm_badge()
                if self.model and self._current_row >= 0:
                    seg = self.model.segment_at(self._current_row)
                    if seg:
                        self._lookup_matches(seg)
                return

        new_tm = AttachedTMConfig(path=path, lookup=lookup, concordance=concordance, update=update, penalty=penalty)
        self.attached_tms.append(new_tm)
        if self._current_project and path not in self._current_project.tm_paths:
            self._current_project.tm_paths.append(path)
        self._update_tm_badge()
        if self.model and self._current_row >= 0:
            seg = self.model.segment_at(self._current_row)
            if seg:
                self._lookup_matches(seg)

    def _update_tm_badge(self) -> None:
        """Atualiza o badge visual na UI indicando o estado das TMs associadas."""
        if not hasattr(self, "lbl_attached_tm"):
            return
        active_tms = [tm for tm in self.attached_tms if tm.enabled]
        if not active_tms:
            self.lbl_attached_tm.setText("[Nenhuma TM associada - Clique em Associar TM (Alt+F8)]")
            self.lbl_attached_tm.setStyleSheet("color: #e67e22; font-size: 10px; background-color: #2b2210; border: 1px solid #7d4806; border-radius: 3px; padding: 1px 6px;")
        elif len(active_tms) == 1:
            tm = active_tms[0]
            upd_str = " (Update)" if tm.update else ""
            self.lbl_attached_tm.setText(f"[TM Ativa: {tm.name}{upd_str}]")
            self.lbl_attached_tm.setStyleSheet("color: #2ecc71; font-size: 10px; background-color: #122b1c; border: 1px solid #1e7e40; border-radius: 3px; padding: 1px 6px;")
        else:
            self.lbl_attached_tm.setText(f"[{len(active_tms)} TMs Associadas]")
            self.lbl_attached_tm.setStyleSheet("color: #2ecc71; font-size: 10px; background-color: #122b1c; border: 1px solid #1e7e40; border-radius: 3px; padding: 1px 6px;")

    def _update_stats(self) -> None:
        """Atualiza a contagem dos badges da ReviewBar e barra de progresso."""
        if not self.tm:
            self._stats_label.setText("Nenhum ficheiro carregado")
            self._progress_bar.setValue(0)
            return

        total = self.tm.count()
        translated = self.tm.count_translated()
        state_counts = self.tm.count_by_state()
        self.review_bar.update_counts(state_counts)

        total_words = self.tm.total_words()
        trans_words = self.tm.translated_words()
        percentage = (trans_words / total_words * 100.0) if total_words > 0 else ((translated / total * 100.0) if total > 0 else 0.0)
        percentage = max(0.0, min(100.0, percentage))

        self._stats_label.setText(
            f"Palavras: {total_words:,} ({trans_words:,} traduzidas, {percentage:.1f}%)  |  "
            f"Segmentos: {total:,} ({translated:,} traduzidos)  |  "
            f"Idioma: {self._src_lang} ➔ {self._tgt_lang}"
        )
        self._progress_bar.setValue(int(round(percentage)))
        matched = self.model.rowCount() if self.model else total
        self.adv_filter.update_match_count(matched, total)

        # Sincroniza dados com o ficheiro de projeto ativo, se aplicável
        if getattr(self, "_current_project", None) and getattr(self, "_active_loading_path", None):
            try:
                cur_abs = os.path.abspath(self._active_loading_path)
                for pf in self._current_project.files:
                    if os.path.abspath(pf.path) == cur_abs:
                        pf.segment_count = total
                        pf.translated_count = state_counts.get("translated", 0)
                        pf.approved_count = state_counts.get("approved", 0)
                        pf.draft_count = state_counts.get("draft", 0)
                        pf.rejected_count = state_counts.get("rejected", 0)
                        pf.untranslated_count = state_counts.get("untranslated", 0)
                        if total_words > 0:
                            pf.words = total_words
                            pf.translated_words = trans_words
                            pf.approved_words = int(round((pf.approved_count / total) * total_words)) if total > 0 else 0
                            pf.draft_words = int(round((pf.draft_count / total) * total_words)) if total > 0 else 0
                            pf.rejected_words = int(round((pf.rejected_count / total) * total_words)) if total > 0 else 0
                            pf.untranslated_words = max(0, total_words - (pf.translated_words + pf.approved_words + pf.draft_words + pf.rejected_words))
                        pf.status = "Translated" if pf.progress >= 100.0 else ("In Translation" if pf.progress > 0 else "New")
                        break
            except Exception:
                pass

    def _check_spelling(self) -> None:
        """Verifica a ortografia da tradução (F7)."""
        if not self._spell_checker.available:
            QMessageBox.information(self, "Ortografia", "Verificador nativo do Windows indisponível.")
            return
        text = self.tgt_edit.toPlainText()
        errors = self._spell_checker.check(text)
        if errors:
            error_list = "\n".join(f"  - {word}" for word in errors)
            QMessageBox.warning(self, "Erros Ortográficos", f"Possíveis erros detectados:\n{error_list}")
        else:
            QMessageBox.information(self, "Ortografia", "Nenhum erro ortográfico detectado.")

    def show_xbench_qa(self) -> None:
        """Abre o diálogo de verificação de QA estilo ApSIC Xbench."""
        if not self.tm or self.tm.count() == 0:
            QMessageBox.information(self, "ApSIC Xbench QA", "Nenhum segmento carregado para verificar.")
            return

        from ui.xbench_dialog import XbenchQADialog
        total = self.tm.count()
        segments = self.tm.page(0, total)
        dialog = XbenchQADialog(segments, parent=self)
        dialog.jump_to_segment_requested.connect(self._select_row)
        dialog.exec()

    def _prev_file(self) -> None:
        if not self._current_project or self._current_file_index <= 0:
            return
        self._current_file_index -= 1
        self._update_nav_buttons()
        self.load_file(self._current_project.files[self._current_file_index].path)

    def _next_file(self) -> None:
        if not self._current_project or self._current_file_index >= len(self._current_project.files) - 1:
            return
        self._current_file_index += 1
        self._update_nav_buttons()
        self.load_file(self._current_project.files[self._current_file_index].path)

    def _update_nav_buttons(self) -> None:
        if not self._current_project:
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            return
        self.btn_prev.setEnabled(self._current_file_index > 0)
        self.btn_next.setEnabled(self._current_file_index < len(self._current_project.files) - 1)

    def export(self, kind: str) -> None:
        """Exporta o ficheiro atual para TMX, SDLXLIFF ou SDLTM."""
        if not self.tm:
            QMessageBox.warning(self, "Exportar", "Nenhum ficheiro carregado.")
            return

        from PySide6.QtWidgets import QFileDialog

        if kind == "tmx":
            path, _ = QFileDialog.getSaveFileName(self, "Exportar TMX", "", "TMX (*.tmx)")
            if path:
                n = write_tmx(self.tm, path, self._src_lang, self._tgt_lang)
                QMessageBox.information(self, "Exportar", f"{n} segmentos exportados para:\n{path}")
        elif kind == "sdltm":
            path, _ = QFileDialog.getSaveFileName(self, "Exportar SDLTM", "", "SDL TM (*.sdltm)")
            if path:
                n = write_sdltm(self.tm, path, self._src_lang, self._tgt_lang)
                QMessageBox.information(self, "Exportar", f"{n} segmentos exportados para:\n{path}")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Exportar SDLXLIFF", "", "SDLXLIFF (*.sdlxliff)")
            if path:
                n = write_sdlxliff(self.tm, path, self._src_lang, self._tgt_lang, original=os.path.basename(path))
                QMessageBox.information(self, "Exportar", f"{n} unidades exportadas para:\n{path}")

    def closeEvent(self, event) -> None:
        if self.loader is not None and self.loader.isRunning():
            self.loader.requestInterruption()
            self.loader.quit()
            self.loader.wait(2000)
        if hasattr(self, "_slm_worker") and self._slm_worker is not None and self._slm_worker.isRunning():
            self._slm_worker.quit()
            self._slm_worker.wait(1000)
        if hasattr(self, "_slm_lookup_worker") and self._slm_lookup_worker is not None and self._slm_lookup_worker.isRunning():
            self._slm_lookup_worker.quit()
            self._slm_lookup_worker.wait(500)
        super().closeEvent(event)
