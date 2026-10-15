"""
io_layer.sdlpackage - Manipulador de pacotes do SDL Trados Studio (.sdlppx e .sdlrpx).

Os pacotes do Trados são ficheiros ZIP que contêm:
  - Ficheiro de projeto (.sdlproj)
  - Ficheiros de tradução bilingues (.sdlxliff) organizados por diretório de idioma
  - Memórias de tradução (.sdltm) no diretório TMs/
  - Bases terminológicas (Termbase/) e relatórios (Reports/)

Este módulo permite:
  - Descompactar pacotes de projeto (.sdlppx) e carregar o projeto e ficheiros diretamente
  - Gerar pacotes de retorno (.sdlrpx) com os ficheiros .sdlxliff traduzidos
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from core.project import Project
from io_layer.sdlproj import parse_sdlproj


def is_sdlpackage(path: str) -> bool:
    """Verifica se o ficheiro é um pacote SDL Trados (.sdlppx ou .sdlrpx)."""
    return Path(path).suffix.lower() in (".sdlppx", ".sdlrpx")


def extract_package(package_path: str, extract_to: Optional[str] = None) -> Tuple[Optional[str], Optional[Project]]:
    """
    Extrai um pacote .sdlppx/.sdlrpx para uma pasta e retorna o caminho para o .sdlproj e o Project.
    Se extract_to não for fornecido, cria uma pasta com o nome do pacote ao lado dele.
    """
    pkg_file = Path(package_path)
    if not pkg_file.exists():
        return None, None

    if extract_to is None:
        target_dir = pkg_file.parent / f"{pkg_file.stem}_extracted"
    else:
        target_dir = Path(extract_to)

    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(package_path, "r") as zf:
        zf.extractall(target_dir)

    # Localiza o .sdlproj dentro da pasta extraída
    sdlproj_files = list(target_dir.rglob("*.sdlproj"))
    if not sdlproj_files:
        return None, None

    main_proj = sdlproj_files[0]
    project = parse_sdlproj(str(main_proj))
    return str(main_proj), project


def create_return_package(project: Project, out_package_path: str) -> str:
    """
    Gera um pacote de retorno .sdlrpx contendo os ficheiros .sdlxliff traduzidos do projeto.
    """
    out_file = Path(out_package_path)
    if out_file.suffix.lower() != ".sdlrpx":
        out_file = out_file.with_suffix(".sdlrpx")

    out_file.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for proj_file in project.files:
            file_path = Path(proj_file.path)
            if file_path.exists() and file_path.suffix.lower() == ".sdlxliff":
                # Preserva o nome do ficheiro ou subpasta relativa se possível
                arcname = file_path.name
                zf.write(file_path, arcname=arcname)

    return str(out_file)
