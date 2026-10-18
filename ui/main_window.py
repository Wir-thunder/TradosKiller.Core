"""
ui.main_window - editor bilingue moderno com dark mode e dashboard.

Abre TMX/SDLXLIFF/XLIFF, carrega para a TM SQLite e mostra numa tabela
virtualizada. Anti-crash: a tabela nunca tem todos os segmentos em RAM.
Nova versão com UI moderna, estatísticas, visualização de fuzzy matches.
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Optional

from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox,
    QPlainTextEdit, QSplitter, QTableView, QVBoxLayout, QWidget,
    QProgressBar, QFrame, QStatusBar, QToolBar, QDockWidget,
    QTextEdit, QHBoxLayout, QPushButton, QDialog,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tm import TranslationMemory          # noqa: E402
from core.segment import display_text, SegState  # noqa: E402
from ui.segments_model import SegmentsModel    # noqa: E402
from io_layer.tmx import iter_tmx, detect_tmx_langs                  # noqa: E402
from io_layer.sdlxliff import iter_sdlxliff, detect_sdlxliff_langs   # noqa: E402
from io_layer.sdlproj import parse_sdlproj, is_sdlproj_file           # noqa: E402
from core.spellcheck import WindowsSpellChecker  # noqa: E402
from core.project import Project, is_project_file  # noqa: E402
from core.config import load_config, save_config  # noqa: E402


class FileLoaderThread(QThread):
    """Background thread for loading large files without freezing UI."""
    finished = Signal(object, str, str, int)  # tm, src_lang, tgt_lang, count
    error = Signal(str)
    progress = Signal(int, int)  # current, total (optional)
    
    def __init__(self, path: str, ext: str) -> None:
        super().__init__()
        self.path = path
        self.ext = ext
        self.tm = None
    
    def run(self) -> None:
        import uuid
        import os
        from core.tm import TranslationMemory
        
        try:
            db = f"{os.path.splitext(self.path)[0]}.tm-{uuid.uuid4().hex[:10]}.db"
            tm = TranslationMemory(db)
            
            if self.ext == ".tmx":
                src, tgt = detect_tmx_langs(self.path)
                n = tm.add_many(iter_tmx(self.path, src, tgt), src or "", tgt or "")
            else:
                src, tgt = detect_sdlxliff_langs(self.path)
                n = tm.add_many(iter_sdlxliff(self.path), src or "", tgt or "")
            
            tm.rebuild_fts()
            self.tm = tm
            self.finished.emit(tm, src or "en-US", tgt or "pt-BR", n)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CAT Tool — Translation Memory Editor")
        self.resize(1400, 900)
        self.tm: TranslationMemory | None = None
        self.model: SegmentsModel | None = None
        self._current_row = -1
        self._src_lang = "en-US"
        self._tgt_lang = "pt-BR"
        self._recent_files: list[str] = []
        self._stats_frame: Optional[QFrame] = None
        self._spell_checker = WindowsSpellChecker("pt-PT")
        self._current_project: Optional[Project] = None
        self._config = load_config()

        self._apply_dark_theme()
        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self.statusBar().showMessage("Ready. Open a TMX or SDLXLIFF file.")

    # --------------------------------------------------------------- tema dark
    def _apply_dark_theme(self) -> None:
        """Aplica um tema dark moderno e profissional."""
        app = QApplication.instance()
        palette = QPalette()
        
        # Cores do tema dark
        dark_bg = QColor(30, 30, 30)
        darker_bg = QColor(25, 25, 25)
        text_color = QColor(220, 220, 220)
        accent_color = QColor(61, 174, 233)
        accent_hover = QColor(73, 186, 245)
        disabled_color = QColor(100, 100, 100)
        
        palette.setColor(QPalette.Window, dark_bg)
        palette.setColor(QPalette.WindowText, text_color)
        palette.setColor(QPalette.Base, darker_bg)
        palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
        palette.setColor(QPalette.ToolTipBase, text_color)
        palette.setColor(QPalette.ToolTipText, text_color)
        palette.setColor(QPalette.Text, text_color)
        palette.setColor(QPalette.Button, dark_bg)
        palette.setColor(QPalette.ButtonText, text_color)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, accent_color)
        palette.setColor(QPalette.Highlight, accent_color)
        palette.setColor(QPalette.HighlightedText, Qt.white)
        palette.setColor(QPalette.Disabled, QPalette.Text, disabled_color)
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_color)
        
        app.setPalette(palette)
        
        # Fonte padrão
        font = QFont("Segoe UI", 9)
        app.setFont(font)

    # -------------------------------------------------------------- construcao
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Dashboard de estatísticas (topo)
        stats_frame = QFrame()
        stats_frame.setFrameStyle(QFrame.StyledPanel)
        stats_frame.setMaximumHeight(100)
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(12, 8, 12, 8)
        
        stats_header = QLabel("Statistics")
        stats_header.setStyleSheet("font-weight: bold; font-size: 11px; color: #8eb4f3;")
        stats_layout.addWidget(stats_header)
        
        stats_detail = QLabel("No file loaded")
        stats_detail.setStyleSheet("color: #aaa; font-size: 10px;")
        self._stats_label = stats_detail
        stats_layout.addWidget(stats_detail)
        
        # Barra de progresso
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background-color: #2a2a2a;
            }
            QProgressBar::chunk {
                background-color: #3dae73;
                border-radius: 3px;
            }
        """)
        stats_layout.addWidget(self._progress_bar)
        
        layout.addWidget(stats_frame)

        splitter = QSplitter(Qt.Vertical)

        # painel de cima: tabela virtualizada
        self.table = QTableView()
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(24)
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
        splitter.addWidget(self.table)

        # painel de baixo: editor do segmento selecionado (fonte | destino)
        edit_wrap = QWidget()
        ev = QVBoxLayout(edit_wrap)
        ev.setContentsMargins(0, 8, 0, 0)
        
        src_label = QLabel("Source (read-only):")
        src_label.setStyleSheet("color: #8eb4f3; font-weight: bold;")
        ev.addWidget(src_label)
        
        self.src_edit = QPlainTextEdit()
        self.src_edit.setReadOnly(True)
        self.src_edit.setMaximumHeight(100)
        self.src_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #aaa;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        ev.addWidget(self.src_edit)
        
        tgt_label = QLabel("Translation (editable):")
        tgt_label.setStyleSheet("color: #3dae73; font-weight: bold;")
        ev.addWidget(tgt_label)
        
        tgt_layout = QHBoxLayout()
        self.tgt_edit = QPlainTextEdit()
        self.tgt_edit.setMaximumHeight(100)
        self.tgt_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #3dae73;
                border-radius: 4px;
                padding: 6px;
            }
            QPlainTextEdit:focus {
                border: 2px solid #3dae73;
            }
        """)
        tgt_layout.addWidget(self.tgt_edit)
        
        # Spell check button
        self.btn_spell = QPushButton("Check")
        self.btn_spell.setMaximumWidth(60)
        self.btn_spell.setStyleSheet("""
            QPushButton {
                background-color: #8eb4f3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #9ec4ff;
            }
        """)
        self.btn_spell.clicked.connect(self._check_spelling)
        self.btn_spell.setEnabled(self._spell_checker.available)
        tgt_layout.addWidget(self.btn_spell)
        
        ev.addLayout(tgt_layout)
        
        # Fuzzy matches panel
        fuzzy_label = QLabel("Fuzzy Matches / Concordance:")
        fuzzy_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        ev.addWidget(fuzzy_label)
        
        self.fuzzy_edit = QTextEdit()
        self.fuzzy_edit.setReadOnly(True)
        self.fuzzy_edit.setMaximumHeight(80)
        self.fuzzy_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #aaa;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
                font-size: 9px;
            }
        """)
        ev.addWidget(self.fuzzy_edit)
        
        splitter.addWidget(edit_wrap)
        splitter.setSizes([550, 300])

        layout.addWidget(splitter)
        # NOTA: o selectionModel so existe apos definir um modelo; a ligacao
        # do sinal e feita em _load(), quando o modelo e colocado na tabela.
        
        # Guardar referência para o stats_frame
        self._stats_frame = stats_frame

    def _build_menu(self) -> None:
        mb = self.menuBar()
        mb.setStyleSheet("""
            QMenuBar {
                background-color: #2d2d2d;
                color: #ddd;
                border-bottom: 1px solid #444;
            }
            QMenuBar::item {
                padding: 6px 12px;
                background-color: transparent;
            }
            QMenuBar::item:selected {
                background-color: #3dae73;
            }
            QMenu {
                background-color: #2d2d2d;
                color: #ddd;
                border: 1px solid #444;
            }
            QMenu::item {
                padding: 6px 24px;
            }
            QMenu::item:selected {
                background-color: #3dae73;
            }
        """)
        
        m_file = mb.addMenu("&File")
        act_open = QAction("&Open TMX/SDLXLIFF/XLIFF…", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_file)
        m_file.addAction(act_open)
        
        act_open_sdl = QAction("Open SDL &Project…", self)
        act_open_sdl.setShortcut("Ctrl+Shift+S")
        act_open_sdl.triggered.connect(lambda: self.open_sdlproj_dialog())
        m_file.addAction(act_open_sdl)
        
        act_open_proj = QAction("Open CAT &Project…", self)
        act_open_proj.setShortcut("Ctrl+Shift+O")
        act_open_proj.triggered.connect(self.open_project)
        m_file.addAction(act_open_proj)
        
        act_new_proj = QAction("New CAT &Project…", self)
        act_new_proj.setShortcut("Ctrl+Shift+N")
        act_new_proj.triggered.connect(self.new_project)
        m_file.addAction(act_new_proj)
        
        m_file.addSeparator()
        
        # Recent files
        self._recent_menu = m_file.addMenu("Recent Files")
        self._update_recent_menu()
        
        m_file.addSeparator()

        act_save = QAction("&Save Segment", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self.save_current)
        m_file.addAction(act_save)

        act_tmed = QAction("Memory &Editor…", self)
        act_tmed.setShortcut("Ctrl+M")
        act_tmed.triggered.connect(self.open_tm_editor)
        m_file.addAction(act_tmed)

        m_exp = m_file.addMenu("&Export")
        act_tmx = QAction("Export &TMX…", self)
        act_tmx.triggered.connect(lambda: self.export("tmx"))
        m_exp.addAction(act_tmx)
        act_sdl = QAction("Export &SDLXLIFF…", self)
        act_sdl.triggered.connect(lambda: self.export("sdlxliff"))
        m_exp.addAction(act_sdl)

        m_file.addSeparator()
        act_quit = QAction("&Exit", self)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)
        
        m_view = mb.addMenu("&View")
        act_stats = QAction("Statistics Dashboard", self)
        act_stats.setCheckable(True)
        act_stats.setChecked(True)
        act_stats.triggered.connect(lambda: self._stats_frame.setVisible(act_stats.isChecked()) if self._stats_frame else None)
        m_view.addAction(act_stats)

    def _update_recent_menu(self) -> None:
        """Update the recent files menu."""
        self._recent_menu.clear()
        
        if not self._config.recent_files:
            act = QAction("No recent files", self)
            act.setEnabled(False)
            self._recent_menu.addAction(act)
            return
        
        for path in self._config.recent_files:
            act = QAction(os.path.basename(path), self)
            act.setData(path)
            act.triggered.connect(lambda checked, p=path: self._open_recent(p))
            self._recent_menu.addAction(act)
        
        self._recent_menu.addSeparator()
        act_clear = QAction("Clear Recent", self)
        act_clear.triggered.connect(self._clear_recent)
        self._recent_menu.addAction(act_clear)
    
    def _open_recent(self, path: str) -> None:
        """Open a recent file."""
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found", f"File not found:\n{path}")
            self._config.recent_files.remove(path)
            save_config(self._config)
            self._update_recent_menu()
            return
        
        if is_sdlproj_file(path):
            self.open_sdlproj(path)
        elif is_project_file(path):
            self.open_project_path(path)
        else:
            try:
                self._load(path)
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, "Error", f"Failed to open:\n{e}")
    
    def _clear_recent(self) -> None:
        """Clear recent files list."""
        self._config.clear_recent_files()
        save_config(self._config)
        self._update_recent_menu()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #2d2d2d;
                border: none;
                spacing: 4px;
                padding: 4px;
            }
            QToolBar QToolButton {
                background-color: #3d3d3d;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                color: #ddd;
            }
            QToolBar QToolButton:hover {
                background-color: #4d4d4d;
            }
            QToolBar QToolButton:pressed {
                background-color: #3dae73;
            }
        """)
        
        act_open = QAction("Open", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_file)
        toolbar.addAction(act_open)
        
        act_save = QAction("Save", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self.save_current)
        toolbar.addAction(act_save)
        
        toolbar.addSeparator()
        
        act_tm = QAction("Memory Editor", self)
        act_tm.setShortcut("Ctrl+M")
        act_tm.triggered.connect(self.open_tm_editor)
        toolbar.addAction(act_tm)
        
        self.addToolBar(toolbar)

    # ------------------------------------------------------------- gravar/exportar
    def save_current(self) -> None:
        """Grava a traducao da linha selecionada no SQLite."""
        if not self.model or self._current_row < 0:
            return
        row = self._current_row
        seg = self.model.segment_at(row)
        if seg is None or seg.row_id < 0:
            return
        new_tgt = self.tgt_edit.toPlainText()
        from core.segment import SegState
        self.tm.update_target(seg.row_id, new_tgt, state=SegState.TRANSLATED)
        saved = self.tm.get_row(seg.row_id)
        seg.target = saved.target if saved else new_tgt
        seg.state = SegState.TRANSLATED
        idx = self.model.index(row, 1)
        self.model.dataChanged.emit(idx, idx, [Qt.DisplayRole])
        self.statusBar().showMessage(f"Saved: segment {row + 1}")
        self._update_stats()

    def _update_stats(self) -> None:
        """Atualiza o dashboard de estatísticas."""
        if not self.tm:
            self._stats_label.setText("No file loaded")
            self._progress_bar.setValue(0)
            return
        
        total = self.tm.count()
        translated = self.tm.count_translated()
        percentage = (translated / total * 100) if total > 0 else 0
        
        self._stats_label.setText(
            f"Total: {total:,} segments  |  Translated: {translated:,} ({percentage:.1f}%)  |  "
            f"Source: {self._src_lang}  |  Target: {self._tgt_lang}"
        )
        self._progress_bar.setValue(int(percentage))

    # ------------------------------------------------------------- interaccao
    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Translation File", "",
            "CAT Files (*.tmx *.sdlxliff *.xlf *.xliff *.catproj *.sdlproj);;All Files (*.*)"
        )
        if not path:
            return
        
        # Check if it's a project file
        if is_project_file(path):
            self.open_project_path(path)
            return
        
        # Check if it's an SDL project file
        if is_sdlproj_file(path):
            self.open_sdlproj(path)
            return
        
        try:
            self._load(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to open:\n{e}")
    
    def open_sdlproj_dialog(self) -> None:
        """Open SDL project file dialog."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open SDL Project", "",
            "SDL Project (*.sdlproj);;All Files (*.*)"
        )
        if path:
            self.open_sdlproj(path)
    
    def open_project(self) -> None:
        """Open a project file dialog."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "",
            "CAT Project (*.catproj);;SDL Project (*.sdlproj);;All Files (*.*)"
        )
        if path:
            if is_sdlproj_file(path):
                self.open_sdlproj(path)
            else:
                self.open_project_path(path)
    
    def open_sdlproj(self, path: str) -> None:
        """Open an SDL Trados project file."""
        try:
            project = parse_sdlproj(path)
            if project is None:
                QMessageBox.warning(
                    self, "SDL Project",
                    "Could not parse SDL project or no translation files found."
                )
                return
            
            self._current_project = project
            
            # Open first file in the project
            if project.files:
                first_file = project.files[0]
                self._load(first_file.path)
                self.statusBar().showMessage(
                    f"SDL Project: {project.name} — "
                    f"{len(project.files)} file(s) — "
                    f"{project.source_lang} → {project.target_lang}"
                )
            else:
                QMessageBox.information(
                    self, "SDL Project",
                    "SDL project loaded but no translation files found.\n"
                    "The project file may need to be prepared or exported first."
                )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to open SDL project:\n{e}")
    
    def open_project_path(self, path: str) -> None:
        """Open a project from a file path."""
        try:
            from core.project import Project
            self._current_project = Project.load(path)
            # For now, just open the first file in the project
            if self._current_project.files:
                first_file = self._current_project.files[0]
                self._load(first_file.path)
                self.statusBar().showMessage(
                    f"Project: {self._current_project.name} — "
                    f"{len(self._current_project.files)} file(s)"
                )
            else:
                QMessageBox.information(self, "Project", "Project has no files.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")
    
    def new_project(self) -> None:
        """Create a new project."""
        from ui.project_manager import ProjectManagerDialog
        
        dlg = ProjectManagerDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            proj = dlg.get_project()
            if proj and proj.files:
                self._current_project = proj
                # Open first file
                self._load(proj.files[0].path)
                self.statusBar().showMessage(
                    f"New project: {proj.name} — {len(proj.files)} file(s)"
                )

    def _load(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".tmx", ".sdlxliff", ".xlf", ".xliff"):
            QMessageBox.warning(self, "Format", f"Unsupported extension: {ext}")
            return
        self.save_current()
        
        # Close existing TM
        if self.tm:
            self.tm.close()
            self.tm = None
        
        self._current_loading_path = path
        self.statusBar().showMessage(f"Loading {os.path.basename(path)}... (background)")
        self._progress_bar.setRange(0, 0)  # Indeterminate progress
        
        # Start background thread
        if hasattr(self, "_loader_thread") and self._loader_thread is not None and self._loader_thread.isRunning():
            self._loader_thread.requestInterruption()
            self._loader_thread.quit()
            self._loader_thread.wait(2000)

        self._loader_thread = FileLoaderThread(path, ext)
        self._loader_thread.finished.connect(self._on_load_finished)
        self._loader_thread.error.connect(self._on_load_error)
        self._loader_thread.start()
    
    def _on_load_finished(self, tm, src_lang, tgt_lang, count) -> None:
        """Called when file loading completes in background."""
        self._src_lang = src_lang
        self._tgt_lang = tgt_lang
        self.tm = tm
        self.model = SegmentsModel(tm)
        self.table.setModel(self.model)
        self.table.selectionModel().selectionChanged.connect(self._on_select)
        for i, w in enumerate((50, 480, 480, 100, 60)):
            self.table.setColumnWidth(i, w)
        
        self._progress_bar.setRange(0, 100)
        self._update_stats()
        self.statusBar().showMessage(f"Loaded {count:,} segments")
        
        # Add to recent files
        if hasattr(self, '_current_loading_path'):
            self._config.add_recent_file(self._current_loading_path)
            save_config(self._config)
            self._update_recent_menu()
    
    def _on_load_error(self, error_msg: str) -> None:
        """Called when file loading fails."""
        self._progress_bar.setRange(0, 100)
        QMessageBox.critical(self, "Error", f"Failed to load file:\n{error_msg}")
        self.statusBar().showMessage("Load failed")

    def _on_select(self, selected, _deselected) -> None:
        if not self.model or not selected.indexes():
            return
        row = selected.indexes()[0].row()
        # auto-save: se havia uma linha em edicao e o texto mudou, grava
        self.save_current()
        seg = self.model.segment_at(row)
        if seg:
            self.src_edit.setPlainText(display_text(seg.source))
            self.tgt_edit.setPlainText(display_text(seg.target))
            self._current_row = row
            # Show fuzzy matches
            self._show_fuzzy_matches(seg.source)

    def _check_spelling(self) -> None:
        """Check spelling of current translation and highlight errors."""
        if not self._spell_checker.available:
            QMessageBox.information(self, "Spell Check", "Spell checker not available on this system.")
            return
        
        text = self.tgt_edit.toPlainText()
        if not text:
            return
        
        errors = self._spell_checker.check(text)
        
        if not errors:
            self.statusBar().showMessage("No spelling errors found.")
            return
        
        # Show errors in fuzzy panel temporarily
        error_msg = f"Found {len(errors)} spelling error(s):\n\n"
        for start, length, word in errors[:10]:  # Show first 10
            error_msg += f"• {word} (position {start})\n"
            suggestions = self._spell_checker.suggest(word, limit=3)
            if suggestions:
                error_msg += f"  Suggestions: {', '.join(suggestions)}\n"
        
        if len(errors) > 10:
            error_msg += f"\n... and {len(errors) - 10} more"
        
        self.fuzzy_edit.setPlainText(error_msg)
        self.statusBar().showMessage(f"Found {len(errors)} spelling errors")

    def _show_fuzzy_matches(self, source_text: str) -> None:
        """Shows fuzzy matches from TM for the current source segment."""
        if not self.tm or not source_text:
            self.fuzzy_edit.setPlainText("No matches available.")
            return
        
        # Get concordance results (first 10 words as query)
        words = source_text.split()[:5]
        query = " ".join(words)
        
        matches = self.tm.concordance(query, limit=5)
        
        if not matches:
            self.fuzzy_edit.setPlainText("No similar segments found.")
            return
        
        result_lines = []
        for i, match in enumerate(matches, 1):
            pct = match.percent
            if pct == 0:
                # Calculate simple similarity
                from difflib import SequenceMatcher
                similarity = SequenceMatcher(None, source_text.lower(), match.source.lower()).ratio()
                pct = int(similarity * 100)
            
            result_lines.append(f"{i}. [{pct}%] {display_text(match.source)}")
            if match.target:
                result_lines.append(f"   → {display_text(match.target)}")
            result_lines.append("")
        
        self.fuzzy_edit.setPlainText("\n".join(result_lines))

    def export(self, kind: str) -> None:
        if not self.tm:
            QMessageBox.information(self, "Export", "Open a file first.")
            return
        src, tgt = self.tm.langs()
        if not src:
            src = self._src_lang or "en-US"
        if not tgt:
            tgt = self._tgt_lang or "pt-BR"
        if kind == "tmx":
            path, _ = QFileDialog.getSaveFileName(
                self, "Export TMX", "", "TMX (*.tmx)")
            if not path:
                return
            from io_layer.tmx_writer import write_tmx
            n = write_tmx(self.tm, path, src, tgt)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export SDLXLIFF", "", "SDLXLIFF (*.sdlxliff)")
            if not path:
                return
            from io_layer.sdlxliff_writer import write_sdlxliff
            n = write_sdlxliff(self.tm, path, src, tgt,
                               original=os.path.basename(path))
        self.statusBar().showMessage(f"Exported: {n:,} units -> {os.path.basename(path)}")
        QMessageBox.information(self, "Export", f"Exported successfully:\n{path}\n({n:,} units)")

    def open_tm_editor(self) -> None:
        """Abre a janela do Editor de Memoria sobre a TM actual."""
        if not self.tm:
            QMessageBox.information(self, "Memory Editor",
                                    "Open a file first (TMX/SDLXLIFF).")
            return
        from ui.tm_editor import TmEditorWindow
        self._tm_editor = TmEditorWindow(
            self.tm, self._src_lang, self._tgt_lang, parent=None)
        self._tm_editor.show()
        # Update stats when editor closes
        self._tm_editor.destroyed.connect(self._update_stats)

    def closeEvent(self, event) -> None:
        self.save_current()
        if hasattr(self, "_loader_thread") and self._loader_thread is not None and self._loader_thread.isRunning():
            self._loader_thread.requestInterruption()
            self._loader_thread.quit()
            self._loader_thread.wait(2000)
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
