"""
core.project - Project management for multiple translation files.

Allows managing multiple TMX/SDLXLIFF files as a single project.
Stores project metadata, file lists, and associated resources (TMs/TBs) in JSON.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class ProjectFile:
    """Represents a single file in a project."""
    path: str
    file_type: str = "sdlxliff"  # "tmx" or "sdlxliff"
    source_lang: str = ""
    target_lang: str = ""
    words: int = 0
    segment_count: int = 0
    translated_count: int = 0
    draft_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    untranslated_count: int = 0
    
    # Word-level breakdown (Trados Studio standard)
    translated_words: int = 0
    draft_words: int = 0
    approved_words: int = 0
    rejected_words: int = 0
    untranslated_words: int = 0

    # Analysis Statistics match bands
    match_repetitions_words: int = 0
    match_repetitions_segs: int = 0
    match_perfect_words: int = 0
    match_perfect_segs: int = 0
    match_context_words: int = 0
    match_context_segs: int = 0
    match_100_words: int = 0
    match_100_segs: int = 0
    match_95_99_words: int = 0
    match_95_99_segs: int = 0
    match_85_94_words: int = 0
    match_85_94_segs: int = 0
    match_75_84_words: int = 0
    match_75_84_segs: int = 0
    match_50_74_words: int = 0
    match_50_74_segs: int = 0
    match_new_words: int = 0
    match_new_segs: int = 0

    size_bytes: int = 0
    status: str = "In Translation"
    usage: str = "Translatable"
    file_type_ident: str = "SpreadsheetML v. 1"
    last_modified: str = ""
    
    @property
    def progress(self) -> float:
        """Returns translation progress as percentage strictly bounded [0.0, 100.0]."""
        # Trados standard: If word counts are available, use words (Translated + Approved) / Total Words
        confirmed_words = self.translated_words + self.approved_words
        if self.words > 0 and confirmed_words > 0:
            return max(0.0, min(100.0, (confirmed_words / self.words) * 100.0))
        
        # Fallback to segments
        confirmed_segs = self.translated_count + self.approved_count
        if self.segment_count > 0 and confirmed_segs > 0:
            return max(0.0, min(100.0, (confirmed_segs / self.segment_count) * 100.0))
            
        return 0.0

    @property
    def size_formatted(self) -> str:
        if self.size_bytes > 0:
            return f"{self.size_bytes // 1024} KB"
        try:
            if os.path.exists(self.path):
                sz = os.path.getsize(self.path)
                return f"{sz // 1024} KB"
        except Exception:
            pass
        return "0 KB"


@dataclass
class Project:
    """Represents a translation project with multiple files and resources."""
    name: str
    path: str = ""
    created: str = ""
    modified: str = ""
    due_date: str = "[none]"
    status: str = "In Progress"
    project_type: str = "Studio project"
    customer: str = "(none)"
    description: str = ""
    location: str = ""
    server: str = "(none)"
    organization: str = "n/a"
    project_template: str = "(none)"
    reference_project: str = "(none)"
    files: List[ProjectFile] = field(default_factory=list)
    
    # Recursos essenciais do projeto injetados aqui
    tm_paths: List[str] = field(default_factory=list) # Caminhos para os ficheiros SQLite (.sdltm)
    tb_paths: List[str] = field(default_factory=list) # Caminhos para Termbases
    
    source_lang: str = ""
    target_lang: str = ""
    
    # Flag para ativar pré-tradução via SLM (Ollama) neste projeto
    use_local_slm: bool = False 
    
    def __post_init__(self) -> None:
        if not self.created:
            self.created = datetime.now().isoformat()
        self.modified = datetime.now().isoformat()
        if not self.location and self.path:
            self.location = os.path.dirname(self.path)
    
    def add_file(self, path: str, file_type: str = "sdlxliff") -> ProjectFile:
        proj_file = ProjectFile(
            path=path,
            file_type=file_type,
            last_modified=datetime.now().isoformat()
        )
        self.files.append(proj_file)
        self.modified = datetime.now().isoformat()
        return proj_file
    
    def remove_file(self, path: str) -> bool:
        for i, f in enumerate(self.files):
            if f.path == path:
                self.files.pop(i)
                self.modified = datetime.now().isoformat()
                return True
        return False
    
    def total_segments(self) -> int:
        return sum(f.segment_count for f in self.files)
    
    def total_translated(self) -> int:
        return sum(f.translated_count + f.approved_count for f in self.files)

    def total_words(self) -> int:
        return sum(f.words for f in self.files)

    def total_translated_words(self) -> int:
        return sum(f.translated_words + f.approved_words for f in self.files)
    
    def overall_progress(self) -> float:
        tw = self.total_words()
        cw = self.total_translated_words()
        if tw > 0 and cw > 0:
            return max(0.0, min(100.0, (cw / tw) * 100.0))
        total_segs = self.total_segments()
        cs = self.total_translated()
        if total_segs > 0 and cs > 0:
            return max(0.0, min(100.0, (cs / total_segs) * 100.0))
        return 0.0
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "created": self.created,
            "modified": self.modified,
            "due_date": self.due_date,
            "status": self.status,
            "project_type": self.project_type,
            "customer": self.customer,
            "description": self.description,
            "location": self.location,
            "server": self.server,
            "organization": self.organization,
            "project_template": self.project_template,
            "reference_project": self.reference_project,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "tm_paths": self.tm_paths,
            "tb_paths": self.tb_paths,
            "use_local_slm": self.use_local_slm,
            "files": [
                {
                    "path": f.path,
                    "file_type": f.file_type,
                    "source_lang": f.source_lang,
                    "target_lang": f.target_lang,
                    "words": f.words,
                    "segment_count": f.segment_count,
                    "translated_count": f.translated_count,
                    "draft_count": f.draft_count,
                    "approved_count": f.approved_count,
                    "rejected_count": f.rejected_count,
                    "untranslated_count": f.untranslated_count,
                    "translated_words": f.translated_words,
                    "draft_words": f.draft_words,
                    "approved_words": f.approved_words,
                    "rejected_words": f.rejected_words,
                    "untranslated_words": f.untranslated_words,
                    "size_bytes": f.size_bytes,
                    "status": f.status,
                    "usage": f.usage,
                    "file_type_ident": f.file_type_ident,
                    "last_modified": f.last_modified,
                }
                for f in self.files
            ]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        proj = cls(
            name=data["name"],
            path=data.get("path", ""),
            created=data.get("created", ""),
            modified=data.get("modified", ""),
            due_date=data.get("due_date", "[none]"),
            status=data.get("status", "In Progress"),
            project_type=data.get("project_type", "Studio project"),
            customer=data.get("customer", "(none)"),
            description=data.get("description", ""),
            location=data.get("location", ""),
            server=data.get("server", "(none)"),
            organization=data.get("organization", "n/a"),
            project_template=data.get("project_template", "(none)"),
            reference_project=data.get("reference_project", "(none)"),
            source_lang=data.get("source_lang", ""),
            target_lang=data.get("target_lang", ""),
            tm_paths=data.get("tm_paths", []),
            tb_paths=data.get("tb_paths", []),
            use_local_slm=data.get("use_local_slm", False)
        )
        for f_data in data.get("files", []):
            proj.files.append(ProjectFile(
                path=f_data["path"],
                file_type=f_data.get("file_type", "sdlxliff"),
                source_lang=f_data.get("source_lang", ""),
                target_lang=f_data.get("target_lang", ""),
                words=f_data.get("words", 0),
                segment_count=f_data.get("segment_count", 0),
                translated_count=f_data.get("translated_count", 0),
                draft_count=f_data.get("draft_count", 0),
                approved_count=f_data.get("approved_count", 0),
                rejected_count=f_data.get("rejected_count", 0),
                untranslated_count=f_data.get("untranslated_count", 0),
                translated_words=f_data.get("translated_words", 0),
                draft_words=f_data.get("draft_words", 0),
                approved_words=f_data.get("approved_words", 0),
                rejected_words=f_data.get("rejected_words", 0),
                untranslated_words=f_data.get("untranslated_words", 0),
                size_bytes=f_data.get("size_bytes", 0),
                status=f_data.get("status", "In Translation"),
                usage=f_data.get("usage", "Translatable"),
                file_type_ident=f_data.get("file_type_ident", "SpreadsheetML v. 1"),
                last_modified=f_data.get("last_modified", "")
            ))
        return proj
    
    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: str) -> "Project":
        path_str = str(path)
        ext = Path(path_str).suffix.lower()

        # Natively parse SDL Trados .sdlproj if matching extension or XML signature
        if ext == ".sdlproj":
            from io_layer.sdlproj import parse_sdlproj
            proj = parse_sdlproj(path_str)
            if proj is not None:
                return proj

        try:
            with open(path_str, "rb") as bf:
                head = bf.read(128).strip()
                if head.startswith(b"<?xml") or b"<Project " in head or b"<Project>" in head:
                    from io_layer.sdlproj import parse_sdlproj
                    proj = parse_sdlproj(path_str)
                    if proj is not None:
                        return proj
        except Exception:
            pass

        # Standard CAT project (JSON)
        try:
            with open(path_str, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return cls(name=Path(path_str).stem)
                data = json.loads(content)
            return cls.from_dict(data)
        except Exception:
            return cls(name=Path(path_str).stem)

def is_project_file(path: str) -> bool:
    return Path(path).suffix.lower() in (".catproj", ".sdlproj")