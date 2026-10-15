"""
ui.xbench_dialog - Janela Interativa de Resultados de QA estilo ApSIC Xbench para Trados Studio.

Funcionalidades:
- Execução de QA com diagnóstico completo de erros, avisos e inconsistências
- Filtro por Tipo de Erro e Severidade
- Tabela interativa com badges de status
- Navegação direta para o segmento no Editor ao clicar duas vezes
- Exportação de relatório de QA em formato HTML e TXT
"""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QFrame, QMessageBox, QFileDialog, QSplitter
)

from core.xbench_qa import QAIssue, XbenchQAEngine
from core.segment import Segment


class XbenchQADialog(QDialog):
    """Janela de QA estilo ApSIC Xbench."""

    jump_to_segment_requested = Signal(int)  # row_index to select in editor

    def __init__(self, segments: List[Segment], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ApSIC Xbench QA — Verificação de Qualidade e Inconsistências")
        self.resize(1100, 650)
        self.engine = XbenchQAEngine()
        self.segments = segments
        self.all_issues: List[QAIssue] = []
        self.filtered_issues: List[QAIssue] = []

        self._build_ui()
        self.run_qa()

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
            QTableWidget {
                background-color: #252526;
                gridline-color: #333333;
                selection-background-color: #094771;
                selection-color: white;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #2d2d30;
                color: #8eb4f3;
                padding: 5px;
                border: none;
                border-bottom: 1px solid #3e3e42;
                font-weight: bold;
                font-size: 11px;
            }
            QComboBox {
                background-color: #2d2d30;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header bar
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #252526; border-radius: 6px; padding: 6px;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 4, 8, 4)

        title_lbl = QLabel("ApSIC Xbench QA Verification")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #8eb4f3;")
        header_layout.addWidget(title_lbl)

        self.stats_lbl = QLabel("0 problemas detectados")
        self.stats_lbl.setStyleSheet("font-weight: bold; color: #f39c12; margin-left: 12px;")
        header_layout.addWidget(self.stats_lbl)

        header_layout.addStretch()

        btn_rerun = QPushButton("🔄 Re-executar QA")
        btn_rerun.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        btn_rerun.clicked.connect(self.run_qa)
        header_layout.addWidget(btn_rerun)

        btn_export = QPushButton("📄 Exportar Relatório")
        btn_export.clicked.connect(self._export_report)
        header_layout.addWidget(btn_export)

        layout.addWidget(header_frame)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Filtrar por Severidade:"))
        self.combo_sev = QComboBox()
        self.combo_sev.addItems(["Todas", "Apenas Erros", "Avisos & Erros", "Apenas Informações"])
        self.combo_sev.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.combo_sev)

        filter_bar.addWidget(QLabel("Filtrar por Tipo de Problema:"))
        self.combo_type = QComboBox()
        self.combo_type.addItems(["Todos os Tipos"])
        self.combo_type.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self.combo_type, stretch=1)

        layout.addLayout(filter_bar)

        # Issues Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Nº", "Severidade", "Tipo de Problema", "Descrição", "Texto Fonte", "Texto Tradução"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table)

        # Bottom navigation
        bottom_bar = QHBoxLayout()
        hint = QLabel("💡 Dica: Dê duplo clique em qualquer linha para saltar diretamente para o segmento no Editor.")
        hint.setStyleSheet("color: #888888; font-style: italic;")
        bottom_bar.addWidget(hint)
        bottom_bar.addStretch()

        btn_jump = QPushButton("Ir para o Segmento ➔")
        btn_jump.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 6px 16px;")
        btn_jump.clicked.connect(self._jump_selected)
        bottom_bar.addWidget(btn_jump)

        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

    def set_segments(self, segments: List[Segment]) -> None:
        self.segments = segments
        self.run_qa()

    def run_qa(self) -> None:
        """Executa a verificação completa com o motor Xbench."""
        self.all_issues = self.engine.run_qa(self.segments)
        
        # Atualiza combo de tipos
        current_types = sorted({issue.issue_type for issue in self.all_issues})
        self.combo_type.blockSignals(True)
        self.combo_type.clear()
        self.combo_type.addItem("Todos os Tipos")
        for t in current_types:
            self.combo_type.addItem(t)
        self.combo_type.blockSignals(False)

        self._apply_filter()

    def _apply_filter(self) -> None:
        sev_choice = self.combo_sev.currentText()
        type_choice = self.combo_type.currentText()

        self.filtered_issues = []
        for issue in self.all_issues:
            if sev_choice == "Apenas Erros" and issue.severity != "Error":
                continue
            if sev_choice == "Avisos & Erros" and issue.severity not in ("Error", "Warning"):
                continue
            if sev_choice == "Apenas Informações" and issue.severity != "Info":
                continue

            if type_choice != "Todos os Tipos" and issue.issue_type != type_choice:
                continue

            self.filtered_issues.append(issue)

        self._update_table()

    def _update_table(self) -> None:
        self.table.setRowCount(len(self.filtered_issues))
        error_count = sum(1 for i in self.all_issues if i.severity == "Error")
        warning_count = sum(1 for i in self.all_issues if i.severity == "Warning")
        self.stats_lbl.setText(f"{len(self.all_issues)} problemas encontrados ({error_count} erros, {warning_count} avisos)")

        for row, issue in enumerate(self.filtered_issues):
            item_num = QTableWidgetItem(str(issue.row_index + 1))
            item_num.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_num)

            # Severidade com badge colorido
            item_sev = QTableWidgetItem(f"● {issue.severity}")
            item_sev.setTextAlignment(Qt.AlignCenter)
            if issue.severity == "Error":
                item_sev.setForeground(QColor(231, 76, 60))
            elif issue.severity == "Warning":
                item_sev.setForeground(QColor(243, 156, 18))
            else:
                item_sev.setForeground(QColor(52, 152, 219))
            self.table.setItem(row, 1, item_sev)

            item_type = QTableWidgetItem(issue.issue_type)
            item_type.setForeground(QColor(142, 180, 243))
            self.table.setItem(row, 2, item_type)

            self.table.setItem(row, 3, QTableWidgetItem(issue.description))
            self.table.setItem(row, 4, QTableWidgetItem(issue.source))
            self.table.setItem(row, 5, QTableWidgetItem(issue.target))

    def _on_row_double_clicked(self, row: int, column: int) -> None:
        if 0 <= row < len(self.filtered_issues):
            issue = self.filtered_issues[row]
            self.jump_to_segment_requested.emit(issue.row_index)
            self.accept()

    def _jump_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.filtered_issues):
            self._on_row_double_clicked(row, 0)
        else:
            QMessageBox.information(self, "Navegação", "Selecione uma linha da tabela para saltar para o segmento correspondente.")

    def _export_report(self) -> None:
        if not self.all_issues:
            QMessageBox.information(self, "Exportar Relatório", "Nenhum problema encontrado para exportar.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Relatório de QA ApSIC Xbench",
            "xbench_qa_report.html",
            "Relatório HTML (*.html);;Ficheiro de Texto (*.txt)"
        )
        if not path:
            return

        if path.endswith(".html"):
            html = [
                "<!DOCTYPE html><html><head><meta charset='utf-8'>",
                "<title>Relatório de QA ApSIC Xbench</title>",
                "<style>",
                "body { font-family: Segoe UI, sans-serif; background: #fdfdfd; color: #222; margin: 20px; }",
                "h1 { color: #007acc; }",
                "table { width: 100%; border-collapse: collapse; margin-top: 15px; }",
                "th, td { border: 1px solid #ccc; padding: 8px; text-align: left; font-size: 13px; }",
                "th { background: #f0f4f8; color: #007acc; }",
                ".error { color: #d9534f; font-weight: bold; }",
                ".warning { color: #f0ad4e; font-weight: bold; }",
                ".info { color: #5bc0de; }",
                "</style></head><body>",
                "<h1>Relatório de QA ApSIC Xbench</h1>",
                f"<p>Total de problemas: <strong>{len(self.all_issues)}</strong></p>",
                "<table><tr><th>Nº</th><th>Severidade</th><th>Tipo</th><th>Descrição</th><th>Fonte</th><th>Tradução</th></tr>",
            ]
            for issue in self.all_issues:
                cls = issue.severity.lower()
                html.append(f"<tr><td>{issue.row_index + 1}</td><td class='{cls}'>{issue.severity}</td><td>{issue.issue_type}</td><td>{issue.description}</td><td>{issue.source}</td><td>{issue.target}</td></tr>")
            html.append("</table></body></html>")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(html))
        else:
            lines = [f"=== Relatório de QA ApSIC Xbench ({len(self.all_issues)} ocorrências) ===\n"]
            for issue in self.all_issues:
                lines.append(f"[{issue.severity.upper()}] Seg {issue.row_index + 1} | {issue.issue_type}")
                lines.append(f"  Descrição: {issue.description}")
                lines.append(f"  Fonte:     {issue.source}")
                lines.append(f"  Tradução:  {issue.target}\n")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

        QMessageBox.information(self, "Relatório Exportado", f"Relatório gravado com sucesso em:\n{path}")

