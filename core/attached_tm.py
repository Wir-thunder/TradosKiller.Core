"""
core.attached_tm - Gestão e consulta de Memórias de Tradução associadas ao projeto/ficheiro.

Reproduz o comportamento do SDL Trados Studio (Language Pairs -> Translation Memory and Automated Translation):
- Cada memória anexada (.sdltm ou .tmx) possui configurações de:
  - Enabled: Ativa ou inativa
  - Lookup: Consultar correspondências (100% e Fuzzy) ao navegar pelos segmentos
  - Concordance: Incluir na busca de concordância (F3)
  - Update: Gravar e atualizar a memória ao confirmar segmentos (Ctrl+Enter)
  - Penalty: Penalidade percentual aplicada ao score (ex: 1% para TMs secundárias)
"""
from __future__ import annotations

import difflib
import os
import sqlite3
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from core.segment import Segment, SegState, SegOrigin, display_text
from io_layer.sdltm import parse_sdltm_segment_xml, build_sdltm_segment_xml, insert_or_update_sdltm_unit, detect_sdltm_langs
from io_layer.tmx import iter_tmx, detect_tmx_langs


@dataclass
class TMMatch:
    """Representa uma correspondência encontrada numa memória associada."""
    tm_name: str
    source: str
    target: str
    percent: int
    is_exact: bool = False
    origin: str = "TM"
    diff_html: str = ""

    @property
    def display_label(self) -> str:
        symbol = "★" if self.percent >= 100 else "◆"
        return f"{symbol} [{self.percent}% - {self.tm_name}] {display_text(self.target)}"


@dataclass
class AttachedTMConfig:
    """Configuração individual de uma memória associada ao documento/projeto."""
    path: str
    name: str = ""
    enabled: bool = True
    lookup: bool = True       # Consultar correspondências
    concordance: bool = True  # Busca de concordância F3
    update: bool = True       # Atualizar ao confirmar segmento (Ctrl+Enter)
    penalty: int = 0          # Penalidade percentual (ex: 0%)

    def __post_init__(self) -> None:
        if not self.name and self.path:
            self.name = os.path.basename(self.path)

    @property
    def file_type(self) -> str:
        ext = os.path.splitext(self.path)[1].lower()
        if ext == ".sdltm":
            return "File-based SDLTM"
        elif ext == ".tmx":
            return "File-based TMX"
        return "Translation Memory"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "enabled": self.enabled,
            "lookup": self.lookup,
            "concordance": self.concordance,
            "update": self.update,
            "penalty": self.penalty
        }

    @classmethod
    def from_dict(cls, data: dict) -> AttachedTMConfig:
        return cls(
            path=data.get("path", ""),
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            lookup=data.get("lookup", True),
            concordance=data.get("concordance", True),
            update=data.get("update", True),
            penalty=data.get("penalty", 0)
        )


class AttachedTMManager:
    """Motor de consulta e atualização das memórias de tradução associadas."""

    @staticmethod
    def query_matches(source_text: str, tms: List[AttachedTMConfig],
                      min_match: int = 70, limit: int = 5) -> List[TMMatch]:
        """Busca correspondências exatas e parciais (fuzzy) em todas as TMs ativas com Lookup=True."""
        clean_src = display_text(source_text).strip()
        if not clean_src:
            return []

        matches: List[TMMatch] = []

        for tm in tms:
            if not tm.enabled or not tm.lookup or not os.path.exists(tm.path):
                continue

            ext = os.path.splitext(tm.path)[1].lower()
            if ext == ".sdltm":
                tm_matches = AttachedTMManager._query_sdltm(clean_src, tm, min_match, limit)
                matches.extend(tm_matches)
            elif ext == ".tmx":
                tm_matches = AttachedTMManager._query_tmx(clean_src, tm, min_match, limit)
                matches.extend(tm_matches)

        # Ordena por % de correspondência decrescente
        matches.sort(key=lambda m: m.percent, reverse=True)
        return matches[:limit]

    @staticmethod
    def _query_sdltm(clean_src: str, tm: AttachedTMConfig,
                     min_match: int = 70, limit: int = 5) -> List[TMMatch]:
        results: List[TMMatch] = []
        try:
            import re
            from xml.sax.saxutils import escape

            conn = sqlite3.connect(f"file:{tm.path}?mode=ro", uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 1. Busca exata por hash
            src_hash = zlib.crc32(clean_src.encode("utf-8"))
            row = cur.execute(
                "SELECT source_segment, target_segment FROM translation_units WHERE source_hash = ? LIMIT 1",
                (src_hash,)
            ).fetchone()

            if row and row["target_segment"]:
                tgt_txt, _ = parse_sdltm_segment_xml(row["target_segment"])
                eff_percent = max(0, 100 - tm.penalty)
                results.append(TMMatch(
                    tm_name=tm.name,
                    source=clean_src,
                    target=tgt_txt,
                    percent=eff_percent,
                    is_exact=True,
                    origin="SDLTM"
                ))
                conn.close()
                return results

            # 2. Busca exata por XML Value (com e sem escape XML)
            for cand_val in {clean_src, escape(clean_src)}:
                pat = f"%<Value>{cand_val}</Value>%"
                row2 = cur.execute(
                    "SELECT source_segment, target_segment FROM translation_units WHERE source_segment LIKE ? LIMIT 1",
                    (pat,)
                ).fetchone()
                if row2 and row2["target_segment"]:
                    src_parsed, _ = parse_sdltm_segment_xml(row2["source_segment"])
                    if display_text(src_parsed).strip().lower() == clean_src.lower():
                        tgt_txt, _ = parse_sdltm_segment_xml(row2["target_segment"])
                        eff_percent = max(0, 100 - tm.penalty)
                        results.append(TMMatch(
                            tm_name=tm.name,
                            source=clean_src,
                            target=tgt_txt,
                            percent=eff_percent,
                            is_exact=True,
                            origin="SDLTM"
                        ))
                        conn.close()
                        return results

            # 3. Busca Fuzzy inteligente filtrando pelas palavras mais significativas
            words = sorted(
                {w for w in re.findall(r"\w{3,}", clean_src) if not w.isdigit()},
                key=len,
                reverse=True
            )[:3]

            rows = []
            if words:
                clauses = " OR ".join(["source_segment LIKE ?" for _ in words])
                params = [f"%{w}%" for w in words]
                rows = cur.execute(
                    f"SELECT source_segment, target_segment FROM translation_units WHERE {clauses} LIMIT 300",
                    params
                ).fetchall()

            if not rows:
                rows = cur.execute(
                    "SELECT source_segment, target_segment FROM translation_units LIMIT 250"
                ).fetchall()

            for r in rows:
                if not r["target_segment"] or not r["source_segment"]:
                    continue
                cand_src, _ = parse_sdltm_segment_xml(r["source_segment"])
                cand_src_clean = display_text(cand_src).strip()
                if not cand_src_clean:
                    continue

                if cand_src_clean.lower() == clean_src.lower():
                    ratio = 100
                else:
                    ratio = int(difflib.SequenceMatcher(None, clean_src.lower(), cand_src_clean.lower()).ratio() * 100)
                eff_percent = max(0, ratio - tm.penalty)
                if eff_percent >= min_match:
                    cand_tgt, _ = parse_sdltm_segment_xml(r["target_segment"])
                    results.append(TMMatch(
                        tm_name=tm.name,
                        source=cand_src_clean,
                        target=display_text(cand_tgt),
                        percent=eff_percent,
                        is_exact=(eff_percent == 100),
                        origin="SDLTM"
                    ))

            conn.close()
        except Exception:
            pass

        return results

    @staticmethod
    def _query_tmx(clean_src: str, tm: AttachedTMConfig,
                   min_match: int = 70, limit: int = 5) -> List[TMMatch]:
        results: List[TMMatch] = []
        try:
            count = 0
            for seg in iter_tmx(tm.path):
                cand_src = display_text(seg.source).strip()
                if not cand_src or not seg.target:
                    continue

                if cand_src.lower() == clean_src.lower():
                    eff_percent = max(0, 100 - tm.penalty)
                    results.append(TMMatch(
                        tm_name=tm.name,
                        source=cand_src,
                        target=display_text(seg.target),
                        percent=eff_percent,
                        is_exact=True,
                        origin="TMX"
                    ))
                    break

                ratio = int(difflib.SequenceMatcher(None, clean_src.lower(), cand_src.lower()).ratio() * 100)
                eff_percent = max(0, ratio - tm.penalty)
                if eff_percent >= min_match:
                    results.append(TMMatch(
                        tm_name=tm.name,
                        source=cand_src,
                        target=display_text(seg.target),
                        percent=eff_percent,
                        is_exact=False,
                        origin="TMX"
                    ))

                count += 1
                if count > 500:
                    break
        except Exception:
            pass

        return results

    @staticmethod
    def concordance_search(term: str, tms: List[AttachedTMConfig], limit: int = 20) -> List[TMMatch]:
        """Executa busca de concordância (F3) em todas as memórias com Concordance=True."""
        term_clean = term.strip().lower()
        if not term_clean:
            return []

        results: List[TMMatch] = []

        for tm in tms:
            if not tm.enabled or not tm.concordance or not os.path.exists(tm.path):
                continue

            ext = os.path.splitext(tm.path)[1].lower()
            if ext == ".sdltm":
                try:
                    conn = sqlite3.connect(f"file:{tm.path}?mode=ro", uri=True)
                    conn.row_factory = sqlite3.Row
                    pat = f"%{term_clean}%"
                    rows = conn.execute(
                        "SELECT source_segment, target_segment FROM translation_units WHERE lower(source_segment) LIKE ? LIMIT ?",
                        (pat, limit)
                    ).fetchall()
                    for r in rows:
                        src_txt, _ = parse_sdltm_segment_xml(r["source_segment"])
                        tgt_txt, _ = parse_sdltm_segment_xml(r["target_segment"])
                        if term_clean in src_txt.lower():
                            results.append(TMMatch(
                                tm_name=tm.name,
                                source=src_txt,
                                target=tgt_txt,
                                percent=100 if src_txt.lower() == term_clean else 80,
                                origin="Concordance"
                            ))
                    conn.close()
                except Exception:
                    pass

        return results

    @staticmethod
    def update_tms(source_text: str, target_text: str, tms: List[AttachedTMConfig],
                   src_lang: str = "en-US", tgt_lang: str = "pt-PT") -> int:
        """Atualiza todas as memórias configuradas com Update=True ao confirmar o segmento."""
        clean_src = display_text(source_text).strip()
        clean_tgt = display_text(target_text).strip()
        if not clean_src or not clean_tgt:
            return 0

        updated_count = 0

        for tm in tms:
            if not tm.enabled or not tm.update or not os.path.exists(tm.path):
                continue

            ext = os.path.splitext(tm.path)[1].lower()
            if ext == ".sdltm":
                ok = insert_or_update_sdltm_unit(tm.path, clean_src, clean_tgt, src_lang, tgt_lang)
                if ok:
                    updated_count += 1

        return updated_count

