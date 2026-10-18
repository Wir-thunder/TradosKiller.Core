"""
ui.generate_filtered_dialog - Diálogo para gerar ficheiros a partir dos segmentos filtrados (ADF 2.0 Generate).

Permite ao tradutor exportar a seleção do Advanced Display Filter para:
- SDLXLIFF (*.sdlxliff): Ficheiro bilíngue nativo do SDL Trados Studio para terceirização ou sub-projeto.
- TMX (*.tmx): Memória de Tradução aberta (TMX 1.4b) com as unidades filtradas.
- CSV / Excel (*.csv): Tabela bilíngue formatada (UTF-8 com BOM) para revisão com cliente ou revisor externo.
- SDLTM (*.sdltm): Base de dados de memória de tradução nativa do Trados.
"""
from __future__ import annotations

import os
import csv
from typing import List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QLineEdit, QFileDialog,
    QCheckBox, QProgressBar, QMessageBox, QFrame, QGroupBox
)

from core.segment import Segment, display_text
from io_layer.sdlxliff_writer import write_sdlxliff
from io_layer.tmx_writer import write_tmx
from io_layer.sdltm import write_sdltm
from core.tm import TranslationMemory


class GenerateFilteredDialog(QDialog):
    """Janela de exportação / geração de ficheiro a partir de segmentos filtrados."""

    def __init__(self, segments: List[Segment], total_segments_count: int,
                 filter_summary: str = "", src_lang: str = "en-US", tgt_lang: str = "pt-PT",
                 source_file_name: str = "Document", parent=None) -> None:
        super().__init__(parent)
        self.segments = segments
        self.total_count = total_segments_count
        self.filter_summary = filter_summary or "Filtro Ativo"
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.source_file_name = source_file_name
        self.generated_path: Optional[str] = None

        self.setWindowTitle("Gerar Ficheiro a partir de Segmentos Filtrados (Generate)")
        self.resize(620, 480)
        self._apply_dark_theme()
        self._build_ui()
        self._update_default_path()

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
            QGroupBox {
                font-size: 11px;
                font-weight: bold;
                color: #8eb4f3;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QRadioButton {
                color: #dddddd;
                font-size: 11px;
                spacing: 6px;
                padding: 3px 0;
            }
            QLineEdit {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                padding: 5px 8px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
            }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 5px 14px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #444444;
            }
            QCheckBox {
                color: #cccccc;
                font-size: 11px;
                spacing: 6px;
            }
        """)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ---------------- Banner informativo de topo
        top_banner = QFrame()
        top_banner.setStyleSheet("background-color: #252526; border-radius: 4px; padding: 6px;")
        bv = QVBoxLayout(top_banner)
        bv.setContentsMargins(8, 6, 8, 6)
        bv.setSpacing(4)

        title_lbl = QLabel("📑 Gerar Ficheiro Filtrado — Advanced Display Filter 2.0")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #8eb4f3;")
        bv.addWidget(title_lbl)

        count_text = f"Segmentos filtrados: <b>{len(self.segments):,}</b> de <b>{self.total_count:,}</b>"
        pct = (len(self.segments) / self.total_count * 100) if self.total_count > 0 else 0
        count_lbl = QLabel(f"{count_text} ({pct:.1f}% do documento)")
        count_lbl.setStyleSheet("color: #2ecc71; font-size: 11px;")
        bv.addWidget(count_lbl)

        if self.filter_summary:
            f_lbl = QLabel(f"Filtro aplicado: <i>{self.filter_summary}</i>")
            f_lbl.setStyleSheet("color: #aaaaaa; font-size: 10px;")
            bv.addWidget(f_lbl)

        layout.addWidget(top_banner)

        # ---------------- Formato de Saída (Target Format)
        grp_format = QGroupBox("Formato de Exportação")
        fv = QVBoxLayout(grp_format)
        fv.setSpacing(6)

        self.btn_group = QButtonGroup(self)

        self.rb_sdlxliff = QRadioButton("📄 Ficheiro Bilíngue SDLXLIFF (*.sdlxliff)")
        self.rb_sdlxliff.setToolTip("Exporta um ficheiro bilíngue SDLXLIFF com os segmentos filtrados prontos para tradução")
        self.rb_sdlxliff.setChecked(True)
        self.btn_group.addButton(self.rb_sdlxliff, 0)
        fv.addWidget(self.rb_sdlxliff)

        self.rb_csv = QRadioButton("📊 Tabela de Revisão Bilíngue Excel / CSV (*.csv)")
        self.rb_csv.setToolTip("Exporta uma planilha com UTF-8 BOM que abre diretamente no Microsoft Excel (ideal para envio a clientes/revisores)")
        self.btn_group.addButton(self.rb_csv, 1)
        fv.addWidget(self.rb_csv)

        self.rb_tmx = QRadioButton("📚 Memória de Tradução TMX 1.4b (*.tmx)")
        self.rb_tmx.setToolTip("Exporta como base de memória TMX compatível com qualquer CAT Tool")
        self.btn_group.addButton(self.rb_tmx, 2)
        fv.addWidget(self.rb_tmx)

        self.rb_sdltm = QRadioButton("💾 Memória de Tradução SDLTM (*.sdltm)")
        self.rb_sdltm.setToolTip("Exporta diretamente para uma nova base de dados de memória SDLTM")
        self.btn_group.addButton(self.rb_sdltm, 3)
        fv.addWidget(self.rb_sdltm)

        self.btn_group.idClicked.connect(self._on_format_changed)
        layout.addWidget(grp_format)

        # ---------------- Caminho de Destino
        grp_dest = QGroupBox("Ficheiro de Destino")
        dv = QVBoxLayout(grp_dest)
        dv.setSpacing(6)

        path_box = QHBoxLayout()
        self.txt_path = QLineEdit()
        path_box.addWidget(self.txt_path, stretch=1)

        btn_browse = QPushButton("Procurar...")
        btn_browse.clicked.connect(self._browse_path)
        path_box.addWidget(btn_browse, stretch=0)
        dv.addLayout(path_box)

        self.chk_open_folder = QCheckBox("Abrir pasta de destino ao concluir a geração")
        self.chk_open_folder.setChecked(True)
        dv.addWidget(self.chk_open_folder)

        layout.addWidget(grp_dest)

        # ---------------- Barra de Progresso
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: #333; border-radius: 3px; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 3px; }
        """)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # ---------------- Barra Inferior de Ações
        bot_bar = QHBoxLayout()
        bot_bar.addStretch()

        self.btn_generate = QPushButton("▶ Gerar Ficheiro (Generate)")
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                font-weight: bold;
                padding: 6px 18px;
            }
            QPushButton:hover {
                background-color: #1c97ea;
            }
        """)
        self.btn_generate.clicked.connect(self._execute_generate)
        bot_bar.addWidget(self.btn_generate)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        bot_bar.addWidget(btn_cancel)

        layout.addLayout(bot_bar)

    def _on_format_changed(self, btn_id: int) -> None:
        self._update_default_path()

    def _update_default_path(self) -> None:
        base = os.path.splitext(self.source_file_name)[0] or "Filtered_Segments"
        folder = os.path.dirname(self.source_file_name) or os.path.expanduser("~/Documents")
        
        ext_map = {0: ".sdlxliff", 1: ".csv", 2: ".tmx", 3: ".sdltm"}
        fmt_id = self.btn_group.checkedId()
        ext = ext_map.get(fmt_id, ".sdlxliff")
        
        default_name = f"{base}_Filtered{ext}"
        self.txt_path.setText(os.path.join(folder, default_name))

    def _browse_path(self) -> None:
        fmt_id = self.btn_group.checkedId()
        if fmt_id == 0:
            filter_str = "Ficheiro SDLXLIFF (*.sdlxliff)"
        elif fmt_id == 1:
            filter_str = "Tabela CSV Excel (*.csv)"
        elif fmt_id == 2:
            filter_str = "Memória TMX (*.tmx)"
        else:
            filter_str = "Memória SDLTM (*.sdltm)"

        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Ficheiro Filtrado Como", self.txt_path.text(), filter_str
        )
        if path:
            self.txt_path.setText(path)

    def _execute_generate(self) -> None:
        out_path = self.txt_path.text().strip()
        if not out_path:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione o caminho de destino.")
            return

        if not self.segments:
            QMessageBox.warning(self, "Aviso", "Nenhum segmento corresponde ao filtro atual para exportar.")
            return

        self.progress_bar.setRange(0, 0)
        self.btn_generate.setEnabled(False)

        try:
            fmt_id = self.btn_group.checkedId()
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            if fmt_id == 0:
                # SDLXLIFF
                write_sdlxliff(
                    out_path=out_path,
                    src_lang=self.src_lang,
                    tgt_lang=self.tgt_lang,
                    original=os.path.basename(out_path),
                    segments=self.segments
                )
            elif fmt_id == 1:
                # CSV Excel com UTF-8-SIG (BOM)
                self._write_csv(out_path)
            elif fmt_id == 2:
                # TMX 1.4b
                write_tmx(
                    out_path=out_path,
                    src_lang=self.src_lang,
                    tgt_lang=self.tgt_lang,
                    segments=self.segments
                )
            elif fmt_id == 3:
                # SDLTM
                self._write_sdltm(out_path)

            self.generated_path = out_path
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Sucesso")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText(f"✓ Ficheiro gerado com sucesso!\n\nDestino: {out_path}\nTotal de segmentos exportados: {len(self.segments):,}")
            
            btn_open_file = msg_box.addButton("Abrir Ficheiro", QMessageBox.ActionRole)
            btn_open_dir = msg_box.addButton("Abrir Pasta", QMessageBox.ActionRole)
            btn_ok = msg_box.addButton("OK", QMessageBox.AcceptRole)

            msg_box.exec()

            if msg_box.clickedButton() == btn_open_file:
                try:
                    os.startfile(out_path)
                except Exception as e:
                    QMessageBox.warning(self, "Erro", f"Não foi possível abrir o ficheiro:\n{e}")
            elif msg_box.clickedButton() == btn_open_dir or self.chk_open_folder.isChecked():
                try:
                    os.startfile(os.path.dirname(out_path))
                except Exception:
                    pass

            self.accept()

        except Exception as ex:
            QMessageBox.critical(self, "Erro", f"Falha ao gerar ficheiro filtrado:\n{ex}")
        finally:
            self.progress_bar.setRange(0, 100)
            self.btn_generate.setEnabled(True)

    def _write_csv(self, out_path: str) -> None:
        """Escreve planilha bilíngue em CSV com BOM para abertura direta no Excel."""
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID", "Status", "Origem", "Match %",
                f"Fonte ({self.src_lang})", f"Tradução ({self.tgt_lang})"
            ])
            for idx, seg in enumerate(self.segments, 1):
                writer.writerow([
                    seg.row_id or idx,
                    seg.state.value.capitalize(),
                    seg.origin.value.upper(),
                    f"{seg.percent}%" if seg.percent > 0 else "",
                    display_text(seg.source),
                    display_text(seg.target)
                ])

    def _write_sdltm(self, out_path: str) -> None:
        """Cria e preenche uma memória SDLTM nativa."""
        import tempfile
        tmp_db = os.path.join(tempfile.gettempdir(), f"gen_sdltm_{os.getpid()}.db")
        if os.path.exists(tmp_db):
            os.remove(tmp_db)

        tm = TranslationMemory(tmp_db)
        tm.add_many(self.segments, self.src_lang, self.tgt_lang)
        write_sdltm(tm, out_path, self.src_lang, self.tgt_lang)
        tm.close()
        if os.path.exists(tmp_db):
            os.remove(tmp_db)

