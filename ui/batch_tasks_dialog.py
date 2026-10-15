"""
ui.batch_tasks_dialog - Diálogo de Tarefas em Lote estilo SDL Trados Studio (Batch Tasks Wizard).

Permite executar:
- Analyze Files: Contagem de palavras, repetições e correspondências de TM.
- Pre-translate Files: Tradução automática contra a memória local e memórias anexadas (.sdltm).
- Verify Files: Verificação de qualidade (QA) estilo ApSIC Xbench em lote.
- Update Main Translation Memories: Consolidação de segmentos aprovados na memória .sdltm.
"""
from __future__ import annotations

import os
from typing import List, Optional
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QListWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QFrame,
    QMessageBox, QFileDialog, QSplitter, QTextEdit, QSpinBox,
    QCheckBox
)

from core.batch_tasks import BatchTaskEngine, BatchAnalysisReport
from core.project import Project
from core.slm import OllamaClient
from core.config import load_config


class BatchTasksDialog(QDialog):
    """Janela de execução de Tarefas em Lote (Trados Batch Tasks)."""

    def __init__(self, project: Optional[Project] = None, current_tm=None,
                 initial_task: str = "analyze", parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.tm = current_tm
        self.current_report: Optional[BatchAnalysisReport] = None

        self.setWindowTitle("Tarefas em Lote — SDL Trados Studio Batch Tasks")
        self.resize(850, 560)
        self._apply_dark_theme()
        self._build_ui()
        self._load_files()

        # Seleciona tarefa inicial
        idx = {"analyze": 0, "pretranslate": 1, "verify": 2, "update_tm": 3, "heal": 4}.get(initial_task, 0)
        self.task_combo.setCurrentIndex(idx)
        self._on_task_changed(idx)

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                font-size: 11px;
                color: #cccccc;
            }
            QComboBox {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QListWidget {
                background-color: #252526;
                color: #dddddd;
                border: 1px solid #333333;
                border-radius: 4px;
                font-size: 11px;
            }
            QTableWidget {
                background-color: #252526;
                gridline-color: #333333;
                selection-background-color: #094771;
                selection-color: white;
                font-size: 11px;
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

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Barra Superior: Escolha da Tarefa
        top_frame = QFrame()
        top_frame.setStyleSheet("background-color: #252526; border-radius: 4px; padding: 4px;")
        tl = QHBoxLayout(top_frame)
        tl.setContentsMargins(8, 6, 8, 6)

        tl.addWidget(QLabel("Tarefa em Lote:"))
        self.task_combo = QComboBox()
        self.task_combo.addItems([
            "📊 Analyze Files (Análise de Palavras & TM)",
            "⚡ Pre-translate Files (Pré-tradução Automática)",
            "🔎 Verify Files (Auditoria de QA em Lote)",
            "💾 Update Main Translation Memories (Atualizar .sdltm)",
            "🔧 Auto-heal Broken Segmentation (Corrigir Quebras Indevidas)"
        ])
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        tl.addWidget(self.task_combo)

        tl.addStretch()
        layout.addWidget(top_frame)

        # Splitter Central: Lista de Ficheiros à esquerda, Opções e Resultados à direita
        splitter = QSplitter(Qt.Horizontal)

        # Painel Esquerdo: Ficheiros do Projeto
        left_widget = QFrame()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.addWidget(QLabel("Ficheiros Selecionados:"))

        self.file_list = QListWidget()
        left_layout.addWidget(self.file_list)

        btn_box = QHBoxLayout()
        btn_sel_all = QPushButton("Todos")
        btn_sel_all.clicked.connect(self._select_all_files)
        btn_sel_none = QPushButton("Nenhum")
        btn_sel_none.clicked.connect(self._deselect_all_files)
        btn_box.addWidget(btn_sel_all)
        btn_box.addWidget(btn_sel_none)
        left_layout.addLayout(btn_box)

        splitter.addWidget(left_widget)

        # Painel Direito: Descrição, Opções e Tabela de Resultados
        right_widget = QFrame()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)

        self.task_desc_lbl = QLabel()
        self.task_desc_lbl.setStyleSheet("color: #8eb4f3; font-size: 11px; margin-bottom: 4px;")
        right_layout.addWidget(self.task_desc_lbl)

        # Opções específicas da tarefa
        self.options_frame = QFrame()
        self.options_frame.setStyleSheet("background-color: #202022; border-radius: 4px; padding: 4px;")
        self.opt_layout = QHBoxLayout(self.options_frame)
        self.opt_layout.setContentsMargins(6, 4, 6, 4)

        self.chk_confirm = QCheckBox("Confirmar segmentos 100%")
        self.chk_confirm.setChecked(True)
        self.chk_confirm.setStyleSheet("color: #ccc; font-size: 11px;")
        self.opt_layout.addWidget(self.chk_confirm)

        self.chk_use_slm = QCheckBox("🤖 Usar SLM (Ollama) para novos/fuzzy")
        self.chk_use_slm.setToolTip("Gera traduções neurais especializadas para segmentos sem correspondência 100% de TM")
        self.chk_use_slm.setStyleSheet("color: #00a4e4; font-size: 11px; font-weight: bold;")
        self.opt_layout.addWidget(self.chk_use_slm)

        self.combo_slm_model = QComboBox()
        self.combo_slm_model.setToolTip("Modelo SLM a utilizar na pré-tradução")
        self.combo_slm_model.setStyleSheet("""
            QComboBox {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 11px;
                min-width: 140px;
            }
        """)
        self.opt_layout.addWidget(self.combo_slm_model)
        self._populate_slm_models()

        self.opt_layout.addStretch()
        right_layout.addWidget(self.options_frame)

        # Tabela de Resultados / Relatório
        self.table_report = QTableWidget()
        self.table_report.setColumnCount(8)
        self.table_report.setHorizontalHeaderLabels([
            "Ficheiro", "Segmentos", "Palavras", "Repetições", "100% Matches", "Fuzzy", "Novo", "Aproveitamento"
        ])
        self.table_report.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 8):
            self.table_report.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        right_layout.addWidget(self.table_report)

        # Log ou Mensagem textual
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet("background-color: #181818; color: #8eb4f3; border: 1px solid #333;")
        self.log_edit.setVisible(False)
        right_layout.addWidget(self.log_edit)

        splitter.addWidget(right_widget)
        splitter.setSizes([260, 560])
        layout.addWidget(splitter)

        # Barra de Progresso
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: #333; border-radius: 4px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 4px; }
        """)
        layout.addWidget(self.progress_bar)

        # Barra Inferior de Ações
        bottom_box = QHBoxLayout()

        self.btn_export_html = QPushButton("🌐 Exportar Relatório HTML...")
        self.btn_export_html.setEnabled(False)
        self.btn_export_html.clicked.connect(self._export_html_report)
        bottom_box.addWidget(self.btn_export_html)

        bottom_box.addStretch()

        self.btn_run = QPushButton("▶ Executar Tarefa em Lote")
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #1c97ea;
            }
        """)
        self.btn_run.clicked.connect(self._execute_batch_task)
        bottom_box.addWidget(self.btn_run)

        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.accept)
        bottom_box.addWidget(btn_close)

        layout.addLayout(bottom_box)

    def _load_files(self) -> None:
        self.file_list.clear()
        if self.project and self.project.files:
            for f in self.project.files:
                item = QListWidgetItem(f"{os.path.basename(f.path)} ({f.file_type.upper()})")
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, f.path)
                self.file_list.addItem(item)
        elif self.tm and hasattr(self.tm, "db_path"):
            item = QListWidgetItem(os.path.basename(self.tm.db_path))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, self.tm.db_path)
            self.file_list.addItem(item)

    def _select_all_files(self) -> None:
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.Checked)

    def _deselect_all_files(self) -> None:
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.Unchecked)

    def _get_checked_files(self) -> List[str]:
        files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked:
                files.append(item.data(Qt.UserRole))
        return files

    def _on_task_changed(self, index: int) -> None:
        descriptions = [
            "Contagem detalhada de palavras, repetições internas e correspondências com a Memória de Tradução.",
            "Aplica automaticamente correspondências exatas da TM aos segmentos pendentes.",
            "Executa todas as verificações de controle de qualidade (QA ApSIC Xbench) em todos os ficheiros.",
            "Envia todas as traduções confirmadas e aprovadas para a memória de tradução principal (.sdltm).",
            "Detecta e recombina automaticamente segmentos quebrados por abreviações, decimais ou regras legadas do Trados."
        ]
        self.task_desc_lbl.setText(descriptions[index] if index < len(descriptions) else "")
        self.options_frame.setVisible(index == 1) # apenas pretranslate tem opções específicas
        self.table_report.setVisible(index == 0)
        self.log_edit.setVisible(index != 0)
        self.btn_export_html.setEnabled(index == 0 and self.current_report is not None)

    def _execute_batch_task(self) -> None:
        selected_files = self._get_checked_files()
        if not selected_files:
            QMessageBox.warning(self, "Aviso", "Selecione pelo menos um ficheiro para processar.")
            return

        task_idx = self.task_combo.currentIndex()
        self.progress_bar.setRange(0, 0) # Indeterminate

        try:
            if task_idx == 0:
                self._run_analyze(selected_files)
            elif task_idx == 1:
                self._run_pretranslate(selected_files)
            elif task_idx == 2:
                self._run_verify(selected_files)
            elif task_idx == 3:
                self._run_update_tm(selected_files)
            elif task_idx == 4:
                self._run_heal(selected_files)
        finally:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)

    def _run_analyze(self, files: List[str]) -> None:
        proj_name = self.project.name if self.project else "Ficheiros Ativos"
        src_lang = self.project.source_lang if self.project else "en-US"
        tgt_lang = self.project.target_lang if self.project else "pt-PT"

        report = BatchTaskEngine.analyze_project(
            project_name=proj_name,
            file_paths=files,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
            reference_tm=self.tm
        )
        self.current_report = report
        self.btn_export_html.setEnabled(True)

        # Preenche a tabela
        self.table_report.setRowCount(len(report.files) + 1)
        for row, f in enumerate(report.files):
            self.table_report.setItem(row, 0, QTableWidgetItem(f.file_name))
            self.table_report.setItem(row, 1, QTableWidgetItem(f"{f.total_segments:,}"))
            self.table_report.setItem(row, 2, QTableWidgetItem(f"{f.total_words:,}"))
            self.table_report.setItem(row, 3, QTableWidgetItem(f"{f.repetitions_words:,}"))
            self.table_report.setItem(row, 4, QTableWidgetItem(f"{f.match_100_words:,}"))
            fuzzy = f.fuzzy_95_99_words + f.fuzzy_85_94_words + f.fuzzy_75_84_words
            self.table_report.setItem(row, 5, QTableWidgetItem(f"{fuzzy:,}"))
            new_item = QTableWidgetItem(f"{f.new_words:,}")
            new_item.setForeground(QColor(230, 126, 34))
            self.table_report.setItem(row, 6, new_item)
            lev_item = QTableWidgetItem(f"{f.leverage_percent:.1f}%")
            lev_item.setForeground(QColor(46, 204, 113))
            self.table_report.setItem(row, 7, lev_item)

        # Linha Total
        t_row = len(report.files)
        t = report.totals
        tot_label = QTableWidgetItem("TOTAL GERAL")
        tot_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        tot_label.setForeground(QColor(0, 122, 204))
        self.table_report.setItem(t_row, 0, tot_label)
        self.table_report.setItem(t_row, 1, QTableWidgetItem(f"{t.total_segments:,}"))
        self.table_report.setItem(t_row, 2, QTableWidgetItem(f"{t.total_words:,}"))
        self.table_report.setItem(t_row, 3, QTableWidgetItem(f"{t.repetitions_words:,}"))
        self.table_report.setItem(t_row, 4, QTableWidgetItem(f"{t.match_100_words:,}"))
        t_fuzzy = t.fuzzy_95_99_words + t.fuzzy_85_94_words + t.fuzzy_75_84_words
        self.table_report.setItem(t_row, 5, QTableWidgetItem(f"{t_fuzzy:,}"))
        t_new = QTableWidgetItem(f"{t.new_words:,}")
        t_new.setFont(QFont("Segoe UI", 9, QFont.Bold))
        t_new.setForeground(QColor(230, 126, 34))
        self.table_report.setItem(t_row, 6, t_new)
        t_lev = QTableWidgetItem(f"{t.leverage_percent:.1f}%")
        t_lev.setFont(QFont("Segoe UI", 9, QFont.Bold))
        t_lev.setForeground(QColor(46, 204, 113))
        self.table_report.setItem(t_row, 7, t_lev)

    def _populate_slm_models(self) -> None:
        """Carrega os modelos locais disponíveis no Ollama."""
        self.combo_slm_model.clear()
        client = OllamaClient()
        if client.is_available():
            models = client.list_models()
            cfg_model = getattr(load_config(), "ollama_model", "toyotao:latest")
            target_idx = 0
            for idx, m in enumerate(models):
                self.combo_slm_model.addItem(m)
                if m == cfg_model or "toyotao" in m:
                    target_idx = idx
            if models:
                self.combo_slm_model.setCurrentIndex(target_idx)
        else:
            self.combo_slm_model.addItem("toyotao:latest")

    def _run_pretranslate(self, files: List[str]) -> None:
        if not self.tm:
            QMessageBox.warning(self, "Aviso", "Nenhuma base de memória (TM) carregada para pré-tradução.")
            return

        use_slm = self.chk_use_slm.isChecked()
        slm_model = self.combo_slm_model.currentText()
        total_pretranslated = 0
        log_lines = ["=== EXECUÇÃO: PRE-TRANSLATE FILES ==="]
        if use_slm:
            log_lines.append(f"🤖 SLM Fallback Ativo: {slm_model}")

        for path in files:
            segs = BatchTaskEngine.extract_segments_from_file(path)
            cnt = BatchTaskEngine.pretranslate_segments(
                segments=segs,
                reference_tm=self.tm,
                confirm=self.chk_confirm.isChecked(),
                use_slm=use_slm,
                slm_model=slm_model
            )
            total_pretranslated += cnt
            extra_msg = f" (TM + SLM {slm_model})" if use_slm else " (TM 100%)"
            log_lines.append(f"• {os.path.basename(path)}: {cnt} segmento(s) pré-traduzido(s){extra_msg}")

        log_lines.append("--------------------------------------------------")
        log_lines.append(f"Total de segmentos pré-traduzidos: {total_pretranslated}")
        self.log_edit.setPlainText("\n".join(log_lines))

    def _run_verify(self, files: List[str]) -> None:
        issues = BatchTaskEngine.verify_project_files(files)
        log_lines = [
            f"=== EXECUÇÃO: VERIFY FILES (QA AUDIT) ===",
            f"Ficheiros verificados: {len(files)}",
            f"Total de problemas detectados: {len(issues)}",
            "--------------------------------------------------"
        ]
        if not issues:
            log_lines.append("✓ Parabéns! Nenhum erro de qualidade ou inconsistência detectado.")
        else:
            for iss in issues[:100]: # Limita log a 100
                log_lines.append(f"[{iss.severity.upper()}] {iss.file_name} #{iss.row_id}: {iss.issue_type} - {iss.description}")
            if len(issues) > 100:
                log_lines.append(f"... e mais {len(issues) - 100} problemas.")

        self.log_edit.setPlainText("\n".join(log_lines))

    def _run_update_tm(self, files: List[str]) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Selecionar Memória SDLTM Principal", "", "Trados SDLTM (*.sdltm)"
        )
        if not path:
            return

        all_segs = []
        for f in files:
            all_segs.extend(BatchTaskEngine.extract_segments_from_file(f))

        src_l = self.project.source_lang if self.project else "en-US"
        tgt_l = self.project.target_lang if self.project else "pt-PT"

        count = BatchTaskEngine.update_main_tm(all_segs, path, src_l, tgt_l)
        self.log_edit.setPlainText(
            f"=== EXECUÇÃO: UPDATE MAIN TRANSLATION MEMORIES ===\n"
            f"Memória de destino: {path}\n"
            f"Segmentos confirmados gravados: {count:,}\n"
            f"Base de memória nativa SDL Trados Studio atualizada com sucesso!"
        )

    def _run_heal(self, files: List[str]) -> None:
        total, details = BatchTaskEngine.heal_segmentation_for_files(files, current_tm=self.tm)
        log_lines = [
            "=== EXECUÇÃO: AUTO-HEAL BROKEN SEGMENTATION ===",
            "Motor: Smart Multilingual Sentence Segmenter",
            f"Ficheiros processados: {len(files)}",
            f"Total de quebras indevidas recombinadas: {total}",
            "--------------------------------------------------"
        ]
        log_lines.extend([f"• {d}" for d in details])
        if total == 0:
            log_lines.append("\n✓ A segmentação está íntegra. Nenhuma quebra indevida foi encontrada.")
        else:
            log_lines.append(f"\n✓ Sucesso! {total} fragmentos de sentenças foram unificados com perfeição.")
        self.log_edit.setPlainText("\n".join(log_lines))

    def _export_html_report(self) -> None:
        if not self.current_report:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Relatório de Análise", "AnalysisReport.html", "HTML (*.html)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.current_report.to_html())
            QMessageBox.information(self, "Exportação", f"Relatório salvo com sucesso:\n{path}")

