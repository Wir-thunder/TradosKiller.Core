"""
ui.create_sdltm_dialog - Diálogo para criação de nova memória de tradução RWS Trados (.sdltm).

Permite ao tradutor definir:
- Caminho do ficheiro no disco
- Nome descritivo da memória
- Idioma de Origem (Source Language)
- Idioma de Destino (Target Language)
Gera uma base SQLite SDLTM 100% em conformidade com o SDL Trados Studio.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFileDialog, QMessageBox, QFrame,
    QGroupBox
)

from io_layer.sdltm import create_empty_sdltm
from ui.quick_start_dialog import COMMON_LANGS


class CreateSdltmDialog(QDialog):
    """Diálogo modal moderno para criação de novas memórias .sdltm."""

    def __init__(
        self,
        default_src: str = "en-US",
        default_tgt: str = "pt-BR",
        parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Criar Nova Memória de Tradução SDL Trados (.sdltm)")
        self.resize(560, 380)
        self.created_path: Optional[str] = None
        self._default_src = default_src
        self._default_tgt = default_tgt

        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #cccccc;
                font-size: 11px;
            }
            QGroupBox {
                border: 1px solid #3e3e42;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
                font-weight: bold;
                color: #8eb4f3;
                font-size: 11px;
            }
            QLineEdit, QComboBox {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 11px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #007acc;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: #ffffff;
                selection-background-color: #007acc;
                border: 1px solid #3e3e42;
            }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 7px 16px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Cabeçalho
        head_v = QVBoxLayout()
        head_v.setSpacing(3)
        title = QLabel("➕ Nova Memória de Tradução RWS (.sdltm)")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #8eb4f3;")
        head_v.addWidget(title)

        subtitle = QLabel("Crie uma memória de tradução nativa compatível com todas as versões do Trados Studio.")
        subtitle.setStyleSheet("color: #888888; font-size: 11px;")
        head_v.addWidget(subtitle)
        layout.addLayout(head_v)

        # Grupo: Localização do Ficheiro & Nome
        grp_file = QGroupBox("Arquivo & Identificação")
        gv = QVBoxLayout(grp_file)
        gv.setSpacing(8)

        lbl_path = QLabel("Local do Arquivo (.sdltm):")
        gv.addWidget(lbl_path)

        path_h = QHBoxLayout()
        self.edit_path = QLineEdit()
        self.edit_path.setPlaceholderText("Selecione onde salvar o arquivo .sdltm...")
        self.edit_path.textChanged.connect(self._on_path_changed)
        path_h.addWidget(self.edit_path, stretch=1)

        btn_browse = QPushButton("Procurar...")
        btn_browse.clicked.connect(self._browse_save_path)
        path_h.addWidget(btn_browse)
        gv.addLayout(path_h)

        lbl_name = QLabel("Nome Interno da Memória:")
        gv.addWidget(lbl_name)
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Nome exibido no Trados Studio...")
        gv.addWidget(self.edit_name)

        layout.addWidget(grp_file)

        # Grupo: Par de Idiomas
        grp_lang = QGroupBox("Par de Idiomas da Memória")
        gl = QHBoxLayout(grp_lang)
        gl.setSpacing(12)

        # Origem
        src_v = QVBoxLayout()
        src_v.setSpacing(4)
        src_v.addWidget(QLabel("Idioma Fonte (Origem):"))
        self.combo_src = QComboBox()
        self.combo_src.setEditable(True)
        for code, name in COMMON_LANGS:
            self.combo_src.addItem(name, code)
        self._select_combo_code(self.combo_src, self._default_src)
        src_v.addWidget(self.combo_src)
        gl.addLayout(src_v)

        arrow = QLabel("➔")
        arrow.setAlignment(Qt.AlignCenter)
        arrow.setStyleSheet("font-size: 16px; color: #8eb4f3; font-weight: bold; margin-top: 14px;")
        gl.addWidget(arrow)

        # Destino
        tgt_v = QVBoxLayout()
        tgt_v.setSpacing(4)
        tgt_v.addWidget(QLabel("Idioma Alvo (Tradução):"))
        self.combo_tgt = QComboBox()
        self.combo_tgt.setEditable(True)
        for code, name in COMMON_LANGS:
            self.combo_tgt.addItem(name, code)
        self._select_combo_code(self.combo_tgt, self._default_tgt)
        tgt_v.addWidget(self.combo_tgt)
        gl.addLayout(tgt_v)

        layout.addWidget(grp_lang)

        # Botões inferiores
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_create = QPushButton("💾 Criar Memória (.sdltm)")
        self.btn_create.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 7px 20px;
            }
            QPushButton:hover {
                background-color: #1c97ea;
            }
        """)
        self.btn_create.clicked.connect(self._create_tm)
        btn_layout.addWidget(self.btn_create)

        layout.addLayout(btn_layout)

    def _select_combo_code(self, combo: QComboBox, code: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == code or code.lower() in combo.itemText(i).lower():
                combo.setCurrentIndex(i)
                return
        combo.setEditText(code)

    def _get_lang_code(self, combo: QComboBox) -> str:
        idx = combo.currentIndex()
        if idx >= 0 and combo.itemData(idx):
            return combo.itemData(idx)
        text = combo.currentText().strip()
        if "—" in text:
            return text.split("—")[-1].strip()
        return text

    def _on_path_changed(self, text: str) -> None:
        if text.strip() and not self.edit_name.text().strip():
            stem = Path(text.strip()).stem
            self.edit_name.setText(stem)

    def _browse_save_path(self) -> None:
        default_dir = os.path.expanduser("~/Documents")
        default_file = os.path.join(default_dir, "NovaMemoria.sdltm")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Nova Memória de Tradução (.sdltm)",
            default_file,
            "Memória de Tradução SDL Trados (*.sdltm);;Todos os Ficheiros (*.*)"
        )
        if path:
            if not path.lower().endswith(".sdltm"):
                path += ".sdltm"
            self.edit_path.setText(path)
            if not self.edit_name.text().strip():
                self.edit_name.setText(Path(path).stem)

    def _create_tm(self) -> None:
        path = self.edit_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Caminho Inválido", "Por favor, selecione o local onde o arquivo .sdltm será salvo.")
            return

        if not path.lower().endswith(".sdltm"):
            path += ".sdltm"

        src_lang = self._get_lang_code(self.combo_src)
        tgt_lang = self._get_lang_code(self.combo_tgt)
        if not src_lang or not tgt_lang:
            QMessageBox.warning(self, "Idiomas Inválidos", "Por favor, defina os códigos de idioma de origem e destino.")
            return

        if src_lang.lower() == tgt_lang.lower():
            QMessageBox.warning(self, "Idiomas Iguais", "O idioma de origem e o idioma de destino não podem ser iguais.")
            return

        name = self.edit_name.text().strip() or Path(path).stem

        # Se já existir, confirma substituição
        if os.path.exists(path):
            reply = QMessageBox.question(
                self,
                "Sobrescrever Memória",
                f"O arquivo já existe:\n{path}\n\nDeseja sobrescrevê-lo com uma nova memória vazia?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        try:
            created = create_empty_sdltm(path, src_lang=src_lang, tgt_lang=tgt_lang, name=name)
            self.created_path = created
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Criar Memória", f"Não foi possível criar o arquivo .sdltm:\n{e}")
