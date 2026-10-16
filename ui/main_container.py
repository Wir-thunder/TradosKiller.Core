"""
ui.main_container - Janela Principal da CAT Tool com Ribbon Bar e Sidebar estilo SDL Trados Studio.

Layout Profissional RWS Trados:
- Ribbon Bar no topo com abas: Início, Revisão, Memórias, Projeto & Ficheiros
- Sidebar lateral de navegação rápida: Welcome, Projects, Files, Reports, Editor, TMs
- Suporte nativo completo a ficheiros RWS (.sdlxliff, .sdltm, .sdlproj, .sdlppx, .sdlrpx) e TMX
- Barra de Localizar e Substituir (Ctrl+F / Ctrl+H) e Review Bar com badges de status
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QStackedWidget, QFileDialog, QMessageBox, QStatusBar
)

from ui.ribbon import RibbonBar
from ui.screens.welcome_screen import WelcomeScreen
from ui.screens.projects_screen import ProjectsScreen
from ui.screens.files_screen import FilesScreen
from ui.screens.editor_screen import EditorScreen
from ui.screens.tm_screen import TmScreen
from ui.quick_start_dialog import QuickStartDialog
from ui.xbench_dialog import XbenchQADialog
from ui.tm_utility_dialog import TmManagementUtilityDialog
from core.segment import SegState
from core.project import Project, is_project_file
from core.file_importer import convert_to_sdlxliff, is_supported_file
from io_layer.sdlproj import parse_sdlproj, is_sdlproj_file
from io_layer.sdlpackage import is_sdlpackage, extract_package, create_return_package


class NavigationButton(QPushButton):
    """Botão de navegação vertical na barra lateral."""
    
    def __init__(self, text: str, icon: str = "", parent=None) -> None:
        super().__init__(parent)
        self.text_label = text
        self.icon_label = icon
        self._is_active = False
        self._update_style()
    
    def set_active(self, active: bool) -> None:
        self._is_active = active
        self._update_style()
    
    def _update_style(self) -> None:
        if self._is_active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #007acc;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 12px;
                    text-align: left;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #1c97ea;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #cccccc;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 12px;
                    text-align: left;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #383838;
                    color: #ffffff;
                }
            """)
        self.setText(f"{self.icon_label}  {self.text_label}")


class MainContainer(QMainWindow):
    """Janela principal com Ribbon Bar estilo Trados e sidebar lateral."""
    
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CAT Tool — Professional RWS Trados Translation Workspace")
        self.resize(1440, 920)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)
        
        self._current_project: Optional[Project] = None
        
        self._apply_dark_theme()
        self._build_ui()
        self._connect_signals()

    def _apply_dark_theme(self) -> None:
        """Aplica tema escuro profissional estilo Trados Studio."""
        app = QApplication.instance()
        palette = QPalette()
        
        dark_bg = QColor(30, 30, 30)
        darker_bg = QColor(24, 24, 24)
        text_color = QColor(220, 220, 220)
        accent_color = QColor(0, 122, 204)
        
        palette.setColor(QPalette.Window, dark_bg)
        palette.setColor(QPalette.WindowText, text_color)
        palette.setColor(QPalette.Base, darker_bg)
        palette.setColor(QPalette.AlternateBase, QColor(36, 36, 36))
        palette.setColor(QPalette.Text, text_color)
        palette.setColor(QPalette.Button, dark_bg)
        palette.setColor(QPalette.ButtonText, text_color)
        palette.setColor(QPalette.Highlight, accent_color)
        palette.setColor(QPalette.HighlightedText, Qt.white)
        
        app.setPalette(palette)
        app.setFont(QFont("Segoe UI", 9))

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---------------- Ribbon Bar Superior
        self.ribbon = RibbonBar(self)
        root_layout.addWidget(self.ribbon)

        # ---------------- Área de Trabalho: Sidebar + Stack de Telas
        workspace = QWidget()
        workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        # Sidebar Lateral
        sidebar = QFrame()
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet("background-color: #252526; border-right: 1px solid #333333;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 8, 6, 8)
        sidebar_layout.setSpacing(3)

        title = QLabel("TRADOS WORKSPACE")
        title.setStyleSheet("font-size: 11px; font-weight: bold; color: #007acc; padding: 6px;")
        sidebar_layout.addWidget(title)

        self.btn_welcome = NavigationButton("Início", "🏠")
        self.btn_welcome.clicked.connect(lambda: self._navigate_to("welcome"))
        sidebar_layout.addWidget(self.btn_welcome)

        self.btn_projects = NavigationButton("Projetos", "📋")
        self.btn_projects.clicked.connect(lambda: self._navigate_to("projects"))
        sidebar_layout.addWidget(self.btn_projects)

        self.btn_files = NavigationButton("Ficheiros", "📁")
        self.btn_files.clicked.connect(lambda: self._navigate_to("files"))
        sidebar_layout.addWidget(self.btn_files)

        self.btn_editor = NavigationButton("Editor de Tradução", "✏")
        self.btn_editor.clicked.connect(lambda: self._navigate_to("editor"))
        sidebar_layout.addWidget(self.btn_editor)

        self.btn_tm = NavigationButton("Memórias de Tradução", "🗄")
        self.btn_tm.clicked.connect(lambda: self._navigate_to("tm"))
        sidebar_layout.addWidget(self.btn_tm)

        self.btn_reports = NavigationButton("Relatórios & Estatísticas", "📊")
        self.btn_reports.clicked.connect(lambda: self._navigate_to("reports"))
        sidebar_layout.addWidget(self.btn_reports)

        sidebar_layout.addStretch()
        workspace_layout.addWidget(sidebar)

        # Conteúdo Principal (Stack)
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #1e1e1e;")
        workspace_layout.addWidget(self.stack)

        self._create_screens()
        root_layout.addWidget(workspace)

        # Status Bar inferior
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("background-color: #007acc; color: white; font-size: 10px; font-weight: bold;")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("TradosKiller pronto — Arraste qualquer ficheiro para traduzir.")

        self._navigate_to("welcome")

    def _create_screens(self) -> None:
        """Cria as telas integradas da aplicação."""
        # 0. Welcome Screen (Drag & Drop Universal Hub)
        self.welcome_screen = WelcomeScreen()
        self.stack.addWidget(self.welcome_screen)

        # 1. Projects
        self.projects_screen = ProjectsScreen()
        self.stack.addWidget(self.projects_screen)

        # 2. Files (Trados Files View)
        self.files_screen = FilesScreen()
        self.stack.addWidget(self.files_screen)

        # 3. Reports
        reports = QWidget()
        rl = QVBoxLayout(reports)
        rl.setContentsMargins(30, 30, 30, 30)
        rl.addWidget(QLabel("Relatórios de Tradução e Análise"))
        rl.addStretch()
        self.stack.addWidget(reports)

        # 4. Editor de Tradução
        self.editor_screen = EditorScreen()
        self.stack.addWidget(self.editor_screen)

        # 5. Translation Memories
        self.tm_screen = TmScreen()
        self.stack.addWidget(self.tm_screen)

    def _connect_signals(self) -> None:
        """Conecta todos os sinais do Ribbon e das telas."""
        # Welcome Screen
        self.welcome_screen.file_selected.connect(self._handle_universal_file_import)
        self.welcome_screen.open_project_requested.connect(self.projects_screen._open_project_dialog)
        self.welcome_screen.open_tm_requested.connect(lambda: self._navigate_to("tm"))

        self.projects_screen.project_opened.connect(self._on_project_opened)
        self.projects_screen.file_opened.connect(self._open_specific_file)
        self.files_screen.open_file_in_editor.connect(self._open_specific_file)
        self.files_screen.batch_tasks_requested.connect(self._show_batch_tasks)

        # Conexões do Ribbon Bar
        r = self.ribbon
        r.new_project_requested.connect(self._on_new_project)
        r.open_project_requested.connect(self.projects_screen._open_project_dialog)
        r.open_file_requested.connect(self._open_file_dialog)
        r.save_file_requested.connect(self.editor_screen.save_current)
        r.xbench_qa_requested.connect(self._show_xbench_qa)
        r.verify_qa_requested.connect(self._show_xbench_qa)
        r.display_filter_changed.connect(self._on_display_filter_changed)
        r.display_filter_reset.connect(self._on_display_filter_reset)
        r.batch_tasks_requested.connect(self._show_batch_tasks)
        r.explore_folder_requested.connect(self._explore_containing_folder)
        r.project_settings_requested.connect(self._show_project_settings)
        r.tm_utility_requested.connect(self._show_tm_utility)
        r.advanced_filter_requested.connect(self._on_ribbon_adf)

        r.confirm_and_next_requested.connect(self._on_ribbon_confirm)
        r.copy_source_requested.connect(self.editor_screen.copy_source_to_target)
        r.clear_target_requested.connect(self.editor_screen.clear_target)
        r.prev_segment_requested.connect(self.editor_screen.prev_segment)
        r.next_segment_requested.connect(self.editor_screen.next_segment)
        r.next_untranslated_requested.connect(self.editor_screen.next_untranslated)
        r.merge_segment_requested.connect(self.editor_screen.merge_with_next_segment)
        r.split_segment_requested.connect(self.editor_screen.split_current_segment)
        r.heal_segmentation_requested.connect(self.editor_screen.auto_heal_segmentation)
        r.find_requested.connect(self._on_ribbon_find)
        r.replace_requested.connect(self._on_ribbon_replace)
        r.approve_requested.connect(lambda: self.editor_screen.set_current_status(SegState.APPROVED))
        r.reject_requested.connect(lambda: self.editor_screen.set_current_status(SegState.REJECTED))
        r.draft_requested.connect(lambda: self.editor_screen.set_current_status(SegState.DRAFT))
        r.spellcheck_requested.connect(self.editor_screen._check_spelling)
        r.concordance_requested.connect(self.editor_screen.show_concordance)
        r.tm_editor_requested.connect(lambda: self._navigate_to("tm"))
        r.open_sdlproj_requested.connect(self._open_sdlproj_dialog)
        r.open_sdlpackage_requested.connect(self._open_sdlpackage_dialog)
        r.export_return_package_requested.connect(self._export_return_package_dialog)
        r.export_sdltm_requested.connect(lambda: self.editor_screen.export("sdltm"))
        r.export_sdlxliff_requested.connect(lambda: self.editor_screen.export("sdlxliff"))
        r.export_tmx_requested.connect(lambda: self.editor_screen.export("tmx"))
        r.switch_view_requested.connect(self._navigate_to)
        r.slm_studio_requested.connect(self._show_slm_studio)
        r.slm_translate_requested.connect(self._on_slm_translate_requested)

    def _navigate_to(self, screen: str) -> None:
        """Altera a tela ativa, atualiza os botões da barra lateral e o Ribbon."""
        self.btn_welcome.set_active(screen == "welcome")
        self.btn_projects.set_active(screen == "projects")
        self.btn_files.set_active(screen == "files")
        self.btn_reports.set_active(screen == "reports")
        self.btn_editor.set_active(screen == "editor")
        self.btn_tm.set_active(screen == "tm")
        
        screen_map = {
            "welcome": 0,
            "projects": 1,
            "files": 2,
            "reports": 3,
            "editor": 4,
            "tm": 5,
        }
        idx = screen_map.get(screen, 0)
        self.stack.setCurrentIndex(idx)
        self.ribbon.set_view_context(screen)

    def _on_ribbon_confirm(self) -> None:
        if self.stack.currentIndex() != 4:
            self._navigate_to("editor")
        self.editor_screen.confirm_and_next()

    def _on_ribbon_find(self) -> None:
        if self.stack.currentIndex() != 4:
            self._navigate_to("editor")
        self.editor_screen.show_find()

    def _on_ribbon_replace(self) -> None:
        if self.stack.currentIndex() != 4:
            self._navigate_to("editor")
        self.editor_screen.show_replace()

    def _on_ribbon_adf(self) -> None:
        if self.stack.currentIndex() != 4:
            self._navigate_to("editor")
        self.editor_screen.toggle_advanced_filter()

    def _on_display_filter_changed(self, query: str, field: str, status: str, case_sensitive: bool) -> None:
        if self.stack.currentIndex() != 4:
            self._navigate_to("editor")
        self.editor_screen.apply_display_filter(query, field, status, case_sensitive)

    def _on_display_filter_reset(self) -> None:
        if self.stack.currentIndex() != 4:
            self._navigate_to("editor")
        self.editor_screen.reset_display_filter()

    # ------------------------------------------------------------- Gestão de Ficheiros, Documentos & Pacotes
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if is_supported_file(p):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if is_supported_file(p):
                event.acceptProposedAction()
                self._handle_universal_file_import(p)
                return

    def _open_file_dialog(self) -> None:
        filter_str = (
            "Todos os Formatos Suportados (*.docx *.xlsx *.pptx *.pdf *.png *.jpg *.jpeg *.tiff *.bmp *.txt *.html *.xml *.json *.csv *.sdlxliff *.tmx *.sdltm *.sdlproj *.sdlppx);;"
            "Documentos Office (*.docx *.xlsx *.pptx);;"
            "PDF e Imagens OCR (*.pdf *.png *.jpg *.jpeg *.tiff *.bmp);;"
            "Ficheiros RWS & CAT (*.sdlxliff *.sdltm *.sdlproj *.sdlppx *.sdlrpx *.tmx *.catproj *.xlf *.xliff);;"
            "Todos os Ficheiros (*.*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar Ficheiro para Traduzir", "", filter_str)
        if path:
            self._handle_universal_file_import(path)

    def _handle_universal_file_import(self, path: str) -> None:
        """
        Ponto de entrada universal para qualquer ficheiro arrastado ou selecionado.
        - Se for projeto/pacote (.sdlproj, .sdlppx, .catproj): abre o projeto
        - Se for memória (.sdltm, .tmx): abre para edição ou associa
        - Se for bilingue (.sdlxliff, .xlf, .xliff): abre diálogo de configuração rápida / associação de TM
        - Se for documento ou arquivo fonte (.docx, .xlsx, .pptx, .pdf, imagem OCR, .txt, etc.):
          Converte para .sdlxliff, abre diálogo de associação de TM e inicia tradução no Editor!
        """
        if not path or not os.path.exists(path):
            return

        ext = os.path.splitext(path)[1].lower()

        # 1. Pacotes e Projetos Trados
        if is_sdlpackage(path):
            self._load_sdlpackage(path)
            return
        elif is_sdlproj_file(path):
            self._load_sdlproj(path)
            return
        elif is_project_file(path):
            proj = Project.load(path)
            self._on_project_opened(proj)
            return

        # 2. Arquivo de Memória direto (.sdltm, .tmx)
        if ext in (".sdltm", ".tmx"):
            if self.editor_screen.tm and self.editor_screen.tm.count() > 0:
                self.editor_screen.attach_tm(path)
                self._navigate_to("editor")
                self.status_bar.showMessage(f"Memória de Tradução associada: {os.path.basename(path)}")
            else:
                self.tm_screen.load_tm_file(path)
                self._navigate_to("tm")
                self.status_bar.showMessage(f"Memória de Tradução aberta para edição: {os.path.basename(path)}")
            return

        # 3. Arquivo Bilingue já no formato SDLXLIFF / XLIFF
        if ext in (".sdlxliff", ".xlf", ".xliff"):
            dialog = QuickStartDialog(
                file_path=path,
                segment_count=0,
                default_src_lang="en-US",
                default_tgt_lang="pt-BR",
                parent=self
            )
            if dialog.exec() and dialog.confirmed:
                for tm_p in dialog.selected_tms:
                    self.editor_screen.attach_tm(tm_p)
                self.editor_screen._auto_slm_suggest = dialog.use_slm
                self.editor_screen.load_file(path)
                self._navigate_to("editor")
                self.status_bar.showMessage(f"Ficheiro {os.path.basename(path)} aberto no Editor.")
            return

        # 4. Documentos externos (.docx, .xlsx, .pptx, .pdf, imagens com OCR, .txt, .html, .xml, etc.)
        self.status_bar.showMessage(f"A converter {os.path.basename(path)} para SDLXLIFF...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            sdlxliff_path, seg_count = convert_to_sdlxliff(path, src_lang="en-US", tgt_lang="pt-BR")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Erro na Conversão", f"Não foi possível converter o arquivo para SDLXLIFF:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        # Abre o diálogo pedindo para associar TM e definir idiomas
        dialog = QuickStartDialog(
            file_path=path,
            segment_count=seg_count,
            default_src_lang="en-US",
            default_tgt_lang="pt-BR",
            parent=self
        )
        if dialog.exec() and dialog.confirmed:
            if dialog.source_lang != "en-US" or dialog.target_lang != "pt-BR":
                try:
                    sdlxliff_path, seg_count = convert_to_sdlxliff(
                        path,
                        src_lang=dialog.source_lang,
                        tgt_lang=dialog.target_lang
                    )
                except Exception:
                    pass

            for tm_p in dialog.selected_tms:
                self.editor_screen.attach_tm(tm_p)

            self.editor_screen._auto_slm_suggest = dialog.use_slm
            self.editor_screen.load_file(sdlxliff_path)
            self._navigate_to("editor")
            self.status_bar.showMessage(
                f"Ficheiro {os.path.basename(path)} ({seg_count:,} segmentos) convertido para SDLXLIFF e pronto para traduzir!"
            )

    def _open_sdlproj_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Projeto SDL Trados", "",
            "Projetos SDL (*.sdlproj);;Todos os Ficheiros (*.*)"
        )
        if path:
            self._load_sdlproj(path)

    def _load_sdlproj(self, path: str) -> None:
        project = parse_sdlproj(path)
        if not project or not project.files:
            QMessageBox.warning(self, "Projeto SDL", "Não foi possível extrair ficheiros do projeto SDL.")
            return
        self._on_project_opened(project)
        self.status_bar.showMessage(f"Projeto SDL carregado: {project.name} ({len(project.files)} ficheiro(s))")

    def _open_sdlpackage_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Pacote de Projeto SDL (.sdlppx)", "",
            "Pacotes SDL Trados (*.sdlppx *.sdlrpx);;Todos os Ficheiros (*.*)"
        )
        if path:
            self._load_sdlpackage(path)

    def _load_sdlpackage(self, path: str) -> None:
        proj_path, project = extract_package(path)
        if not project:
            QMessageBox.warning(self, "Pacote SDL", "Falha ao descompactar ou ler projeto do pacote.")
            return
        self._on_project_opened(project)
        self.status_bar.showMessage(f"Pacote extraído com sucesso: {os.path.basename(path)}")

    def _export_return_package_dialog(self) -> None:
        if not self._current_project:
            QMessageBox.warning(self, "Pacote de Retorno", "Nenhum projeto ativo com ficheiros carregados.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Gerar Pacote de Retorno SDL (.sdlrpx)",
            f"{self._current_project.name}_return.sdlrpx",
            "Pacote de Retorno SDL (*.sdlrpx)"
        )
        if path:
            out_file = create_return_package(self._current_project, path)
            QMessageBox.information(self, "Pacote de Retorno", f"Pacote de retorno criado com sucesso:\n{out_file}")

    def _open_specific_file(self, path: str) -> None:
        self.editor_screen.load_file(path)
        self._navigate_to("editor")
        self.status_bar.showMessage(f"Ficheiro carregado no Editor: {os.path.basename(path)}")

    def _on_new_project(self) -> None:
        self._navigate_to("projects")
        self.projects_screen._new_project()

    def _show_xbench_qa(self) -> None:
        """Abre a janela de QA estilo ApSIC Xbench (Trados Studio Verify F8)."""
        if self.stack.currentIndex() != 4:
            self._navigate_to("editor")
        if not self.editor_screen.tm or self.editor_screen.tm.count() == 0:
            QMessageBox.information(
                self, "Quality Assurance (Verify)",
                "Abra um ficheiro ou projeto primeiro para executar a verificação de QA."
            )
            return

        total = self.editor_screen.tm.count()
        segments = self.editor_screen.tm.page(0, total)
        dialog = XbenchQADialog(segments, parent=self)
        dialog.jump_to_segment_requested.connect(self._on_xbench_jump)
        dialog.exec()

    def _on_xbench_jump(self, row_index: int) -> None:
        self._navigate_to("editor")
        self.editor_screen._select_row(row_index)
        self.editor_screen.tgt_edit.setFocus()

    def _show_tm_utility(self) -> None:
        """Abre o Utilitário Trados Translation Memory Management."""
        dialog = TmManagementUtilityDialog(current_tm=self.editor_screen.tm, parent=self)
        dialog.tm_updated.connect(self._on_tm_utility_updated)
        dialog.exec()

    def _on_tm_utility_updated(self) -> None:
        if self.editor_screen.model:
            self.editor_screen.model.refresh()
            self.editor_screen._update_stats()

    def _on_project_opened(self, project: Project) -> None:
        self._current_project = project
        self.files_screen.set_project(project)
        self.projects_screen._current_project = project
        self.projects_screen._update_details_panel(project)
        if project.files:
            self.editor_screen.load_project(project)
        self._navigate_to("files")
    def _show_batch_tasks(self, task_name: str = "analyze") -> None:
        """Abre o diálogo de Tarefas em Lote (Trados Batch Tasks Wizard)."""
        from ui.batch_tasks_dialog import BatchTasksDialog
        dialog = BatchTasksDialog(
            project=self._current_project,
            current_tm=self.editor_screen.tm,
            initial_task=task_name if task_name != "wizard" else "analyze",
            parent=self
        )
        dialog.exec()

    def _explore_containing_folder(self) -> None:
        """Abre a pasta dos ficheiros no Explorador do Windows."""
        folder = None
        if self._current_project and self._current_project.files:
            folder = os.path.dirname(self._current_project.files[0].path)
        elif self.editor_screen.tm and hasattr(self.editor_screen.tm, "db_path"):
            folder = os.path.dirname(self.editor_screen.tm.db_path)

        if not folder or not os.path.exists(folder):
            folder = os.getcwd()

        try:
            os.startfile(folder)
        except Exception:
            import subprocess
            subprocess.Popen(f'explorer "{folder}"')

    def _show_project_settings(self) -> None:
        """Exibe o diálogo oficial de configurações do projeto e memórias associadas (Alt+F8)."""
        self.editor_screen.show_project_settings()
        if self._current_project:
            self._current_project.tm_paths = [tm.path for tm in self.editor_screen.attached_tms if tm.enabled]

    def _show_slm_studio(self) -> None:
        """Abre o SLM Studio para criação, treino e gestão de modelos neurais a partir de TMs .sdltm."""
        from ui.slm_studio_dialog import SLMStudioDialog
        dialog = SLMStudioDialog(parent=self)
        dialog.model_changed.connect(self._on_slm_model_changed)
        dialog.exec()

    def _on_slm_model_changed(self, model_name: str) -> None:
        self.editor_screen.set_active_slm_model(model_name)
        self.status_bar.showMessage(f"SLM ativa atualizada: {model_name}")

    def _on_slm_translate_requested(self) -> None:
        if self.stack.currentIndex() != 4:
            self._navigate_to("editor")
        self.editor_screen.translate_current_with_slm()

    def closeEvent(self, event) -> None:
        if hasattr(self, "editor_screen") and self.editor_screen.loader is not None and self.editor_screen.loader.isRunning():
            self.editor_screen.loader.requestInterruption()
            self.editor_screen.loader.quit()
            self.editor_screen.loader.wait(2000)
        super().closeEvent(event)
