"""
ui.project_manager - Project management dialog.

Dialog to create, open, and manage translation projects with multiple files.
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QLineEdit, QComboBox, QDialogButtonBox,
)

from core.project import Project, ProjectFile, is_project_file


class ProjectManagerDialog(QDialog):
    """Dialog for managing translation projects."""
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_project: Optional[Project] = None
        self.project_path: str = ""
        self._apply_dark_theme()
        self._build_ui()
    
    def _apply_dark_theme(self) -> None:
        """Apply dark theme consistent with main window."""
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
        palette.setColor(QPalette.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.Button, QColor(30, 30, 30))
        palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.Highlight, QColor(61, 174, 233))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        self.setPalette(palette)
    
    def _build_ui(self) -> None:
        self.setWindowTitle("Project Manager")
        self.resize(900, 600)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Project info
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel("Project:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Project name")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        info_layout.addWidget(self.name_edit, stretch=2)
        
        info_layout.addWidget(QLabel("Source:"))
        self.src_combo = QComboBox()
        self.src_combo.addItems(["en-US", "en-GB", "pt-PT", "pt-BR", "es-ES", "fr-FR", "de-DE"])
        self.src_combo.setStyleSheet("""
            QComboBox {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        info_layout.addWidget(self.src_combo)
        
        info_layout.addWidget(QLabel("Target:"))
        self.tgt_combo = QComboBox()
        self.tgt_combo.addItems(["pt-PT", "pt-BR", "en-US", "es-ES", "fr-FR", "de-DE"])
        self.tgt_combo.setStyleSheet("""
            QComboBox {
                background-color: #1e1e1e;
                color: #ddd;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        info_layout.addWidget(self.tgt_combo)
        
        layout.addLayout(info_layout)
        
        # File list
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["File", "Type", "Segments", "Translated", "Progress"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                gridline-color: #333;
                selection-background-color: #3dae73;
                selection-color: white;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #8eb4f3;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #444;
                font-weight: bold;
            }
        """)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        btn_add = QPushButton("Add File")
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #3dae73;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4dbe83;
            }
        """)
        btn_add.clicked.connect(self._add_file)
        btn_layout.addWidget(btn_add)
        
        btn_remove = QPushButton("Remove")
        btn_remove.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #f75c4c;
            }
        """)
        btn_remove.clicked.connect(self._remove_file)
        btn_layout.addWidget(btn_remove)
        
        btn_layout.addStretch()
        
        # Dialog buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.buttons.setStyleSheet("""
            QPushButton {
                background-color: #3dae73;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4dbe83;
            }
        """)
        self.buttons.accepted.connect(self._save_project)
        self.buttons.rejected.connect(self.reject)
        btn_layout.addWidget(self.buttons)
        
        layout.addLayout(btn_layout)
    
    def _add_file(self) -> None:
        """Add a file to the project."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Translation File", "",
            "CAT Files (*.tmx *.sdlxliff *.xlf *.xliff);;All Files (*.*)"
        )
        if not path:
            return
        
        ext = os.path.splitext(path)[1].lower()
        file_type = "tmx" if ext == ".tmx" else "sdlxliff"
        
        if self.current_project is None:
            self.current_project = Project(name=self.name_edit.text() or "Untitled")
        
        proj_file = self.current_project.add_file(path, file_type)
        self._update_table()
    
    def _remove_file(self) -> None:
        """Remove selected file from project."""
        if self.current_project is None:
            return
        
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Remove", "Select a file to remove.")
            return
        
        proj_file = self.current_project.files[row]
        self.current_project.remove_file(proj_file.path)
        self._update_table()
    
    def _update_table(self) -> None:
        """Update the file list table."""
        if self.current_project is None:
            self.table.setRowCount(0)
            return
        
        self.table.setRowCount(len(self.current_project.files))
        
        for row, f in enumerate(self.current_project.files):
            self.table.setItem(row, 0, QTableWidgetItem(os.path.basename(f.path)))
            self.table.setItem(row, 1, QTableWidgetItem(f.file_type.upper()))
            self.table.setItem(row, 2, QTableWidgetItem(str(f.segment_count)))
            self.table.setItem(row, 3, QTableWidgetItem(str(f.translated_count)))
            self.table.setItem(row, 4, QTableWidgetItem(f"{f.progress:.1f}%"))
    
    def _save_project(self) -> None:
        """Save the project."""
        if self.current_project is None or not self.current_project.files:
            QMessageBox.warning(self, "Save", "Add at least one file to the project.")
            return
        
        self.current_project.name = self.name_edit.text() or "Untitled"
        self.current_project.source_lang = self.src_combo.currentText()
        self.current_project.target_lang = self.tgt_combo.currentText()
        
        if not self.project_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Project", "", "CAT Project (*.catproj)"
            )
            if not path:
                return
            if not path.endswith(".catproj"):
                path += ".catproj"
            self.project_path = path
        
        self.current_project.save(self.project_path)
        self.accept()
    
    def load_project(self, path: str) -> None:
        """Load an existing project."""
        self.project_path = path
        self.current_project = Project.load(path)
        self.name_edit.setText(self.current_project.name)
        
        # Set language combos
        src_idx = self.src_combo.findText(self.current_project.source_lang)
        if src_idx >= 0:
            self.src_combo.setCurrentIndex(src_idx)
        
        tgt_idx = self.tgt_combo.findText(self.current_project.target_lang)
        if tgt_idx >= 0:
            self.tgt_combo.setCurrentIndex(tgt_idx)
        
        self._update_table()
    
    def get_project(self) -> Optional[Project]:
        """Return the current project."""
        return self.current_project
