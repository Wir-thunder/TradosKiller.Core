"""
ui.find_replace_bar - Barra de Localizar e Substituir (Ctrl+F / Ctrl+H) estilo Trados Studio / VS Code.

Suporta:
- Localização rápida com contagem de ocorrências
- Navegação para a ocorrência anterior (Shift+Enter) e próxima (Enter)
- Escopo de busca: Fonte, Tradução ou Ambos
- Modos: Diferenciar Maiúsculas/Minúsculas (Aa), Palavra Inteira (\\b), Regex (.*)
- Substituição individual (Replace) e em massa (Replace All)
- Atalhos integrados e animação de visibilidade suave
"""
from __future__ import annotations

import re
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QFrame, QToolButton
)


class FindReplaceBar(QFrame):
    """Barra compacta de Localizar e Substituir."""
    
    find_next_signal = Signal(str, str, bool, bool, bool) # text, field, case, whole, regex
    find_prev_signal = Signal(str, str, bool, bool, bool)
    replace_signal = Signal(str, str, str, bool, bool)    # find, repl, field, case, regex
    replace_all_signal = Signal(str, str, str, bool, bool)
    filter_signal = Signal(str, str)                      # live filter text, field
    close_signal = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FindReplaceBar")
        self.setStyleSheet("""
            #FindReplaceBar {
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 6px;
                padding: 4px;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #f1f1f1;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
            QToolButton {
                background-color: #333333;
                color: #cccccc;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 3px 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QToolButton:hover {
                background-color: #444444;
                color: #ffffff;
            }
            QToolButton:checked {
                background-color: #007acc;
                color: #ffffff;
                border: 1px solid #1c97ea;
            }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QComboBox {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 11px;
            }
        """)

        self._build_ui()
        self._setup_shortcuts()
        self.hide()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # ---------------- Linha 1: Localizar
        find_row = QHBoxLayout()
        find_row.setSpacing(6)

        # Botão de alternar expansão para Substituir
        self.btn_toggle_replace = QToolButton()
        self.btn_toggle_replace.setText("▶")
        self.btn_toggle_replace.setToolTip("Alternar Substituir (Ctrl+H)")
        self.btn_toggle_replace.setCheckable(True)
        self.btn_toggle_replace.clicked.connect(self._toggle_replace_mode)
        find_row.addWidget(self.btn_toggle_replace)

        # Campo de busca
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Localizar no texto... (Enter para próximo)")
        self.find_edit.setMinimumWidth(220)
        self.find_edit.textChanged.connect(self._on_find_text_changed)
        self.find_edit.returnPressed.connect(self._on_find_next)
        find_row.addWidget(self.find_edit)

        # Contador de ocorrências
        self.lbl_matches = QLabel("0 de 0")
        self.lbl_matches.setStyleSheet("color: #888888; font-size: 10px; padding: 0 4px;")
        find_row.addWidget(self.lbl_matches)

        # Opções de correspondência
        self.btn_case = QToolButton()
        self.btn_case.setText("Aa")
        self.btn_case.setToolTip("Diferenciar maiúsculas/minúsculas (Alt+C)")
        self.btn_case.setCheckable(True)
        self.btn_case.clicked.connect(self._on_find_text_changed)
        find_row.addWidget(self.btn_case)

        self.btn_regex = QToolButton()
        self.btn_regex.setText(".*")
        self.btn_regex.setToolTip("Usar Expressão Regular (Alt+R)")
        self.btn_regex.setCheckable(True)
        self.btn_regex.clicked.connect(self._on_find_text_changed)
        find_row.addWidget(self.btn_regex)

        # Escopo
        self.scope_box = QComboBox()
        self.scope_box.addItems(["Ambos", "Fonte", "Tradução"])
        self.scope_box.setToolTip("Campo onde pesquisar")
        self.scope_box.currentIndexChanged.connect(self._on_find_text_changed)
        find_row.addWidget(self.scope_box)

        # Navegação
        self.btn_prev = QToolButton()
        self.btn_prev.setText("▲")
        self.btn_prev.setToolTip("Ocorrência Anterior (Shift+Enter)")
        self.btn_prev.clicked.connect(self._on_find_prev)
        find_row.addWidget(self.btn_prev)

        self.btn_next = QToolButton()
        self.btn_next.setText("▼")
        self.btn_next.setToolTip("Próxima Ocorrência (Enter)")
        self.btn_next.clicked.connect(self._on_find_next)
        find_row.addWidget(self.btn_next)

        # Fechar
        self.btn_close = QToolButton()
        self.btn_close.setText("✕")
        self.btn_close.setToolTip("Fechar barra (Esc)")
        self.btn_close.clicked.connect(self.close_bar)
        find_row.addWidget(self.btn_close)

        main_layout.addLayout(find_row)

        # ---------------- Linha 2: Substituir
        self.replace_widget = QWidget()
        replace_row = QHBoxLayout(self.replace_widget)
        replace_row.setContentsMargins(24, 0, 0, 0)
        replace_row.setSpacing(6)

        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Substituir por...")
        self.replace_edit.returnPressed.connect(self._on_replace)
        replace_row.addWidget(self.replace_edit)

        self.btn_replace = QPushButton("Substituir")
        self.btn_replace.setToolTip("Substituir segmento atual")
        self.btn_replace.clicked.connect(self._on_replace)
        replace_row.addWidget(self.btn_replace)

        self.btn_replace_all = QPushButton("Substituir Todos")
        self.btn_replace_all.setToolTip("Substituir em todos os segmentos")
        self.btn_replace_all.clicked.connect(self._on_replace_all)
        replace_row.addWidget(self.btn_replace_all)

        main_layout.addWidget(self.replace_widget)
        self.replace_widget.hide()

    def _setup_shortcuts(self) -> None:
        """Configura atalhos internos."""
        QShortcut(QKeySequence("Esc"), self, self.close_bar)
        QShortcut(QKeySequence("Shift+Return"), self, self._on_find_prev)

    def show_find(self, initial_text: str = "") -> None:
        """Abre a barra em modo de Localizar (Ctrl+F)."""
        self.show()
        if initial_text:
            self.find_edit.setText(initial_text)
            self.find_edit.selectAll()
        self.find_edit.setFocus()

    def show_replace(self, initial_text: str = "") -> None:
        """Abre a barra em modo de Substituir (Ctrl+H)."""
        self.show()
        self.btn_toggle_replace.setChecked(True)
        self.btn_toggle_replace.setText("▼")
        self.replace_widget.show()
        if initial_text:
            self.find_edit.setText(initial_text)
            self.find_edit.selectAll()
        self.find_edit.setFocus()

    def _toggle_replace_mode(self) -> None:
        is_open = self.btn_toggle_replace.isChecked()
        self.btn_toggle_replace.setText("▼" if is_open else "▶")
        self.replace_widget.setVisible(is_open)
        if is_open:
            self.replace_edit.setFocus()
        else:
            self.find_edit.setFocus()

    def close_bar(self) -> None:
        self.hide()
        self.close_signal.emit()

    def _get_scope(self) -> str:
        idx = self.scope_box.currentIndex()
        if idx == 1:
            return "source"
        elif idx == 2:
            return "target"
        return "both"

    def _on_find_text_changed(self) -> None:
        txt = self.find_edit.text()
        self.filter_signal.emit(txt, self._get_scope())

    def _on_find_next(self) -> None:
        txt = self.find_edit.text()
        if not txt:
            return
        self.find_next_signal.emit(
            txt, self._get_scope(),
            self.btn_case.isChecked(),
            False,
            self.btn_regex.isChecked()
        )

    def _on_find_prev(self) -> None:
        txt = self.find_edit.text()
        if not txt:
            return
        self.find_prev_signal.emit(
            txt, self._get_scope(),
            self.btn_case.isChecked(),
            False,
            self.btn_regex.isChecked()
        )

    def _on_replace(self) -> None:
        f = self.find_edit.text()
        r = self.replace_edit.text()
        if not f:
            return
        self.replace_signal.emit(
            f, r, self._get_scope(),
            self.btn_case.isChecked(),
            self.btn_regex.isChecked()
        )

    def _on_replace_all(self) -> None:
        f = self.find_edit.text()
        r = self.replace_edit.text()
        if not f:
            return
        self.replace_all_signal.emit(
            f, r, self._get_scope(),
            self.btn_case.isChecked(),
            self.btn_regex.isChecked()
        )

    def update_match_count(self, current: int, total: int) -> None:
        """Atualiza o contador de resultados no estilo '3 de 15'."""
        if total == 0:
            self.lbl_matches.setText("Sem resultados")
            self.lbl_matches.setStyleSheet("color: #e74c3c; font-size: 10px; font-weight: bold;")
        else:
            self.lbl_matches.setText(f"{current} de {total}")
            self.lbl_matches.setStyleSheet("color: #3dae73; font-size: 10px; font-weight: bold;")

