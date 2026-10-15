"""
main.py - ponto de entrada da CAT Tool.

Uso:  python main.py
Abre a janela principal com navegação por sidebar.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from ui.main_container import MainContainer


def main() -> int:
    app = QApplication(sys.argv)
    win = MainContainer()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
