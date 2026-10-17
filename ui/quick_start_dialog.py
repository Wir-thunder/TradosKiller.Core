"""
ui.quick_start_dialog - Diálogo de Configuração Rápida e Associação de Memória de Tradução.

Exibido imediatamente após arrastar ou selecionar qualquer arquivo de texto ou documento:
- Mostra o arquivo importado e total de segmentos detectados/convertidos
- Permite associar uma ou mais Memórias de Tradução (.sdltm, .tmx) via arrastar/soltar ou seleção
- Exibe TMs recentes para reutilização instantânea
- Permite confirmar par de idiomas e assistência neural por SLM
- Um clique (ou Enter) para entrar direto no Editor e começar a traduzir!
"""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QFileDialog, QCheckBox, QListWidget,
    QListWidgetItem, QMessageBox
)

from core.config import load_config, save_config
from core.file_importer import get_file_type_badge


COMMON_LANGS = [
    ("en-US", "Inglês (Estados Unidos) — en-US"),
    ("pt-BR", "Português (Brasil) — pt-BR"),
    ("pt-PT", "Português (Portugal) — pt-PT"),
    ("es-ES", "Espanhol (Espanha) — es-ES"),
    ("es-419", "Espanhol (América Latina) — es-419"),
    ("de-DE", "Alemão (Alemanha) — de-DE"),
    ("fr-FR", "Francês (França) — fr-FR"),
    ("it-IT", "Italiano (Itália) — it-IT"),
    ("ja-JP", "Japonês (Japão) — ja-JP"),
    ("zh-CN", "Chinês Simplificado — zh-CN"),
    ("ru-RU", "Russo (Rússia) — ru-RU"),
]


class TMDropZone(QFrame):
    """Área drag & drop dedicada para soltar ficheiros de Memória (.sdltm, .tmx)."""
    tm_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self._is_hovered = False
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(4)

        icon = QLabel("🗄")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 24px; border: none; background: transparent;")
        layout.addWidget(icon)

        lbl = QLabel("Arraste uma Memória de Tradução (.sdltm ou .tmx) aqui")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #8eb4f3; font-weight: bold; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(lbl)

        sub = QLabel("Ou clique em 'Procurar Memória' abaixo para associar")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #888888; font-size: 10px; border: none; background: transparent;")
        layout.addWidget(sub)

    def _update_style(self):
        border_col = "#007acc" if self._is_hovered else "#3e3e42"
        bg_col = "#1e3a5f" if self._is_hovered else "#252528"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_col};
                border: 2px dashed {border_col};
                border-radius: 6px;
            }}
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                ext = os.path.splitext(url.toLocalFile())[1].lower()
                if ext in (".sdltm", ".tmx", ".db", ".sqlite"):
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
            ext = os.path.splitext(f_path)[1].lower()
            if ext in (".sdltm", ".tmx", ".db", ".sqlite"):
                self.tm_dropped.emit(f_path)
                event.acceptProposedAction()
                return


class QuickStartDialog(QDialog):
    """Diálogo modal para configurar a tradução e anexar TMs antes de abrir no editor."""

    def __init__(
        self,
        file_path: str,
        segment_count: int = 0,
        default_src_lang: str = "en-US",
        default_tgt_lang: str = "pt-BR",
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Configuração Rápida de Tradução — TradosKiller")
        self.resize(620, 520)
        self.setModal(True)

        self.file_path = file_path
        self.segment_count = segment_count
        self.selected_tms: List[str] = []
        self.use_slm = True
        self.confirmed = False

        self._config = load_config()
        self._init_ui(default_src_lang, default_tgt_lang)

    def _init_ui(self, def_src: str, def_tgt: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # ---------------- 1. Cabeçalho com Informações do Arquivo
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet("background-color: #252528; border: 1px solid #333333; border-radius: 6px; padding: 4px;")
        hl = QHBoxLayout(hdr_frame)
        hl.setContentsMargins(10, 8, 10, 8)
        hl.setSpacing(12)

        cat_name, cat_icon = get_file_type_badge(self.file_path)
        icon_lbl = QLabel(cat_icon)
        icon_lbl.setStyleSheet("font-size: 28px;")
        hl.addWidget(icon_lbl)

        info_v = QVBoxLayout()
        info_v.setSpacing(2)

        fname = os.path.basename(self.file_path)
        lbl_name = QLabel(fname)
        lbl_name.setFont(QFont("Segoe UI", 11, QFont.Bold))
        lbl_name.setStyleSheet("color: #ffffff;")
        info_v.addWidget(lbl_name)

        seg_text = f"Pronto para traduzir: {self.segment_count:,} segmentos detectados" if self.segment_count > 0 else "Ficheiro bilingue carregado"
        lbl_details = QLabel(f"{cat_name}  •  {seg_text}")
        lbl_details.setStyleSheet("color: #2ecc71; font-size: 11px; font-weight: bold;")
        info_v.addWidget(lbl_details)
        hl.addLayout(info_v)
        hl.addStretch()

        layout.addWidget(hdr_frame)

        # ---------------- 2. Par de Idiomas
        lang_group = QFrame()
        lang_group.setStyleSheet("background-color: #202022; border: 1px solid #333333; border-radius: 6px;")
        lang_layout = QHBoxLayout(lang_group)
        lang_layout.setContentsMargins(12, 10, 12, 10)
        lang_layout.setSpacing(14)

        # Fonte
        src_v = QVBoxLayout()
        src_v.setSpacing(4)
        src_v.addWidget(QLabel("Idioma Fonte (Origem):"))
        self.combo_src = QComboBox()
        for code, name in COMMON_LANGS:
            self.combo_src.addItem(name, code)
        self._select_lang_code(self.combo_src, def_src)
        src_v.addWidget(self.combo_src)
        lang_layout.addLayout(src_v)

        arrow = QLabel("➔")
        arrow.setStyleSheet("font-size: 16px; color: #8eb4f3; font-weight: bold;")
        arrow.setAlignment(Qt.AlignCenter)
        lang_layout.addWidget(arrow)

        # Destino
        tgt_v = QVBoxLayout()
        tgt_v.setSpacing(4)
        tgt_v.addWidget(QLabel("Idioma Alvo (Tradução):"))
        self.combo_tgt = QComboBox()
        for code, name in COMMON_LANGS:
            self.combo_tgt.addItem(name, code)
        self._select_lang_code(self.combo_tgt, def_tgt)
        tgt_v.addWidget(self.combo_tgt)
        lang_layout.addLayout(tgt_v)

        layout.addWidget(lang_group)

        # ---------------- 3. Associação de Memória de Tradução (TM)
        tm_title = QLabel("Associar Memória de Tradução (Opcional):")
        tm_title.setStyleSheet("font-weight: bold; color: #f39c12; font-size: 11px;")
        layout.addWidget(tm_title)

        self.drop_zone = TMDropZone(self)
        self.drop_zone.tm_dropped.connect(self._add_tm_path)
        layout.addWidget(self.drop_zone)

        # Lista de TMs selecionadas
        self.list_tms = QListWidget()
        self.list_tms.setMaximumHeight(80)
        self.list_tms.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
            }
            QListWidget::item { padding: 4px; }
        """)
        layout.addWidget(self.list_tms)

        # Botões de ação da TM
        tm_btn_layout = QHBoxLayout()
        tm_btn_layout.setSpacing(8)

        btn_browse_tm = QPushButton("📂 Procurar Memória (.sdltm, .tmx)...")
        btn_browse_tm.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: #ffffff; border: 1px solid #555555;
                border-radius: 4px; padding: 5px 12px; font-size: 11px;
            }
            QPushButton:hover { background-color: #444444; }
        """)
        btn_browse_tm.clicked.connect(self._browse_tm)
        tm_btn_layout.addWidget(btn_browse_tm)

        btn_create_tm = QPushButton("➕ Criar Nova TM (.sdltm)...")
        btn_create_tm.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f; color: #93c5fd; border: 1px solid #3b82f6;
                border-radius: 4px; padding: 5px 12px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb; color: white; }
        """)
        btn_create_tm.clicked.connect(self._create_new_tm)
        tm_btn_layout.addWidget(btn_create_tm)

        btn_clear_tm = QPushButton("Remover Selecionada")
        btn_clear_tm.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #888888; border: 1px solid #444444;
                border-radius: 4px; padding: 5px 10px; font-size: 11px;
            }
            QPushButton:hover { background-color: #333333; color: #e74c3c; }
        """)
        btn_clear_tm.clicked.connect(self._remove_selected_tm)
        tm_btn_layout.addWidget(btn_clear_tm)

        tm_btn_layout.addStretch()
        layout.addLayout(tm_btn_layout)

        # ---------------- 4. Assistente Neural SLM (Ollama)
        self.chk_slm = QCheckBox("🤖 Habilitar sugestões automáticas da SLM Neural local (Ollama)")
        self.chk_slm.setChecked(True)
        self.chk_slm.setStyleSheet("color: #cccccc; font-size: 11px;")
        layout.addWidget(self.chk_slm)

        layout.addStretch()

        # ---------------- 5. Botões de Confirmação
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_no_tm = QPushButton("Traduzir sem TM")
        btn_no_tm.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: #bbbbbb; border: 1px solid #444444;
                border-radius: 4px; padding: 8px 16px; font-size: 11px;
            }
            QPushButton:hover { background-color: #444444; color: white; }
        """)
        btn_no_tm.clicked.connect(self._start_without_tm)
        btn_row.addWidget(btn_no_tm)

        btn_row.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #888888; border: 1px solid #444444;
                border-radius: 4px; padding: 8px 16px; font-size: 11px;
            }
            QPushButton:hover { background-color: #333333; }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self.btn_start = QPushButton("▶ Iniciar Tradução Agora (Enter)")
        self.btn_start.setDefault(True)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: white; font-weight: bold; border: none;
                border-radius: 4px; padding: 9px 24px; font-size: 12px;
            }
            QPushButton:hover { background-color: #1c97ea; }
        """)
        self.btn_start.clicked.connect(self._start_translation)
        btn_row.addWidget(self.btn_start)

        layout.addLayout(btn_row)

        # Carrega TMs usadas recentemente na lista se houver
        recent_tms = getattr(self._config, "recent_tms", [])
        if recent_tms and os.path.exists(recent_tms[0]):
            self._add_tm_path(recent_tms[0])

    def _select_lang_code(self, combo: QComboBox, code: str):
        for i in range(combo.count()):
            if combo.itemData(i) == code or code.lower() in combo.itemData(i).lower():
                combo.setCurrentIndex(i)
                return

    def _create_new_tm(self):
        from ui.create_sdltm_dialog import CreateSdltmDialog
        dlg = CreateSdltmDialog(
            default_src=self.source_lang,
            default_tgt=self.target_lang,
            parent=self
        )
        if dlg.exec() and dlg.created_path:
            self._add_tm_path(dlg.created_path)

    def _browse_tm(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Memória de Tradução",
            "",
            "Memórias de Tradução (*.sdltm *.tmx *.db);;Trados SDLTM (*.sdltm);;TMX Standard (*.tmx);;Todos os Ficheiros (*.*)"
        )
        if file_path:
            self._add_tm_path(file_path)

    def _add_tm_path(self, path: str):
        if path not in self.selected_tms and os.path.exists(path):
            self.selected_tms.append(path)
            item = QListWidgetItem(f"✓ {os.path.basename(path)}  —  ({path})")
            item.setData(Qt.UserRole, path)
            self.list_tms.addItem(item)
            self.btn_start.setText("▶ Iniciar Tradução com TM (Enter)")

    def _remove_selected_tm(self):
        curr = self.list_tms.currentItem()
        if curr:
            path = curr.data(Qt.UserRole)
            if path in self.selected_tms:
                self.selected_tms.remove(path)
            self.list_tms.takeItem(self.list_tms.row(curr))
            if not self.selected_tms:
                self.btn_start.setText("▶ Iniciar Tradução Agora (Enter)")

    def _start_without_tm(self):
        self.selected_tms.clear()
        self.confirmed = True
        self.accept()

    def _start_translation(self):
        self.confirmed = True
        self.use_slm = self.chk_slm.isChecked()
        # Salva TMs nos recentes da configuração
        if self.selected_tms:
            recent = getattr(self._config, "recent_tms", [])
            for tm in self.selected_tms:
                if tm in recent:
                    recent.remove(tm)
                recent.insert(0, tm)
            self._config.recent_tms = recent[:10]
            save_config(self._config)
        self.accept()

    @property
    def source_lang(self) -> str:
        return self.combo_src.currentData() or "en-US"

    @property
    def target_lang(self) -> str:
        return self.combo_tgt.currentData() or "pt-BR"

