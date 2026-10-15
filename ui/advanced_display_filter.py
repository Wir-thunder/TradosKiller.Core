"""
ui.advanced_display_filter - Painel Advanced Display Filter 2.0 fiel ao SDL Trados Studio.

Interface:
- Barra de Ações: Apply Filter, Reverse, Clear, Highlight, Generate, Save.
- Abas: Filter Attributes (padrão ativa), Content, Comments & Tags, Document Structure.
- Dual-list: Available / Selected com botões >, <, << e Operator (AND / OR).
- Faixa de Fuzzy Matches.
- Caixa "Filters applied:" e contador "Filtered X of Y segments".
"""
from __future__ import annotations

import json
from typing import Set, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QFrame, QTabWidget,
    QSpinBox, QGroupBox, QListWidget, QListWidgetItem,
    QTextEdit, QMessageBox, QFileDialog
)

from core.advanced_filter import AdvancedFilterCriteria
from core.segment import SegState


# Itens padrão de atributos disponíveis no Trados Studio ADF 2.0
AVAILABLE_ATTRIBUTES = [
    # Status
    "Not Translated",
    "Draft",
    "Translated",
    "Translation Rejected",
    "Translation Approved",
    "Sign-off Rejected",
    "Signed Off",
    # Separador / Grupo Origem
    "── Origin ──",
    "SDL PerfectMatch",
    "Context matches",
    "Neural Machine Translation",
    "Automated translations",
    "100% matches"
]

STATUS_NAME_MAP = {
    "not translated": SegState.UNTRANSLATED.value,
    "draft": SegState.DRAFT.value,
    "translated": SegState.TRANSLATED.value,
    "translation rejected": SegState.REJECTED.value,
    "translation approved": SegState.APPROVED.value,
    "sign-off rejected": SegState.REJECTED.value,
    "signed off": SegState.APPROVED.value,
}


class AdvancedDisplayFilterPanel(QFrame):
    """Painel expansível do Advanced Display Filter 2.0 estilo SDL Trados Studio."""

    filter_applied = Signal(object)   # AdvancedFilterCriteria
    filter_reversed = Signal(object)  # AdvancedFilterCriteria (reverse=True)
    filter_cleared = Signal()
    generate_requested = Signal()     # Disparado ao clicar em Generate
    save_requested = Signal()         # Disparado ao salvar preset

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AdvancedDisplayFilterPanel")
        self._is_reversed = False
        self._apply_dark_theme()
        self._build_ui()
        self._load_available_attributes()
        self._update_filters_applied_text()

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            #AdvancedDisplayFilterPanel {
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 4px;
            }
            QLabel {
                color: #cccccc;
                font-size: 11px;
            }
            QLineEdit, QTextEdit {
                background-color: #1e1e1e;
                color: #f1f1f1;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                padding: 4px 6px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #007acc;
            }
            QComboBox {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 11px;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 3px 6px;
            }
            QListWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QCheckBox {
                color: #e0e0e0;
                font-size: 11px;
                spacing: 5px;
            }
            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #1e1e1e;
                border-radius: 3px;
            }
            QTabBar::tab {
                background: #2d2d30;
                color: #cccccc;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1e1e1e;
                color: #8eb4f3;
                border-bottom: 2px solid #007acc;
            }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QGroupBox {
                color: #8eb4f3;
                font-size: 11px;
                font-weight: bold;
                border: 1px solid #383838;
                border-radius: 3px;
                margin-top: 6px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
            }
        """)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # ---------------- Barra Superior com Ações Estilo Trados Studio ADF 2.0
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        title_lbl = QLabel("Advanced Display Filter 2.0")
        title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #8eb4f3; margin-right: 8px;")
        top_bar.addWidget(title_lbl)

        # 1. Apply Filter
        self.btn_apply = QPushButton("✔ Apply Filter")
        self.btn_apply.setToolTip("Aplica todos os critérios selecionados à tabela de segmentos (Enter)")
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)
        self.btn_apply.clicked.connect(self.apply_filter)
        top_bar.addWidget(self.btn_apply)

        # 2. Reverse
        self.btn_reverse = QPushButton("🔁 Reverse")
        self.btn_reverse.setToolTip("Inverte a exibição (exibe todos os segmentos EXCETO os filtrados)")
        self.btn_reverse.clicked.connect(self.toggle_reverse)
        top_bar.addWidget(self.btn_reverse)

        # 3. Clear
        self.btn_clear = QPushButton("✖ Clear")
        self.btn_clear.setToolTip("Limpa todos os filtros ativos e restaura a visão original")
        self.btn_clear.clicked.connect(self.clear_filter)
        top_bar.addWidget(self.btn_clear)

        # 4. Highlight
        self.btn_highlight = QPushButton("Highlight ▾")
        self.btn_highlight.setToolTip("Destaca visualmente os termos correspondentes na tabela")
        top_bar.addWidget(self.btn_highlight)

        # 5. Generate (Trados ADF 2.0 Generate)
        self.btn_generate = QPushButton("📑 Generate")
        self.btn_generate.setToolTip("Gera / Exporta um novo ficheiro (SDLXLIFF, TMX, Excel CSV, SDLTM) com os segmentos filtrados")
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.btn_generate.clicked.connect(self.generate_requested.emit)
        top_bar.addWidget(self.btn_generate)

        # 6. Save Configuration
        self.btn_save = QPushButton("💾 Save")
        self.btn_save.setToolTip("Salva as configurações de filtro atuais (.sdladfsettings / JSON)")
        self.btn_save.clicked.connect(self._save_settings)
        top_bar.addWidget(self.btn_save)

        top_bar.addStretch()

        self.btn_toggle_collapse = QPushButton("▲ Recolher")
        self.btn_toggle_collapse.clicked.connect(self._toggle_collapse)
        top_bar.addWidget(self.btn_toggle_collapse)

        layout.addLayout(top_bar)

        # ---------------- Abas do Filtro
        self.tabs = QTabWidget()

        # Tab 1: Filter Attributes (Prioritária / Aberta por padrão conforme solicitação)
        self._build_attributes_tab()

        # Tab 2: Content (Fonte e Tradução)
        self._build_content_tab()

        # Tab 3: Comments & Tags
        self._build_tags_tab()

        # Tab 4: Document Structure
        self._build_structure_tab()

        layout.addWidget(self.tabs)

        # ---------------- Seção Inferior: Filters applied & Status
        bot_box = QVBoxLayout()
        bot_box.setSpacing(4)

        bot_box.addWidget(QLabel("Filters applied:"))
        self.txt_filters_applied = QLineEdit()
        self.txt_filters_applied.setReadOnly(True)
        self.txt_filters_applied.setStyleSheet("background-color: #1a1a1a; color: #8eb4f3; font-style: italic;")
        bot_box.addWidget(self.txt_filters_applied)

        self.match_count_lbl = QLabel("Filtered 0 of 0 segments")
        self.match_count_lbl.setStyleSheet("color: #888888; font-size: 11px; margin-top: 2px;")
        bot_box.addWidget(self.match_count_lbl)

        layout.addLayout(bot_box)

    # ------------------------------------------------------------- Aba 1: Filter Attributes
    def _build_attributes_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        desc_lbl = QLabel("Select what attributes to apply to the filter:")
        desc_lbl.setStyleSheet("color: #cccccc; margin-bottom: 2px;")
        layout.addWidget(desc_lbl)

        # Dual List: Available | [ > < << ] | Selected
        dual_layout = QHBoxLayout()
        dual_layout.setSpacing(8)

        # Coluna Esquerda: Available
        left_v = QVBoxLayout()
        left_v.addWidget(QLabel("Available:"))
        self.list_available = QListWidget()
        self.list_available.itemDoubleClicked.connect(self._on_available_double_clicked)
        left_v.addWidget(self.list_available)
        dual_layout.addLayout(left_v, stretch=2)

        # Botões Centrais de Transferência
        btn_v = QVBoxLayout()
        btn_v.addStretch()

        self.btn_add = QPushButton(">")
        self.btn_add.setToolTip("Adicionar atributo selecionado ao filtro")
        self.btn_add.setFixedWidth(36)
        self.btn_add.clicked.connect(self._add_selected_attribute)
        btn_v.addWidget(self.btn_add)

        self.btn_remove = QPushButton("<")
        self.btn_remove.setToolTip("Remover atributo selecionado")
        self.btn_remove.setFixedWidth(36)
        self.btn_remove.clicked.connect(self._remove_selected_attribute)
        btn_v.addWidget(self.btn_remove)

        self.btn_remove_all = QPushButton("<<")
        self.btn_remove_all.setToolTip("Limpar todos os atributos selecionados")
        self.btn_remove_all.setFixedWidth(36)
        self.btn_remove_all.clicked.connect(self._clear_selected_attributes)
        btn_v.addWidget(self.btn_remove_all)

        btn_v.addStretch()
        dual_layout.addLayout(btn_v, stretch=0)

        # Coluna Direita: Selected + Relationship
        right_v = QVBoxLayout()
        right_v.addWidget(QLabel("Selected:"))
        self.list_selected = QListWidget()
        self.list_selected.itemDoubleClicked.connect(self._on_selected_double_clicked)
        right_v.addWidget(self.list_selected)

        # Relationship Box
        grp_rel = QGroupBox("Relationship")
        rel_layout = QHBoxLayout(grp_rel)
        rel_layout.setContentsMargins(6, 6, 6, 6)
        rel_layout.addWidget(QLabel("Operator:"))
        self.op_combo = QComboBox()
        self.op_combo.addItems(["AND", "OR"])
        self.op_combo.currentTextChanged.connect(self._update_filters_applied_text)
        rel_layout.addWidget(self.op_combo)
        rel_layout.addStretch()
        right_v.addWidget(grp_rel)

        dual_layout.addLayout(right_v, stretch=2)
        layout.addLayout(dual_layout)

        # Fuzzy matches between [ min ] and [ max ]
        fuzzy_box = QHBoxLayout()
        self.chk_fuzzy = QCheckBox("Fuzzy matches between")
        self.chk_fuzzy.toggled.connect(self._update_filters_applied_text)
        fuzzy_box.addWidget(self.chk_fuzzy)

        self.spin_min = QSpinBox()
        self.spin_min.setRange(0, 100)
        self.spin_min.setValue(75)
        self.spin_min.valueChanged.connect(self._update_filters_applied_text)
        fuzzy_box.addWidget(self.spin_min)

        fuzzy_box.addWidget(QLabel("and"))

        self.spin_max = QSpinBox()
        self.spin_max.setRange(0, 100)
        self.spin_max.setValue(99)
        self.spin_max.valueChanged.connect(self._update_filters_applied_text)
        fuzzy_box.addWidget(self.spin_max)
        fuzzy_box.addWidget(QLabel("%"))

        fuzzy_box.addSpacing(16)
        btn_quick_100 = QPushButton("100% Matches")
        btn_quick_100.clicked.connect(lambda: self._set_percent_range(100, 100))
        btn_quick_fuzzy = QPushButton("Fuzzy 75-99%")
        btn_quick_fuzzy.clicked.connect(lambda: self._set_percent_range(75, 99))
        fuzzy_box.addWidget(btn_quick_100)
        fuzzy_box.addWidget(btn_quick_fuzzy)

        fuzzy_box.addStretch()
        layout.addLayout(fuzzy_box)

        self.tabs.addTab(tab, "Filter Attributes")

    # ------------------------------------------------------------- Aba 2: Content
    def _build_content_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        mode_options = [
            ("Contém", "contains"),
            ("Correspondência Exata", "exact"),
            ("Não Contém", "not_contains"),
            ("Começa com", "starts_with"),
            ("Termina com", "ends_with"),
            ("Expressão Regular (Regex)", "regex"),
        ]

        # Linha Fonte (Source)
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Texto Fonte:"), stretch=0)
        self.src_input = QLineEdit()
        self.src_input.setPlaceholderText("Buscar no segmento fonte...")
        self.src_input.textChanged.connect(self._update_filters_applied_text)
        self.src_input.returnPressed.connect(self.apply_filter)
        src_row.addWidget(self.src_input, stretch=3)

        self.src_mode_combo = QComboBox()
        for label, val in mode_options:
            self.src_mode_combo.addItem(label, val)
        src_row.addWidget(self.src_mode_combo, stretch=1)

        self.chk_src_case = QCheckBox("Aa (Case Sensitive)")
        src_row.addWidget(self.chk_src_case, stretch=0)
        layout.addLayout(src_row)

        # Linha Tradução (Target)
        tgt_row = QHBoxLayout()
        tgt_row.addWidget(QLabel("Tradução:   "), stretch=0)
        self.tgt_input = QLineEdit()
        self.tgt_input.setPlaceholderText("Buscar na tradução...")
        self.tgt_input.textChanged.connect(self._update_filters_applied_text)
        self.tgt_input.returnPressed.connect(self.apply_filter)
        tgt_row.addWidget(self.tgt_input, stretch=3)

        self.tgt_mode_combo = QComboBox()
        for label, val in mode_options:
            self.tgt_mode_combo.addItem(label, val)
        tgt_row.addWidget(self.tgt_mode_combo, stretch=1)

        self.chk_tgt_case = QCheckBox("Aa (Case Sensitive)")
        tgt_row.addWidget(self.chk_tgt_case, stretch=0)
        layout.addLayout(tgt_row)

        layout.addStretch()
        self.tabs.addTab(tab, "Content")

    # ------------------------------------------------------------- Aba 3: Comments & Tags
    def _build_tags_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.chk_with_tags = QCheckBox("Apenas segmentos com tags inline")
        self.chk_with_tags.toggled.connect(self._update_filters_applied_text)
        self.chk_without_tags = QCheckBox("Apenas segmentos sem tags")
        self.chk_without_tags.toggled.connect(self._update_filters_applied_text)
        self.chk_empty_target = QCheckBox("Apenas tradução vazia (não traduzidos)")
        self.chk_empty_target.toggled.connect(self._update_filters_applied_text)
        self.chk_same_as_source = QCheckBox("Tradução idêntica à fonte (não alterada)")
        self.chk_same_as_source.toggled.connect(self._update_filters_applied_text)

        layout.addWidget(self.chk_with_tags)
        layout.addWidget(self.chk_without_tags)
        layout.addWidget(self.chk_empty_target)
        layout.addWidget(self.chk_same_as_source)
        layout.addStretch()

        self.tabs.addTab(tab, "Comments & Tags")

    # ------------------------------------------------------------- Aba 4: Document Structure
    def _build_structure_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        lbl = QLabel("Filtrar por estrutura de documento (Parágrafos, Tabelas, Cabeçalhos):")
        layout.addWidget(lbl)
        self.chk_struct_body = QCheckBox("Corpo de Texto (Body / Paragraphs)")
        self.chk_struct_body.setChecked(True)
        self.chk_struct_header = QCheckBox("Cabeçalhos e Rodapés (Headers & Footers)")
        self.chk_struct_tables = QCheckBox("Células de Tabela (Tables)")
        layout.addWidget(self.chk_struct_body)
        layout.addWidget(self.chk_struct_header)
        layout.addWidget(self.chk_struct_tables)
        layout.addStretch()

        self.tabs.addTab(tab, "Document Structure")

    # ------------------------------------------------------------- Gerenciamento de Atributos
    def _load_available_attributes(self) -> None:
        self.list_available.clear()
        for attr in AVAILABLE_ATTRIBUTES:
            item = QListWidgetItem(attr)
            if attr.startswith("──"):
                item.setFlags(Qt.NoItemFlags)
                item.setForeground(QColor(140, 140, 140))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.list_available.addItem(item)

    def _on_available_double_clicked(self, item: QListWidgetItem) -> None:
        if item.text().startswith("──"):
            return
        self._add_attribute(item.text())

    def _on_selected_double_clicked(self, item: QListWidgetItem) -> None:
        row = self.list_selected.row(item)
        self.list_selected.takeItem(row)
        self._update_filters_applied_text()

    def _add_selected_attribute(self) -> None:
        item = self.list_available.currentItem()
        if item and not item.text().startswith("──"):
            self._add_attribute(item.text())

    def _add_attribute(self, text: str) -> None:
        existing = [self.list_selected.item(i).text() for i in range(self.list_selected.count())]
        if text not in existing:
            self.list_selected.addItem(text)
            self._update_filters_applied_text()

    def _remove_selected_attribute(self) -> None:
        row = self.list_selected.currentRow()
        if row >= 0:
            self.list_selected.takeItem(row)
            self._update_filters_applied_text()

    def _clear_selected_attributes(self) -> None:
        self.list_selected.clear()
        self._update_filters_applied_text()

    def _set_percent_range(self, min_val: int, max_val: int) -> None:
        self.chk_fuzzy.setChecked(True)
        self.spin_min.setValue(min_val)
        self.spin_max.setValue(max_val)
        self._update_filters_applied_text()

    def _toggle_collapse(self) -> None:
        is_visible = self.tabs.isVisible()
        self.tabs.setVisible(not is_visible)
        self.btn_toggle_collapse.setText("▼ Expandir" if is_visible else "▲ Recolher")

    # ------------------------------------------------------------- Critérios e Filtro
    def _update_filters_applied_text(self) -> None:
        parts: List[str] = []
        selected_attrs = [self.list_selected.item(i).text() for i in range(self.list_selected.count())]
        if selected_attrs:
            op = self.op_combo.currentText()
            parts.append(f"Attributes: ({f' {op} '.join(selected_attrs)})")

        if self.chk_fuzzy.isChecked():
            parts.append(f"Fuzzy: {self.spin_min.value()}% - {self.spin_max.value()}%")

        if self.src_input.text().strip():
            parts.append(f"Source: '{self.src_input.text().strip()}'")

        if self.tgt_input.text().strip():
            parts.append(f"Target: '{self.tgt_input.text().strip()}'")

        if self.chk_with_tags.isChecked():
            parts.append("Tags: Only with tags")
        elif self.chk_without_tags.isChecked():
            parts.append("Tags: Only without tags")

        if self.chk_empty_target.isChecked():
            parts.append("Target: Empty")
        if self.chk_same_as_source.isChecked():
            parts.append("Target == Source")

        prefix = "[REVERSE] " if self._is_reversed else ""
        txt = (prefix + " | ".join(parts)) if parts else (f"{prefix}None (All segments)" if self._is_reversed else "")
        self.txt_filters_applied.setText(txt)

    def get_criteria(self) -> AdvancedFilterCriteria:
        crit = AdvancedFilterCriteria()
        crit.operator = self.op_combo.currentText()
        crit.reverse = self._is_reversed

        # Statuses e Origins a partir da lista Selected
        for i in range(self.list_selected.count()):
            attr = self.list_selected.item(i).text()
            attr_lower = attr.lower()
            if attr_lower in STATUS_NAME_MAP:
                crit.statuses.add(STATUS_NAME_MAP[attr_lower])
            elif "perfectmatch" in attr_lower or "context" in attr_lower:
                crit.origins.add("tm")
            elif "neural" in attr_lower or "automated" in attr_lower:
                crit.origins.add("mt")
                crit.origins.add("auto")
            elif "100%" in attr_lower:
                crit.filter_by_percent = True
                crit.min_percent = 100
                crit.max_percent = 100

        # Faixa Fuzzy
        if self.chk_fuzzy.isChecked():
            crit.filter_by_percent = True
            crit.min_percent = self.spin_min.value()
            crit.max_percent = self.spin_max.value()

        # Texto Fonte & Alvo
        crit.source_text = self.src_input.text()
        crit.source_mode = self.src_mode_combo.currentData()
        crit.source_case = self.chk_src_case.isChecked()

        crit.target_text = self.tgt_input.text()
        crit.target_mode = self.tgt_mode_combo.currentData()
        crit.target_case = self.chk_tgt_case.isChecked()

        # Regras especiais
        crit.only_with_tags = self.chk_with_tags.isChecked()
        crit.only_without_tags = self.chk_without_tags.isChecked()
        crit.only_target_empty = self.chk_empty_target.isChecked()
        crit.only_target_equals_source = self.chk_same_as_source.isChecked()

        return crit

    def apply_filter(self) -> None:
        self._is_reversed = False
        self._update_filters_applied_text()
        crit = self.get_criteria()
        self.filter_applied.emit(crit)

    def toggle_reverse(self) -> None:
        """Inverte o filtro (Reverse): exibe todos os segmentos EXCETO os filtrados."""
        self._is_reversed = not self._is_reversed
        self._update_filters_applied_text()
        crit = self.get_criteria()
        crit.reverse = self._is_reversed
        self.filter_reversed.emit(crit)

    def clear_filter(self) -> None:
        self._is_reversed = False
        self.list_selected.clear()
        self.chk_fuzzy.setChecked(False)
        self.spin_min.setValue(75)
        self.spin_max.setValue(99)

        self.src_input.clear()
        self.tgt_input.clear()
        self.chk_src_case.setChecked(False)
        self.chk_tgt_case.setChecked(False)

        self.chk_with_tags.setChecked(False)
        self.chk_without_tags.setChecked(False)
        self.chk_empty_target.setChecked(False)
        self.chk_same_as_source.setChecked(False)

        self._update_filters_applied_text()
        self.match_count_lbl.setText("Filtered 0 of 0 segments")
        self.filter_cleared.emit()

    def update_match_count(self, matched: int, total: int) -> None:
        if matched == total:
            self.match_count_lbl.setText(f"Filtered {total:,} of {total:,} segments (100%)")
            self.match_count_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        else:
            pct = (matched / total * 100) if total > 0 else 0
            self.match_count_lbl.setText(f"Filtered {matched:,} of {total:,} segments ({pct:.1f}%)")
            self.match_count_lbl.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 11px;")

    def _save_settings(self) -> None:
        """Salva a configuração do filtro em ficheiro .sdladfsettings."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Configuração de Filtro", "CustomFilter.sdladfsettings",
            "Configurações ADF (*.sdladfsettings *.json)"
        )
        if not path:
            return

        crit = self.get_criteria()
        data = {
            "statuses": list(crit.statuses),
            "origins": list(crit.origins),
            "operator": crit.operator,
            "filter_by_percent": crit.filter_by_percent,
            "min_percent": crit.min_percent,
            "max_percent": crit.max_percent,
            "source_text": crit.source_text,
            "target_text": crit.target_text,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Salvar Filtro", f"Filtro salvo com sucesso:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível salvar o filtro:\n{e}")
