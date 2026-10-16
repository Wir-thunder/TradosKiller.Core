"""
ui.slm_studio_dialog - Diálogo Studio para Criação, Treino e Gestão de SLM via Ollama e SDLTMs.

Permite:
- Varrer e selecionar memórias .sdltm do SDL Trados Studio (como as da pasta D:)
- Extrair pares de tradução bilíngues para Few-Shot In-Context Learning
- Gerar Modelfile e registrar o modelo diretamente no Ollama (`ollama create`)
- Exportar dataset de treino completo em formato Alpaca JSONL para fine-tuning (LoRA)
- Configurar o modelo SLM ativo para o Editor e testar traduções em tempo real
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QProgressBar, QTextEdit, QPlainTextEdit, QFileDialog,
    QMessageBox, QListWidget, QListWidgetItem, QTabWidget,
    QWidget, QFrame, QSplitter, QGroupBox
)

from core.slm import OllamaClient, SLMTrainer
from core.config import load_config, save_config


class SLMTrainWorker(QThread):
    """Thread em segundo plano para extração de memórias e criação do modelo Ollama."""
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(
        self,
        model_name: str,
        base_model: str,
        sdltm_paths: List[str],
        few_shot_count: int,
        export_dataset_path: Optional[str] = None
    ) -> None:
        super().__init__()
        self.model_name = model_name
        self.base_model = base_model
        self.sdltm_paths = sdltm_paths
        self.few_shot_count = few_shot_count
        self.export_dataset_path = export_dataset_path

    def run(self) -> None:
        try:
            success, msg = SLMTrainer.create_custom_slm(
                model_name=self.model_name,
                base_model=self.base_model,
                sdltm_paths=self.sdltm_paths,
                few_shot_count=self.few_shot_count,
                export_dataset_path=self.export_dataset_path,
                progress_callback=lambda p, s: self.progress.emit(p, s)
            )
            self.finished.emit(success, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class SLMTestWorker(QThread):
    """Thread para teste de inferência SLM em tempo real sem travar a interface."""
    finished = Signal(str, float)  # translation, elapsed_ms
    error = Signal(str)

    def __init__(self, prompt: str, model: str, temperature: float) -> None:
        super().__init__()
        self.prompt = prompt
        self.model = model
        self.temperature = temperature

    def run(self) -> None:
        t0 = time.time()
        client = OllamaClient()
        try:
            res = client.translate(self.prompt, model=self.model, temperature=self.temperature)
            elapsed_ms = (time.time() - t0) * 1000.0
            self.finished.emit(res, elapsed_ms)
        except Exception as e:
            self.error.emit(str(e))


class SLMStudioDialog(QDialog):
    """Diálogo Studio para Gestão e Treino de SLM Especializada do Tradutor."""

    model_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SLM Studio — Criação e Treino de Modelos Neurais a partir de Memórias SDLTM")
        self.resize(850, 620)
        self.setMinimumSize(780, 550)

        self.client = OllamaClient()
        self.config = load_config()
        self.train_worker: Optional[SLMTrainWorker] = None
        self.test_worker: Optional[SLMTestWorker] = None

        self._build_ui()
        self._refresh_ollama_status()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
            }
            QGroupBox {
                border: 1px solid #3e3e42;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #8eb4f3;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #3e3e42;
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 11px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #007acc;
            }
            QListWidget {
                background-color: #252526;
                color: #dcdcdc;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                padding: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #252526;
                color: #aaaaaa;
                border: 1px solid #333333;
                padding: 6px 16px;
                font-size: 11px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #8eb4f3;
                border-bottom: 2px solid #007acc;
            }
            QProgressBar {
                background-color: #252526;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 3px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Cabeçalho
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #252526; border-radius: 4px; padding: 6px;")
        hl = QHBoxLayout(header_frame)
        hl.setContentsMargins(8, 4, 8, 4)

        icon_lbl = QLabel("🤖")
        icon_lbl.setStyleSheet("font-size: 24px;")
        hl.addWidget(icon_lbl)

        info_vbox = QVBoxLayout()
        title_lbl = QLabel("SLM STUDIO — INTELIGÊNCIA ARTIFICIAL LOCAL & PRIVADA")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #00a4e4;")
        desc_lbl = QLabel("Crie, treine e especialize Small Language Models (SLMs) locais utilizando as suas bases de memórias .sdltm da pasta D:")
        desc_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        info_vbox.addWidget(title_lbl)
        info_vbox.addWidget(desc_lbl)
        hl.addLayout(info_vbox)

        hl.addStretch()

        self.lbl_ollama_badge = QLabel("A verificar Ollama...")
        self.lbl_ollama_badge.setStyleSheet("padding: 4px 10px; border-radius: 12px; font-weight: bold; background-color: #333; color: #fff;")
        hl.addWidget(self.lbl_ollama_badge)

        layout.addWidget(header_frame)

        # Abas
        self.tabs = QTabWidget()
        self._build_tab_creator()
        self._build_tab_active_model()
        layout.addWidget(self.tabs)

        # Botão Fechar
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton("Fechar")
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #333333; color: white; border: 1px solid #484848;
                border-radius: 4px; padding: 6px 16px; font-size: 11px;
            }
            QPushButton:hover { background-color: #444444; }
        """)
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    # -------------------------------------------------------------------------
    # ABA 1: CRIAR SLM ESPECIALIZADA
    # -------------------------------------------------------------------------
    def _build_tab_creator(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Configurações do Modelo
        grp_model = QGroupBox("Configurações do Novo Modelo Ollama")
        gml = QVBoxLayout(grp_model)
        gml.setSpacing(6)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nome do Modelo:"))
        self.txt_model_name = QLineEdit("trados-automotive-slm:latest")
        self.txt_model_name.setToolTip("Nome único para o modelo no Ollama (ex: trados-slm:latest)")
        row1.addWidget(self.txt_model_name, stretch=2)

        row1.addWidget(QLabel("Modelo Base Ollama:"))
        self.combo_base_model = QComboBox()
        self.combo_base_model.setToolTip("Modelo base existente sobre o qual a especialização será criada")
        row1.addWidget(self.combo_base_model, stretch=2)
        gml.addLayout(row1)

        layout.addWidget(grp_model)

        # Seleção de Memórias .sdltm
        grp_sdltm = QGroupBox("Memórias SDLTM de Treino (Toyota, GWM, DYC)")
        gsl = QVBoxLayout(grp_sdltm)
        gsl.setSpacing(6)

        self.list_sdltm = QListWidget()
        self.list_sdltm.setToolTip("Bases de memórias .sdltm que serão lidas para especializar o modelo")
        gsl.addWidget(self.list_sdltm)

        btn_row = QHBoxLayout()
        btn_scan_d = QPushButton("🔍 Varrer Pasta D:\\ (Auto-Detectar)")
        btn_scan_d.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f; color: #93c5fd; border: 1px solid #3b82f6;
                border-radius: 4px; padding: 5px 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2563eb; color: white; }
        """)
        btn_scan_d.clicked.connect(self._scan_d_drive_sdltms)
        btn_row.addWidget(btn_scan_d)

        btn_add_files = QPushButton("📁 Adicionar .sdltm...")
        btn_add_files.setStyleSheet("background-color: #333333; color: white; border-radius: 4px; padding: 5px 12px;")
        btn_add_files.clicked.connect(self._add_sdltm_files)
        btn_row.addWidget(btn_add_files)

        btn_clear = QPushButton("🗑 Limpar")
        btn_clear.setStyleSheet("background-color: #333333; color: #e74c3c; border-radius: 4px; padding: 5px 10px;")
        btn_clear.clicked.connect(self.list_sdltm.clear)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()

        self.lbl_selected_sdltms = QLabel("0 bases selecionadas")
        self.lbl_selected_sdltms.setStyleSheet("color: #888888;")
        btn_row.addWidget(self.lbl_selected_sdltms)
        gsl.addLayout(btn_row)

        layout.addWidget(grp_sdltm)

        # Opções de Treino
        grp_opts = QGroupBox("Opções de Treino & Exportação")
        gol = QHBoxLayout(grp_opts)

        gol.addWidget(QLabel("Exemplos Few-Shot no Modelfile:"))
        self.spin_few_shots = QSpinBox()
        self.spin_few_shots.setRange(20, 1000)
        self.spin_few_shots.setValue(100)
        self.spin_few_shots.setToolTip("Quantidade de pares exemplares reais embutidos nas mensagens de contexto do modelo")
        gol.addWidget(self.spin_few_shots)

        gol.addSpacing(20)

        self.chk_export_dataset = QCheckBox("Exportar dataset de treino completo (.jsonl)")
        self.chk_export_dataset.setChecked(True)
        gol.addWidget(self.chk_export_dataset)

        gol.addStretch()
        layout.addWidget(grp_opts)

        # Barra de Progresso e Ação
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.lbl_train_status = QLabel("Pronto para criar o modelo.")
        self.lbl_train_status.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(self.lbl_train_status)

        action_row = QHBoxLayout()
        self.btn_create_model = QPushButton("🚀 Criar e Treinar Modelo no Ollama")
        self.btn_create_model.setFixedHeight(36)
        self.btn_create_model.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: white; font-weight: bold;
                border-radius: 4px; font-size: 12px; padding: 6px 18px;
            }
            QPushButton:hover { background-color: #1c97ea; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self.btn_create_model.clicked.connect(self._start_training)
        action_row.addWidget(self.btn_create_model)
        layout.addLayout(action_row)

        self.tabs.addTab(tab, "🚀 Criar / Treinar SLM (.sdltm ➔ Ollama)")

    # -------------------------------------------------------------------------
    # ABA 2: MODELO ATIVO & TESTE INTERATIVO
    # -------------------------------------------------------------------------
    def _build_tab_active_model(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Configurações do Modelo Ativo
        grp_active = QGroupBox("Configuração da SLM Ativa no Editor")
        gal = QVBoxLayout(grp_active)
        gal.setSpacing(6)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Modelo Ativo:"))
        self.combo_active_model = QComboBox()
        self.combo_active_model.setToolTip("Modelo que será consultado nas sugestões do Editor e tarefas em lote")
        r1.addWidget(self.combo_active_model, stretch=2)

        r1.addWidget(QLabel("Temperatura:"))
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 1.0)
        self.spin_temp.setSingleStep(0.05)
        self.spin_temp.setValue(0.1)
        self.spin_temp.setToolTip("0.1 para precisão técnica determinística; valores mais altos para maior criatividade")
        r1.addWidget(self.spin_temp)

        btn_browse_gguf = QPushButton("📂 Selecionar .gguf...")
        btn_browse_gguf.setStyleSheet("background-color: #3e3e42; color: #ffffff; border: 1px solid #555555; border-radius: 3px; padding: 4px 8px;")
        btn_browse_gguf.setToolTip("Carrega qualquer modelo .gguf local sem precisar do Ollama")
        btn_browse_gguf.clicked.connect(self._browse_custom_gguf)
        r1.addWidget(btn_browse_gguf)

        btn_save_config = QPushButton("💾 Definir como Padrão")
        btn_save_config.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; border-radius: 3px; padding: 4px 10px;")
        btn_save_config.clicked.connect(self._save_active_settings)
        r1.addWidget(btn_save_config)
        gal.addLayout(r1)

        self.chk_auto_suggest = QCheckBox("Sugerir automaticamente com SLM nos segmentos sem correspondência 100% de TM")
        self.chk_auto_suggest.setChecked(True)
        gal.addWidget(self.chk_auto_suggest)

        layout.addWidget(grp_active)

        # Teste Interativo
        grp_test = QGroupBox("Área de Teste Interativo de Tradução Neural")
        gtl = QVBoxLayout(grp_test)
        gtl.setSpacing(6)

        gtl.addWidget(QLabel("Texto Fonte em Inglês:"))
        self.txt_test_source = QPlainTextEdit()
        self.txt_test_source.setFixedHeight(65)
        self.txt_test_source.setPlaceholderText("Digite um texto em inglês para testar a tradução da SLM (ex: Disconnect the battery terminal)...")
        self.txt_test_source.setPlainText("Disconnect the cable from the negative battery terminal and wait for 90 seconds.")
        gtl.addWidget(self.txt_test_source)

        test_btn_row = QHBoxLayout()
        btn_run_test = QPushButton("▶ Traduzir com SLM")
        btn_run_test.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: white; font-weight: bold;
                border-radius: 4px; padding: 6px 14px;
            }
            QPushButton:hover { background-color: #1c97ea; }
        """)
        btn_run_test.clicked.connect(self._run_interactive_test)
        test_btn_row.addWidget(btn_run_test)

        self.lbl_test_time = QLabel("")
        self.lbl_test_time.setStyleSheet("color: #888888; font-style: italic;")
        test_btn_row.addWidget(self.lbl_test_time)
        test_btn_row.addStretch()
        gtl.addLayout(test_btn_row)

        gtl.addWidget(QLabel("Tradução Gerada pela SLM (Português):"))
        self.txt_test_result = QPlainTextEdit()
        self.txt_test_result.setFixedHeight(65)
        self.txt_test_result.setReadOnly(True)
        self.txt_test_result.setStyleSheet("background-color: #1e1e1e; color: #2ecc71; font-weight: bold;")
        gtl.addWidget(self.txt_test_result)

        layout.addWidget(grp_test)
        layout.addStretch()

        self.tabs.addTab(tab, "⚙️ Modelo Ativo & Teste Interativo")

    # -------------------------------------------------------------------------
    # OPERAÇÕES E SLOTS
    # -------------------------------------------------------------------------
    def _refresh_ollama_status(self) -> None:
        """Atualiza a verificação do servidor Ollama e lista os modelos disponíveis (Ollama + Embedded GGUF)."""
        is_alive = self.client._is_ollama_alive()
        
        from core.embedded_slm import EmbeddedSLMEngine
        has_embedded = EmbeddedSLMEngine.get_instance().is_available()

        if is_alive and has_embedded:
            self.lbl_ollama_badge.setText("● Motor Híbrido: Embedded (Local) + Ollama")
            self.lbl_ollama_badge.setStyleSheet("padding: 4px 10px; border-radius: 12px; font-weight: bold; background-color: #27ae60; color: white;")
        elif has_embedded:
            self.lbl_ollama_badge.setText("● SLM Embedded Ativa (100% Local In-Process)")
            self.lbl_ollama_badge.setStyleSheet("padding: 4px 10px; border-radius: 12px; font-weight: bold; background-color: #2980b9; color: white;")
        elif is_alive:
            self.lbl_ollama_badge.setText("● Ollama Online (11434)")
            self.lbl_ollama_badge.setStyleSheet("padding: 4px 10px; border-radius: 12px; font-weight: bold; background-color: #27ae60; color: white;")
        else:
            self.lbl_ollama_badge.setText("○ Sem Motor SLM (Selecione um .gguf)")
            self.lbl_ollama_badge.setStyleSheet("padding: 4px 10px; border-radius: 12px; font-weight: bold; background-color: #c0392b; color: white;")

        models = self.client.list_models()
        self.combo_base_model.clear()
        self.combo_active_model.clear()

        default_model = getattr(self.config, "ollama_model", "toyotao:latest")
        target_idx = 0

        for idx, m in enumerate(models):
            self.combo_base_model.addItem(m)
            self.combo_active_model.addItem(m)
            if m == default_model or "trados-slm" in m or "toyotao" in m:
                target_idx = idx

        if models:
            self.combo_base_model.setCurrentIndex(target_idx)
            self.combo_active_model.setCurrentIndex(target_idx)

    def _browse_custom_gguf(self) -> None:
        """Permite selecionar manualmente qualquer ficheiro .gguf para uso embarcado."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Modelo GGUF Local",
            "",
            "Modelos GGUF (*.gguf);;Todos os Ficheiros (*.*)"
        )
        if file_path:
            from core.embedded_slm import EmbeddedSLMEngine
            eng = EmbeddedSLMEngine.get_instance()
            ok = eng.load_model(file_path)
            if ok:
                name = f"embedded:{os.path.basename(file_path)}"
                if self.combo_active_model.findText(name) == -1:
                    self.combo_active_model.addItem(name)
                self.combo_active_model.setCurrentText(name)
                self.config.ollama_model = name
                self._refresh_ollama_status()
                QMessageBox.information(
                    self,
                    "Modelo Embedded Carregado",
                    f"Modelo GGUF carregado diretamente em memória com sucesso:\n{os.path.basename(file_path)}\n\n"
                    "O TradosKiller está agora utilizando este modelo in-process sem necessidade de Ollama externo."
                )

    def _scan_d_drive_sdltms(self) -> None:
        r"""Varre automaticamente a pasta D:\ e D:\aa_Memórias_Toyota_GWM_DYC procurando memórias."""
        search_paths = [
            r"D:\aa_Memórias_Toyota_GWM_DYC",
            r"D:\20250218_Trabalhos_PROEDIT",
            r"D:\aa_Projetos_Toyota",
            r"D:\aa_Projetos_GWM"
        ]

        found = []
        for p in search_paths:
            if os.path.exists(p):
                found.extend(SLMTrainer.scan_sdltm_files(p))

        if not found and os.path.exists("D:\\"):
            found.extend(SLMTrainer.scan_sdltm_files("D:\\")[:30])

        existing = {self.list_sdltm.item(i).toolTip() for i in range(self.list_sdltm.count())}

        for path in found:
            if path not in existing:
                size_mb = os.path.getsize(path) / (1024 * 1024)
                item = QListWidgetItem(f"📄 {os.path.basename(path)} ({size_mb:.1f} MB)")
                item.setToolTip(path)
                self.list_sdltm.addItem(item)
                existing.add(path)

        self.lbl_selected_sdltms.setText(f"{self.list_sdltm.count()} bases selecionadas")

    def _add_sdltm_files(self) -> None:
        """Abre diálogo para seleção manual de bases .sdltm."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecionar Memórias SDL Trados (.sdltm)",
            "D:\\",
            "SDL Translation Memories (*.sdltm)"
        )
        if not files:
            return

        existing = {self.list_sdltm.item(i).toolTip() for i in range(self.list_sdltm.count())}

        for path in files:
            if path not in existing:
                size_mb = os.path.getsize(path) / (1024 * 1024)
                item = QListWidgetItem(f"📄 {os.path.basename(path)} ({size_mb:.1f} MB)")
                item.setToolTip(path)
                self.list_sdltm.addItem(item)
                existing.add(path)

        self.lbl_selected_sdltms.setText(f"{self.list_sdltm.count()} bases selecionadas")

    def _start_training(self) -> None:
        """Inicia a extração e criação do modelo SLM no Ollama."""
        model_name = self.txt_model_name.text().strip()
        if not model_name:
            QMessageBox.warning(self, "Aviso", "Por favor, indique um nome para o novo modelo.")
            return

        base_model = self.combo_base_model.currentText()
        if not base_model:
            QMessageBox.warning(self, "Aviso", "Nenhum modelo base selecionado.")
            return

        paths = [self.list_sdltm.item(i).toolTip() for i in range(self.list_sdltm.count())]
        if not paths:
            QMessageBox.warning(self, "Aviso", "Adicione pelo menos uma base de memória .sdltm para treinar o modelo.")
            return

        export_path = None
        if self.chk_export_dataset.isChecked():
            export_path = os.path.join(
                os.environ.get("USERPROFILE", "."),
                "Documents",
                f"{model_name.replace(':', '_')}_dataset.jsonl"
            )

        self.btn_create_model.setEnabled(False)
        self.progress_bar.setValue(5)
        self.lbl_train_status.setText("A inicializar extração de memórias...")

        self.train_worker = SLMTrainWorker(
            model_name=model_name,
            base_model=base_model,
            sdltm_paths=paths,
            few_shot_count=self.spin_few_shots.value(),
            export_dataset_path=export_path
        )
        self.train_worker.progress.connect(self._on_train_progress)
        self.train_worker.finished.connect(self._on_train_finished)
        self.train_worker.start()

    def _on_train_progress(self, percent: int, msg: str) -> None:
        self.progress_bar.setValue(percent)
        self.lbl_train_status.setText(msg)

    def _on_train_finished(self, success: bool, msg: str) -> None:
        self.btn_create_model.setEnabled(True)
        if success:
            self.progress_bar.setValue(100)
            self.lbl_train_status.setText("Modelo criado com sucesso!")
            QMessageBox.information(self, "Sucesso", msg)
            self._refresh_ollama_status()
            # Seleciona o novo modelo como ativo
            new_name = self.txt_model_name.text().strip()
            idx = self.combo_active_model.findText(new_name)
            if idx >= 0:
                self.combo_active_model.setCurrentIndex(idx)
        else:
            self.progress_bar.setValue(0)
            self.lbl_train_status.setText("Falha na criação do modelo.")
            QMessageBox.critical(self, "Erro", msg)

    def _save_active_settings(self) -> None:
        """Salva o modelo ativo nas configurações da aplicação."""
        chosen = self.combo_active_model.currentText()
        if chosen:
            self.config.ollama_model = chosen
            self.config.ollama_enabled = True
            save_config(self.config)
            self.model_changed.emit(chosen)
            QMessageBox.information(self, "Configuração Salva", f"O modelo '{chosen}' foi definido como a SLM ativa do Editor!")

    def _run_interactive_test(self) -> None:
        """Testa o modelo SLM ativo com o texto de entrada."""
        text = self.txt_test_source.toPlainText().strip()
        if not text:
            return

        model = self.combo_active_model.currentText()
        if not model:
            QMessageBox.warning(self, "Aviso", "Selecione um modelo para teste.")
            return

        self.txt_test_result.setPlainText("A processar tradução com a SLM...")
        self.lbl_test_time.setText("Aguardando resposta do Ollama...")

        self.test_worker = SLMTestWorker(
            prompt=text,
            model=model,
            temperature=self.spin_temp.value()
        )
        self.test_worker.finished.connect(self._on_test_finished)
        self.test_worker.error.connect(lambda err: self.txt_test_result.setPlainText(f"Erro: {err}"))
        self.test_worker.start()

    def _on_test_finished(self, translation: str, elapsed_ms: float) -> None:
        self.txt_test_result.setPlainText(translation)
        self.lbl_test_time.setText(f"✓ Resposta em {elapsed_ms:.1f} ms ({elapsed_ms/1000.0:.2f}s)")
