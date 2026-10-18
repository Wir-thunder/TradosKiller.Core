"""
ui.tm_utility_dialog - Utilitário de Gestão e Manutenção de Memórias de Tradução estilo Trados Studio.

Funcionalidades:
- Estatísticas detalhadas da TM (.sdltm, .tmx, sqlite): contagem de TUs, tamanho em disco, pares de idiomas
- Compactar & Otimizar (SQLite VACUUM para recuperar espaço em disco)
- Desduplicação (remoção de unidades de tradução duplicadas redundantes)
- Reconstrução de Índices e Pesquisa Textual FTS5 (Re-index)
- Localizar & Substituir em Massa em toda a Memória
- Verificação de Integridade de Banco de Dados (PRAGMA integrity_check)
- Importação e Exportação bilingue (.sdltm <-> .tmx)
"""
from __future__ import annotations

import os
import sqlite3
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QMessageBox, QFrame, QProgressBar,
    QGroupBox, QCheckBox, QTextEdit, QSplitter
)

from core.tm import TranslationMemory
from io_layer.sdltm import detect_sdltm_langs, iter_sdltm, write_sdltm
from io_layer.tmx import iter_tmx, detect_tmx_langs
from io_layer.tmx_writer import write_tmx


class TmManagementUtilityDialog(QDialog):
    """Utilitário de Gestão e Manutenção de Memórias de Tradução Trados."""

    tm_updated = Signal()

    def __init__(self, current_tm: Optional[TranslationMemory] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Translation Memory Management Utility")
        self.resize(850, 620)
        self.tm = current_tm
        self.active_db_path = current_tm.db_path if current_tm else ""

        self._build_ui()
        if self.active_db_path:
            self._refresh_tm_info()

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
                padding-top: 10px;
                font-weight: bold;
                color: #8eb4f3;
                font-size: 11px;
            }
            QLineEdit {
                background-color: #252526;
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
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QTextEdit {
                background-color: #181818;
                color: #b0b0b0;
                border: 1px solid #333333;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ---------------- Seletor de TM
        file_box = QGroupBox("Memória de Tradução Selecionada")
        file_layout = QHBoxLayout(file_box)
        file_layout.setContentsMargins(10, 10, 10, 10)

        self.path_edit = QLineEdit(self.active_db_path)
        self.path_edit.setPlaceholderText("Selecione um ficheiro .sdltm, .tmx ou base de dados de TM...")
        self.path_edit.setReadOnly(True)
        file_layout.addWidget(self.path_edit, stretch=1)

        btn_browse = QPushButton("Procurar TM...")
        btn_browse.clicked.connect(self._browse_tm)
        file_layout.addWidget(btn_browse)

        btn_new_tm = QPushButton("➕ Nova TM (.sdltm)...")
        btn_new_tm.setStyleSheet("background-color: #1e3a5f; color: #93c5fd; border: 1px solid #3b82f6; font-weight: bold;")
        btn_new_tm.clicked.connect(self._create_new_tm)
        file_layout.addWidget(btn_new_tm)

        layout.addWidget(file_box)

        # ---------------- Painel de Estatísticas
        self.stats_group = QGroupBox("Propriedades & Metadados da TM")
        stats_layout = QVBoxLayout(self.stats_group)
        stats_layout.setContentsMargins(10, 8, 10, 8)

        self.lbl_stats = QLabel("Nenhuma memória selecionada.")
        self.lbl_stats.setStyleSheet("color: #8eb4f3; font-size: 11px; font-weight: normal;")
        stats_layout.addWidget(self.lbl_stats)

        layout.addWidget(self.stats_group)

        # ---------------- Tarefas de Manutenção (Deduplicação, Compactação, Re-index)
        maint_group = QGroupBox("Operações de Manutenção & Limpeza")
        maint_layout = QVBoxLayout(maint_group)
        maint_layout.setContentsMargins(10, 10, 10, 10)
        maint_layout.setSpacing(8)

        btn_row1 = QHBoxLayout()

        btn_vacuum = QPushButton("🧹 Compactar & Otimizar (Vacuum)")
        btn_vacuum.setToolTip("Executa o VACUUM no SQLite para reduzir o tamanho do ficheiro e desfragmentar páginas.")
        btn_vacuum.clicked.connect(self._run_vacuum)
        btn_row1.addWidget(btn_vacuum)

        btn_dedup = QPushButton("✂ Remover Duplicados")
        btn_dedup.setToolTip("Localiza e elimina unidades de tradução idênticas, mantendo a mais recente.")
        btn_dedup.clicked.connect(self._run_dedup)
        btn_row1.addWidget(btn_dedup)

        btn_reindex = QPushButton("⚡ Reconstruir FTS & Índices")
        btn_reindex.setToolTip("Recria índices e o motor de pesquisa FTS5 para acelerar buscas de concordância.")
        btn_reindex.clicked.connect(self._run_reindex)
        btn_row1.addWidget(btn_reindex)

        btn_integrity = QPushButton("🛡 Teste de Integridade")
        btn_integrity.setToolTip("Verifica a consistência e detecta corrupção no banco de dados SQLite.")
        btn_integrity.clicked.connect(self._run_integrity_check)
        btn_row1.addWidget(btn_integrity)

        maint_layout.addLayout(btn_row1)
        layout.addWidget(maint_group)

        # ---------------- Localizar & Substituir na TM
        sr_group = QGroupBox("Localizar & Substituir em Massa na TM")
        sr_layout = QVBoxLayout(sr_group)
        sr_layout.setContentsMargins(10, 10, 10, 10)
        sr_layout.setSpacing(6)

        sr_inputs = QHBoxLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Localizar termo na TM...")
        sr_inputs.addWidget(self.find_edit)

        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Substituir por...")
        sr_inputs.addWidget(self.replace_edit)

        self.chk_target = QCheckBox("Tradução (Alvo)")
        self.chk_target.setChecked(True)
        sr_inputs.addWidget(self.chk_target)

        self.chk_case = QCheckBox("Diferenciar Maiúsculas")
        sr_inputs.addWidget(self.chk_case)

        btn_sr = QPushButton("Substituir na TM")
        btn_sr.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        btn_sr.clicked.connect(self._run_search_replace)
        sr_inputs.addWidget(btn_sr)

        sr_layout.addLayout(sr_inputs)
        layout.addWidget(sr_group)

        # ---------------- Log de Atividades
        layout.addWidget(QLabel("Registo de Atividades & Relatório de Execução:"))
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        layout.addWidget(self.log_edit, stretch=1)

        # Botão Fechar
        btn_close = QPushButton("Fechar Utilitário")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def _log(self, message: str) -> None:
        self.log_edit.append(message)

    def _create_new_tm(self) -> None:
        from ui.create_sdltm_dialog import CreateSdltmDialog
        dlg = CreateSdltmDialog(parent=self)
        if dlg.exec() and dlg.created_path:
            self.active_db_path = dlg.created_path
            self.path_edit.setText(dlg.created_path)
            self.tm = TranslationMemory(dlg.created_path)
            self._refresh_tm_info()
            self.tm_updated.emit()

    def _browse_tm(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir Memória de Tradução", "",
            "Memórias de Tradução (*.sdltm *.tmx *.db);;Memória SDLTM (*.sdltm);;TMX Standard (*.tmx);;Todos (*.*)"
        )
        if not path:
            return

        self.active_db_path = path
        self.path_edit.setText(path)

        # Se for .tmx ou .sdltm, podemos converter temporariamente ou associar
        ext = os.path.splitext(path)[1].lower()
        if ext in (".sdltm", ".db"):
            self.tm = TranslationMemory(path)
        else:
            # TMX
            src, tgt = detect_tmx_langs(path)
            temp_db = f"{os.path.splitext(path)[0]}.db"
            self.tm = TranslationMemory(temp_db)
            self.tm.add_many(iter_tmx(path, src, tgt), src or "", tgt or "")
            self.tm.rebuild_fts()

        self._refresh_tm_info()

    def _refresh_tm_info(self) -> None:
        if not self.active_db_path or not os.path.exists(self.active_db_path):
            self.lbl_stats.setText("Ficheiro não encontrado.")
            return

        size_kb = os.path.getsize(self.active_db_path) / 1024
        size_str = f"{size_kb / 1024:.2f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"

        tu_count = 0
        src_lang = "Desconhecido"
        tgt_lang = "Desconhecido"

        ext = os.path.splitext(self.active_db_path)[1].lower()
        if ext == ".sdltm":
            src_lang, tgt_lang = detect_sdltm_langs(self.active_db_path)
            try:
                conn = sqlite3.connect(f"file:{self.active_db_path}?mode=ro", uri=True)
                tu_count = conn.execute("SELECT count(*) FROM translation_units").fetchone()[0]
                conn.close()
            except Exception:
                pass
        elif self.tm:
            tu_count = self.tm.count()
            src_lang = getattr(self.tm, "srclang", "Multilíngue")
            tgt_lang = getattr(self.tm, "tgtlang", "Multilíngue")

        self.lbl_stats.setText(
            f"Ficheiro: {os.path.basename(self.active_db_path)}  |  "
            f"Tamanho em disco: {size_str}  |  "
            f"Total de Unidades de Tradução (TUs): {tu_count:,}  |  "
            f"Idiomas: {src_lang or 'N/A'} ➔ {tgt_lang or 'N/A'}"
        )
        self._log(f"Informações carregadas para: {os.path.basename(self.active_db_path)} ({tu_count} TUs, {size_str})")

    def _run_vacuum(self) -> None:
        """Executa VACUUM para recuperar espaço em disco."""
        if not self.active_db_path:
            QMessageBox.warning(self, "Aviso", "Nenhuma TM selecionada.")
            return

        size_before = os.path.getsize(self.active_db_path)
        try:
            conn = sqlite3.connect(self.active_db_path, check_same_thread=False)
            conn.execute("VACUUM")
            conn.close()
            size_after = os.path.getsize(self.active_db_path)
            diff_kb = (size_before - size_after) / 1024
            self._log(f"✔ [VACUUM Concluído] Espaço recuperado em disco: {diff_kb:.1f} KB")
            self._refresh_tm_info()
            QMessageBox.information(self, "Otimização Concluída", f"Memória compactada com sucesso!\nEspaço recuperado: {diff_kb:.1f} KB.")
        except Exception as e:
            self._log(f"❌ [Erro VACUUM] {e}")
            QMessageBox.critical(self, "Erro", f"Falha ao executar compactação:\n{e}")

    def _run_dedup(self) -> None:
        """Remove segmentos duplicados idênticos da base."""
        if not self.tm:
            QMessageBox.warning(self, "Aviso", "Abra ou selecione uma TM ativa.")
            return

        try:
            cur = self.tm.conn.cursor()
            # Identifica duplicados por source e target idênticos mantendo o de maior id
            cur.execute("""
                DELETE FROM segments
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM segments
                    GROUP BY source, target
                )
            """)
            deleted = cur.rowcount
            self.tm.conn.commit()
            self._log(f"✔ [Deduplicação Concluída] {deleted} unidades redundantes removidas.")
            self._refresh_tm_info()
            self.tm_updated.emit()
            QMessageBox.information(self, "Deduplicação", f"Limpeza concluída!\n{deleted} unidades duplicadas foram removidas.")
        except Exception as e:
            self._log(f"❌ [Erro Deduplicação] {e}")
            QMessageBox.critical(self, "Erro", f"Falha ao deduplicar:\n{e}")

    def _run_reindex(self) -> None:
        """Reconstrói os índices e a tabela virtual FTS5."""
        if not self.tm:
            QMessageBox.warning(self, "Aviso", "Abra ou selecione uma TM ativa.")
            return

        try:
            self.tm.rebuild_fts()
            self._log("✔ [Re-index Concluído] Índices e tabela FTS5 reconstruídos com sucesso.")
            QMessageBox.information(self, "Re-index", "Índices de pesquisa e concordância reconstruídos com sucesso!")
        except Exception as e:
            self._log(f"❌ [Erro Re-index] {e}")
            QMessageBox.critical(self, "Erro", f"Falha ao reconstruir índices:\n{e}")

    def _run_integrity_check(self) -> None:
        """Executa PRAGMA integrity_check no SQLite."""
        if not self.active_db_path:
            QMessageBox.warning(self, "Aviso", "Nenhuma TM selecionada.")
            return

        try:
            conn = sqlite3.connect(self.active_db_path, check_same_thread=False)
            res = conn.execute("PRAGMA integrity_check").fetchall()
            conn.close()
            status = "\n".join(row[0] for row in res)
            self._log(f"✔ [Integridade do Banco de Dados] Resultado:\n{status}")
            QMessageBox.information(self, "Teste de Integridade", f"Resultado do teste de integridade SQLite:\n{status}")
        except Exception as e:
            self._log(f"❌ [Erro Integridade] {e}")
            QMessageBox.critical(self, "Erro", f"Falha no teste de integridade:\n{e}")

    def _run_search_replace(self) -> None:
        """Localiza e substitui em massa na base da TM."""
        find_text = self.find_edit.text()
        replace_text = self.replace_edit.text()
        if not find_text:
            QMessageBox.warning(self, "Aviso", "Digite o texto a ser localizado.")
            return

        if not self.tm:
            QMessageBox.warning(self, "Aviso", "Nenhuma TM ativa selecionada.")
            return

        field = "target" if self.chk_target.isChecked() else "source"
        case = self.chk_case.isChecked()

        n = self.tm.bulk_replace(find=find_text, repl=replace_text, field=field,
                                 case_sensitive=case, use_regex=False)
        self._log(f"✔ [Substituição em Massa] '{find_text}' ➔ '{replace_text}' ({n} ocorrências no campo {field}).")
        self._refresh_tm_info()
        self.tm_updated.emit()
        QMessageBox.information(self, "Substituição na TM", f"{n} unidade(s) de tradução modificada(s) com sucesso na memória.")

