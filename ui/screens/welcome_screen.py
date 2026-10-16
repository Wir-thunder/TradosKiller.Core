"""
ui.screens.welcome_screen - Tela Inicial Universal do TradosKiller.

Foco total em usabilidade e velocidade:
- Enorme zona Drag & Drop para qualquer formato de arquivo (Office, PDF, Imagens com OCR, Texto, CAT).
- Clique para selecionar arquivo ou arraste direto para criar automaticamente o SDLXLIFF.
- Painel com formatos suportados e atalhos rápidos para abrir projetos ou TMs.
- Histórico de ficheiros e projetos recentes com abertura em 1 clique.
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QScrollArea, QListWidget, QListWidgetItem
)

from core.config import load_config
from core.file_importer import ALL_SUPPORTED_EXTS, get_file_type_badge, is_supported_file


class UniversalDropZone(QFrame):
    """Área drag & drop principal na tela de boas-vindas."""
    file_dropped = Signal(str)
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self._is_hovered = False
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 45, 40, 45)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        icon = QLabel("📥")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 56px; border: none; background: transparent;")
        layout.addWidget(icon)

        title = QLabel("Arraste e solte qualquer arquivo aqui para começar")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setStyleSheet("color: #ffffff; border: none; background: transparent;")
        layout.addWidget(title)

        sub = QLabel(
            "Word (.docx), Excel (.xlsx), PowerPoint (.pptx), PDF, Imagens (com OCR),\n"
            "Texto (.txt, .md, .html, .xml, .json) ou arquivos Trados (.sdlxliff, .sdltm, .tmx)"
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #9cdcfe; font-size: 12px; line-height: 1.5; border: none; background: transparent;")
        layout.addWidget(sub)

        btn_select = QPushButton("📂 Selecionar Arquivo do Computador...")
        btn_select.setCursor(Qt.PointingHandCursor)
        btn_select.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: white; font-weight: bold;
                border: none; border-radius: 5px; padding: 10px 24px; font-size: 13px;
                margin-top: 8px;
            }
            QPushButton:hover { background-color: #1c97ea; }
        """)
        btn_select.clicked.connect(self.clicked.emit)
        layout.addWidget(btn_select, alignment=Qt.AlignCenter)

    def _update_style(self):
        border_col = "#007acc" if self._is_hovered else "#3e3e42"
        bg_col = "#1b334f" if self._is_hovered else "#202023"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_col};
                border: 2px dashed {border_col};
                border-radius: 12px;
            }}
            QFrame:hover {{
                border-color: #007acc;
                background-color: #18283c;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if is_supported_file(path) or os.path.isdir(path):
                    event.acceptProposedAction()
                    self._is_hovered = True
                    self._update_style()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._is_hovered = False
        self._update_style()

    def dropEvent(self, event: QDropEvent):
        self._is_hovered = False
        self._update_style()
        for url in event.mimeData().urls():
            f_path = url.toLocalFile()
            if is_supported_file(f_path):
                self.file_dropped.emit(f_path)
                event.acceptProposedAction()
                return


class WelcomeScreen(QWidget):
    """Tela de boas-vindas centrada no fluxo drag & drop rápido sem burocracia."""
    file_selected = Signal(str)
    open_project_requested = Signal()
    open_tm_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = load_config()
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        # ---------------- Cabeçalho Superior
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        logo_title_v = QVBoxLayout()
        logo_title_v.setSpacing(2)

        title = QLabel("TradosKiller — CAT Workspace de Alta Performance")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("color: #8eb4f3;")
        logo_title_v.addWidget(title)

        subtitle = QLabel("Traduza qualquer documento sem travar e sem burocracia.")
        subtitle.setStyleSheet("color: #888888; font-size: 12px;")
        logo_title_v.addWidget(subtitle)

        header_layout.addLayout(logo_title_v)
        header_layout.addStretch()

        # Botões de Ação Rápida no Topo
        btn_proj = QPushButton("📦 Abrir Projeto (.sdlproj)")
        btn_proj.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30; color: #e0e0e0; border: 1px solid #3e3e42;
                border-radius: 4px; padding: 7px 14px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #3e3e42; color: white; }
        """)
        btn_proj.clicked.connect(self.open_project_requested.emit)
        header_layout.addWidget(btn_proj)

        btn_tm = QPushButton("🗄 Abrir Memória (.sdltm)")
        btn_tm.setStyleSheet("""
            QPushButton {
                background-color: #2d2d30; color: #e0e0e0; border: 1px solid #3e3e42;
                border-radius: 4px; padding: 7px 14px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #3e3e42; color: white; }
        """)
        btn_tm.clicked.connect(self.open_tm_requested.emit)
        header_layout.addWidget(btn_tm)

        main_layout.addLayout(header_layout)

        # ---------------- Zona Drag & Drop Universal (O Coração da Tela)
        self.drop_zone = UniversalDropZone(self)
        self.drop_zone.file_dropped.connect(self._handle_file_dropped)
        self.drop_zone.clicked.connect(self._browse_file)
        main_layout.addWidget(self.drop_zone, stretch=3)

        # ---------------- Badges dos Formatos Suportados
        badges_frame = QFrame()
        badges_frame.setStyleSheet("background-color: #202022; border: 1px solid #2d2d30; border-radius: 6px;")
        bf_layout = QHBoxLayout(badges_frame)
        bf_layout.setContentsMargins(14, 10, 14, 10)
        bf_layout.setSpacing(16)

        badges_info = [
            ("📝 Documentos", "Word (.docx), Excel (.xlsx), PowerPoint (.pptx)"),
            ("📑 PDF & OCR", "PDFs nativos e digitalizados, Imagens (.png, .jpg)"),
            ("🗂 Trados & CAT", ".sdlxliff, .sdltm, .tmx, .sdlproj, .sdlppx"),
            ("🌐 Web & Texto", ".txt, .html, .xml, .json, .csv, .md, .po"),
        ]

        for b_title, b_desc in badges_info:
            b_v = QVBoxLayout()
            b_v.setSpacing(2)
            lbl_bt = QLabel(b_title)
            lbl_bt.setStyleSheet("color: #8eb4f3; font-weight: bold; font-size: 11px;")
            b_v.addWidget(lbl_bt)
            lbl_bd = QLabel(b_desc)
            lbl_bd.setStyleSheet("color: #888888; font-size: 10px;")
            b_v.addWidget(lbl_bd)
            bf_layout.addLayout(b_v)

        main_layout.addWidget(badges_frame)

        # ---------------- Ficheiros Recentes
        recent_files = getattr(self._config, "recent_files", [])
        if recent_files:
            recents_lbl = QLabel("Ficheiros Recentes:")
            recents_lbl.setStyleSheet("color: #cccccc; font-weight: bold; font-size: 12px; margin-top: 4px;")
            main_layout.addWidget(recents_lbl)

            self.list_recents = QListWidget()
            self.list_recents.setMaximumHeight(120)
            self.list_recents.setStyleSheet("""
                QListWidget {
                    background-color: #1a1a1a;
                    border: 1px solid #333333;
                    border-radius: 4px;
                    color: #e0e0e0;
                    font-size: 11px;
                }
                QListWidget::item { padding: 5px 8px; border-bottom: 1px solid #252525; }
                QListWidget::item:hover { background-color: #094771; }
            """)

            for p in recent_files[:5]:
                if os.path.exists(p):
                    cat, icon = get_file_type_badge(p)
                    item = QListWidgetItem(f"{icon}  {os.path.basename(p)}  —  {p}")
                    item.setData(Qt.UserRole, p)
                    self.list_recents.addItem(item)

            self.list_recents.itemDoubleClicked.connect(self._on_recent_double_clicked)
            main_layout.addWidget(self.list_recents, stretch=1)

    def _browse_file(self):
        """Abre o diálogo de seleção de arquivo suportando todos os formatos do Trados + OCR."""
        filter_str = (
            "Todos os Formatos Suportados (*.docx *.xlsx *.pptx *.pdf *.png *.jpg *.jpeg *.tiff *.bmp *.txt *.html *.xml *.json *.csv *.sdlxliff *.tmx *.sdltm *.sdlproj *.sdlppx);;"
            "Documentos Office (*.docx *.xlsx *.pptx);;"
            "PDF e Imagens OCR (*.pdf *.png *.jpg *.jpeg *.tiff *.bmp);;"
            "Arquivos Trados e CAT (*.sdlxliff *.sdltm *.tmx *.sdlproj *.sdlppx);;"
            "Arquivos de Texto e Web (*.txt *.html *.xml *.json *.csv *.md);;"
            "Todos os Arquivos (*.*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(self, "Selecionar Arquivo para Traduzir", "", filter_str)
        if file_path:
            self.file_selected.emit(file_path)

    def _handle_file_dropped(self, path: str):
        self.file_selected.emit(path)

    def _on_recent_double_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            self.file_selected.emit(path)

