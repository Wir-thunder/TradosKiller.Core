"""
setup.py - Instalação do pacote TradosKiller CAT Tool
"""
from setuptools import setup, find_packages

setup(
    name="TradosKiller",
    version="1.0.0",
    description="CAT Tool de alto desempenho compatível nativamente com SDL Trados Studio (.sdlproj, .sdlxliff, .sdltm) e SLM Neural",
    author="Wir-thunder",
    author_email="icaro.trad@gmail.com",
    packages=find_packages(),
    py_modules=["main"],
    install_requires=[
        "PySide6>=6.6.0",
        "lxml>=4.9.0",
        "python-docx>=1.0.0",
        "requests>=2.31.0",
        "comtypes>=1.4.0",
    ],
    entry_points={
        "gui_scripts": [
            "tradoskiller = main:main",
        ],
        "console_scripts": [
            "tradoskiller-cli = main:main",
        ],
    },
    python_requires=">=3.9",
)
