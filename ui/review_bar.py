"""
ui.review_bar - Barra de Revisão e Controle de Qualidade estilo SDL Trados Studio.

Componentes:
- Workflow de Status de Segmento (Confirm & Next, Approve, Reject, Draft)
- Segment Filter Bar com badges em tempo real (Todos, Não Traduzidos, Rascunho, Traduzidos, Aprovados, Rejeitados)
- Navegação rápida para o próximo segmento pendente (Next Untranslated)
- Verificação Ortográfica e Garantia de Qualidade (QA)
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QButtonGroup, QToolButton, QScrollArea
)

from core.segment import SegState


class ReviewFilterPill(QPushButton):
    """Botão em formato de pill/tag com badge numérico de contagem."""
    
    def __init__(self, text: str, state_key: str, color_hex: str, parent=None) -> None:
        super().__init__(parent)
        self.state_key = state_key
        self.base_text = text
        self.color_hex = color_hex
        self.count = 0
        self.setCheckable(True)
        self._update_appearance()

    def set_count(self, count: int) -> None:
        self.count = count
        self._update_appearance()

    def _update_appearance(self) -> None:
        self.setText(f"{self.base_text} ({self.count})")
        is_checked = self.isChecked()
        border_col = self.color_hex if is_checked else "#3e3e42"
        bg_col = self.color_hex if is_checked else "#252526"
        text_col = "#ffffff" if is_checked else "#cccccc"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_col};
                color: {text_col};
                border: 1px solid {border_col};
                border-radius: 12px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: {'bold' if is_checked else 'normal'};
            }}
            QPushButton:hover {{
                border: 1px solid {self.color_hex};
                color: #ffffff;
            }}
        """)


class ReviewBar(QFrame):
    """Barra horizontal de revisão e filtragem de segmentos."""

    filter_changed = Signal(str)           # state: "all", "untranslated", "draft", "translated", "approved", "rejected"
    status_change_requested = Signal(SegState) # SegState to apply to current segment
    confirm_and_next_requested = Signal()
    next_untranslated_requested = Signal()
    spellcheck_requested = Signal()
    concordance_requested = Signal()
    xbench_qa_requested = Signal()
    advanced_filter_requested = Signal()
    project_settings_requested = Signal()
    slm_requested = Signal()
    slm_studio_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ReviewBar")
        self.setStyleSheet("""
            #ReviewBar {
                background-color: #202022;
                border-bottom: 1px solid #333333;
                padding: 4px;
            }
            QLabel {
                font-size: 11px;
                color: #aaaaaa;
            }
        """)

        self._pills: dict[str, ReviewFilterPill] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFixedHeight(38)

        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        # ---------------- Seção 1: Ações de Status (Trados Workflow)
        actions_label = QLabel("Revisão:")
        actions_label.setStyleSheet("font-weight: bold; color: #8eb4f3;")
        layout.addWidget(actions_label)

        # Confirm & Next (O botão mais importante de qualquer CAT tool)
        self.btn_confirm = QPushButton("✓ Confirmar & Próximo")
        self.btn_confirm.setToolTip("Grava, marca como Traduzido e avança (Ctrl+Enter)")
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.btn_confirm.clicked.connect(self.confirm_and_next_requested.emit)
        layout.addWidget(self.btn_confirm)

        # Approve
        self.btn_approve = QPushButton("🔒 Aprovar")
        self.btn_approve.setToolTip("Aprova o segmento como tradução final (Ctrl+Shift+A)")
        self.btn_approve.setStyleSheet("""
            QPushButton {
                background-color: #16a085;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1abc9c;
            }
        """)
        self.btn_approve.clicked.connect(lambda: self.status_change_requested.emit(SegState.APPROVED))
        layout.addWidget(self.btn_approve)

        # Reject
        self.btn_reject = QPushButton("✗ Rejeitar")
        self.btn_reject.setToolTip("Rejeita o segmento para correção (Ctrl+Shift+R)")
        self.btn_reject.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #e74c3c;
            }
        """)
        self.btn_reject.clicked.connect(lambda: self.status_change_requested.emit(SegState.REJECTED))
        layout.addWidget(self.btn_reject)

        # Draft
        self.btn_draft = QPushButton("✎ Rascunho")
        self.btn_draft.setToolTip("Marca como rascunho / pendente")
        self.btn_draft.setStyleSheet("""
            QPushButton {
                background-color: #d38600;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #f39c12;
            }
        """)
        self.btn_draft.clicked.connect(lambda: self.status_change_requested.emit(SegState.DRAFT))
        layout.addWidget(self.btn_draft)

        # Divisor
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setStyleSheet("color: #444444;")
        layout.addWidget(div)

        # ---------------- Seção 2: Filtros de Visualização
        filter_label = QLabel("Filtrar:")
        filter_label.setStyleSheet("color: #888888; font-weight: bold;")
        layout.addWidget(filter_label)

        self.pill_group = QButtonGroup(self)
        self.pill_group.setExclusive(True)

        filter_specs = [
            ("Todos", "all", "#007acc"),
            ("Não Traduzidos", "untranslated", "#7f8c8d"),
            ("Rascunho", "draft", "#f39c12"),
            ("Traduzidos", "translated", "#27ae60"),
            ("Aprovados", "approved", "#16a085"),
            ("Rejeitados", "rejected", "#c0392b"),
        ]

        for text, key, color in filter_specs:
            pill = ReviewFilterPill(text, key, color)
            pill.clicked.connect(self._on_pill_clicked)
            self.pill_group.addButton(pill)
            self._pills[key] = pill
            layout.addWidget(pill)

        self._pills["all"].setChecked(True)
        self._pills["all"]._update_appearance()

        layout.addStretch()

        # ---------------- Seção 3: Navegação Rápida
        self.btn_next_untrans = QPushButton("⏭ Próximo Pendente")
        self.btn_next_untrans.setToolTip("Pular para o próximo segmento não traduzido (Ctrl+Alt+Down)")
        self.btn_next_untrans.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #8eb4f3;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
                color: #ffffff;
            }
        """)
        self.btn_next_untrans.clicked.connect(self.next_untranslated_requested.emit)
        layout.addWidget(self.btn_next_untrans)

        # Concordance trigger
        self.btn_concordance = QPushButton("🔍 Concordância (F3)")
        self.btn_concordance.setToolTip("Buscar termo selecionado nas memórias de tradução (F3)")
        self.btn_concordance.setStyleSheet("""
            QPushButton {
                background-color: #333333;
                color: #ddd;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)
        self.btn_concordance.clicked.connect(self.concordance_requested.emit)
        layout.addWidget(self.btn_concordance)

        # Xbench QA trigger
        self.btn_xbench = QPushButton("🔎 Xbench QA")
        self.btn_xbench.setToolTip("Executar verificação de qualidade completa ApSIC Xbench")
        self.btn_xbench.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #f39c12;
                border: 1px solid #f39c12;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f39c12;
                color: #1e1e1e;
            }
        """)
        self.btn_xbench.clicked.connect(self.xbench_qa_requested.emit)
        layout.addWidget(self.btn_xbench)

        # Advanced Display Filter 2.0 trigger
        self.btn_adf = QPushButton("🔻 Filtro Avançado (F6)")
        self.btn_adf.setToolTip("Abrir/Fechar o Advanced Display Filter 2.0 (F6)")
        self.btn_adf.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #8eb4f3;
                border: 1px solid #007acc;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #007acc;
                color: #ffffff;
            }
        """)
        self.btn_adf.clicked.connect(self.advanced_filter_requested.emit)
        layout.addWidget(self.btn_adf)

        # Associar TM (Project Settings - Alt+F8)
        self.btn_tm_settings = QPushButton("⚙ Associar TM (Alt+F8)")
        self.btn_tm_settings.setToolTip("Associar memórias de tradução (.sdltm, .tmx) e configurar correspondências (Alt+F8)")
        self.btn_tm_settings.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f;
                color: #93c5fd;
                border: 1px solid #3b82f6;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563eb;
                color: #ffffff;
            }
        """)
        self.btn_tm_settings.clicked.connect(self.project_settings_requested.emit)
        layout.addWidget(self.btn_tm_settings)

        # Traduzir com SLM Local (Ollama)
        self.btn_slm = QPushButton("🤖 SLM (Ctrl+G)")
        self.btn_slm.setToolTip("Traduzir o segmento atual com a SLM Neural treinada (Ctrl+G)")
        self.btn_slm.setStyleSheet("""
            QPushButton {
                background-color: #2c3e50;
                color: #00a4e4;
                border: 1px solid #00a4e4;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00a4e4;
                color: white;
            }
        """)
        self.btn_slm.clicked.connect(self.slm_requested.emit)
        layout.addWidget(self.btn_slm)

        # Abrir SLM Studio
        self.btn_slm_studio = QPushButton("⚙ SLM Studio")
        self.btn_slm_studio.setToolTip("Abrir o estúdio de treino e gestão de SLMs a partir de memórias .sdltm")
        self.btn_slm_studio.setStyleSheet("""
            QPushButton {
                background-color: #252526;
                color: #a29bfe;
                border: 1px solid #6c5ce7;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6c5ce7;
                color: white;
            }
        """)
        self.btn_slm_studio.clicked.connect(self.slm_studio_requested.emit)
        layout.addWidget(self.btn_slm_studio)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def minimumSizeHint(self) -> QSize:
        return QSize(250, 38)

    def _on_pill_clicked(self) -> None:
        for key, pill in self._pills.items():
            pill._update_appearance()
            if pill.isChecked():
                self.filter_changed.emit(key)

    def update_counts(self, counts: dict[str, int]) -> None:
        """Atualiza a contagem dos badges de cada status."""
        total = sum(counts.values())
        if "all" in self._pills:
            self._pills["all"].set_count(total)
        for key, cnt in counts.items():
            if key in self._pills:
                self._pills[key].set_count(cnt)

    def set_filter(self, state_key: str) -> None:
        """Ativa programaticamente um filtro específico."""
        if state_key in self._pills:
            self._pills[state_key].setChecked(True)
            self._on_pill_clicked()

