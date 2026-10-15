"""
build_installer.py - Compila o TradosKiller em um executável autônomo (.exe) para Windows.
"""
import os
import sys
import subprocess
from pathlib import Path

def build():
    root = Path(__file__).resolve().parent
    icon_path = root / "assets" / "app_icon.ico"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=TradosKiller",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--add-data=assets;assets",
        "main.py"
    ]
    if icon_path.exists():
        cmd.insert(4, f"--icon={icon_path}")
        
    print(f"Executando PyInstaller: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(root))
    print("\n[OK] Compilacao concluida com sucesso! Executavel gerado em: dist/TradosKiller/TradosKiller.exe")

if __name__ == "__main__":
    build()

