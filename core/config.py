from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Config:
    """Application configuration."""
    recent_files: List[str] = field(default_factory=list)
    recent_projects: List[str] = field(default_factory=list)
    max_recent_files: int = 10
    
    # Idiomas padrão
    default_source_lang: str = "en-US"
    default_target_lang: str = "pt-PT" # Ajustado para o teu contexto local
    
    # Comportamento Geral
    auto_save: bool = True
    theme: str = "dark"
    
    # Motor de Memória de Tradução (O Fim do Gargalo)
    tm_load_to_ram: bool = True  # Carrega o SQLite inteiro para hash maps no arranque
    
    # Correção Ortográfica e Gramatical (LanguageTool)
    spell_check_enabled: bool = True
    languagetool_endpoint: str = "http://localhost:8081" # Permite usar um servidor local standalone
    
    # Integração de Pré-tradução Neural (SLMs Locais)
    ollama_enabled: bool = False
    ollama_model: str = "llama3.2" # Ou phi3, mistral, etc.
    ollama_endpoint: str = "http://localhost:11434/api/generate"
    
    def add_recent_file(self, path: str) -> None:
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        if len(self.recent_files) > self.max_recent_files:
            self.recent_files = self.recent_files[:self.max_recent_files]
    
    def clear_recent_files(self) -> None:
        self.recent_files.clear()
    
    def to_dict(self) -> dict:
        return {
            "recent_files": self.recent_files,
            "recent_projects": self.recent_projects,
            "max_recent_files": self.max_recent_files,
            "default_source_lang": self.default_source_lang,
            "default_target_lang": self.default_target_lang,
            "auto_save": self.auto_save,
            "theme": self.theme,
            "tm_load_to_ram": self.tm_load_to_ram,
            "spell_check_enabled": self.spell_check_enabled,
            "languagetool_endpoint": self.languagetool_endpoint,
            "ollama_enabled": self.ollama_enabled,
            "ollama_model": self.ollama_model,
            "ollama_endpoint": self.ollama_endpoint,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        return cls(
            recent_files=data.get("recent_files", []),
            recent_projects=data.get("recent_projects", []),
            max_recent_files=data.get("max_recent_files", 10),
            default_source_lang=data.get("default_source_lang", "en-US"),
            default_target_lang=data.get("default_target_lang", "pt-PT"),
            auto_save=data.get("auto_save", True),
            theme=data.get("theme", "dark"),
            tm_load_to_ram=data.get("tm_load_to_ram", True),
            spell_check_enabled=data.get("spell_check_enabled", True),
            languagetool_endpoint=data.get("languagetool_endpoint", "http://localhost:8081"),
            ollama_enabled=data.get("ollama_enabled", False),
            ollama_model=data.get("ollama_model", "llama3.2"),
            ollama_endpoint=data.get("ollama_endpoint", "http://localhost:11434/api/generate"),
        )
    
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: str) -> "Config":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return cls()
                data = json.loads(content)
            return cls.from_dict(data)
        except Exception:
            return cls()

def get_config_path() -> str:
    home = Path.home()
    config_dir = home / ".cat_tool"
    return str(config_dir / "config.json")

def load_config() -> Config:
    return Config.load(get_config_path())

def save_config(config: Config) -> None:
    config.save(get_config_path())