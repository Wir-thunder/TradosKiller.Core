"""
core.tm - Translation Memory em SQLite.

Regra anti-crash: os segmentos vivem em disco, nunca todos em RAM.
- Indice em 'source' para match exacto (O(log n)).
- Tabela FTS5 para concordancia/pesquisa (se disponivel).
- Lookups sempre por consulta paginada (LIMIT/OFFSET), nunca SELECT * massivo.
"""
from __future__ import annotations

import sqlite3
import json
import requests
from pathlib import Path
from typing import Iterable, List, Optional, Callable

# Este import TEM de estar aqui no tm.py (mas NÃO no segment.py)
from .segment import (
    InlineTag, Segment, SegState, SegOrigin, display_text, merge_inline_tokens,
)

class TranslationMemory:
    def __init__(self, db_path: str | Path, tm_paths: List[str] = None) -> None:
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA cache_size = 50000")
            self.conn.execute("PRAGMA temp_store = MEMORY")
        except sqlite3.OperationalError:
            pass
        self._fts_ok = False
        self.attached_tms = []
        
        self._init_schema()
        
        # Mantém a regra anti-crash: Ligar as BDs em vez de as carregar para a RAM
        if tm_paths:
            self._attach_reference_tms(tm_paths)

    # ------------------------------------------------------------------ schema
    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS segments (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                tu_id   TEXT,
                seg_id  TEXT,
                source  TEXT NOT NULL,
                target  TEXT,
                state   TEXT DEFAULT 'untranslated',
                origin  TEXT DEFAULT 'none',
                percent INTEGER DEFAULT 0,
                srclang TEXT,
                tgtlang TEXT,
                source_tags TEXT NOT NULL DEFAULT '[]',
                target_tags TEXT NOT NULL DEFAULT '[]',
                segment_order INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        existing = {row["name"] for row in cur.execute("PRAGMA table_info(segments)")}
        for column, definition in (
            ("source_tags", "TEXT NOT NULL DEFAULT '[]'"),
            ("target_tags", "TEXT NOT NULL DEFAULT '[]'"),
            ("segment_order", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if column not in existing:
                cur.execute(f"ALTER TABLE segments ADD COLUMN {column} {definition}")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_source ON segments(source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tu     ON segments(tu_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_order  ON segments(segment_order, id)")
        
        # FTS5 para concordancia (opcional: depende da build do SQLite)
        try:
            cur.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS seg_fts "
                "USING fts5(source, target, content='segments', content_rowid='id')"
            )
            # Triggers FTS
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS fts_ai AFTER INSERT ON segments BEGIN
                  INSERT INTO seg_fts(rowid, source, target) VALUES (new.id, new.source, new.target);
                END;
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS fts_ad AFTER DELETE ON segments BEGIN
                  INSERT INTO seg_fts(seg_fts, rowid, source, target) VALUES ('delete', old.id, old.source, old.target);
                END;
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS fts_au AFTER UPDATE ON segments BEGIN
                  INSERT INTO seg_fts(seg_fts, rowid, source, target) VALUES ('delete', old.id, old.source, old.target);
                  INSERT INTO seg_fts(rowid, source, target) VALUES (new.id, new.source, new.target);
                END;
            """)
            self._fts_ok = True
        except sqlite3.OperationalError:
            self._fts_ok = False
            
        self.conn.commit()

    # ------------------------------------------------------------------- Integrações (TMs externas e Ollama)
    def _attach_reference_tms(self, tm_paths: List[str]) -> None:
        """Liga ficheiros .sdltm/sqlite externos UMA ÚNICA VEZ no arranque usando ATTACH."""
        cur = self.conn.cursor()
        for i, path in enumerate(tm_paths):
            if not Path(path).exists():
                continue
            
            db_alias = f"ref_tm_{i}"
            # Usa f-string para o caminho porque o SQLite ATTACH nem sempre aceita parâmetros '?'
            path_str = str(path).replace("'", "''") 
            cur.execute(f"ATTACH DATABASE '{path_str}' AS {db_alias}")
            self.attached_tms.append(db_alias)

    def get_reference_match(self, source_text: str) -> Optional[str]:
        """Busca instantânea em disco usando os índices das TMs anexadas (.sdltm ou sqlite)."""
        if not self.attached_tms or not source_text:
            return None

        clean_text = display_text(source_text).strip()
        if not clean_text:
            return None

        for alias in self.attached_tms:
            try:
                # 1. Tenta correspondência em .sdltm via XML do Trados
                pattern = f"%<Value>{clean_text}</Value>%"
                row = self.conn.execute(
                    f"SELECT target_segment FROM {alias}.translation_units WHERE source_segment LIKE ? LIMIT 1",
                    (pattern,),
                ).fetchone()

                if not row or not row[0]:
                    # 2. Tenta correspondência simples para sqlite genérico
                    row = self.conn.execute(
                        f"SELECT target_segment FROM {alias}.translation_units WHERE source_segment = ? LIMIT 1",
                        (clean_text,),
                    ).fetchone()

                if row and row[0]:
                    target_raw = row[0]
                    if "<Segment" in target_raw and "<Elements" in target_raw:
                        from io_layer.sdltm import parse_sdltm_segment_xml
                        tgt_txt, _ = parse_sdltm_segment_xml(target_raw)
                        return display_text(tgt_txt)
                    return target_raw
            except sqlite3.OperationalError:
                continue

        return None

    def ask_ollama_slm(self, source_text: str, model: str = "qwen2.5:1.5b") -> Optional[str]:
        """Fallback de tradução neural local e confidencial via Ollama."""
        endpoint = "http://localhost:11434/api/generate"
        prompt = f"Traduza o seguinte texto técnico para Português de Portugal. Responda APENAS com a tradução, sem notas:\n\n{source_text}"
        
        try:
            response = requests.post(endpoint, json={
                "model": model,
                "prompt": prompt,
                "stream": False
            }, timeout=10)
            
            if response.status_code == 200:
                return response.json().get("response", "").strip()
        except requests.exceptions.RequestException:
            pass 
        
        return None

    # ------------------------------------------------------------------- escrita
    def add(self, seg: Segment, srclang: str = "", tgtlang: str = "") -> int:
        seg_order = seg.order
        if seg_order == 0:
            max_row = self.conn.execute("SELECT MAX(segment_order) FROM segments").fetchone()
            seg_order = (max_row[0] + 1) if (max_row and max_row[0] is not None) else 0

        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO segments(tu_id,seg_id,source,target,state,origin,percent,srclang,tgtlang,"
            "source_tags,target_tags,segment_order) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                seg.tu_id, seg.seg_id, seg.source, seg.target,
                seg.state.value, seg.origin.value, seg.percent, srclang, tgtlang,
                _encode_tags(seg.source_tags), _encode_tags(seg.target_tags), seg_order,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_many(self, segs: Iterable[Segment], srclang: str = "", tgtlang: str = "",
                 batch_size: int = 5000, progress_callback: Optional[Callable[[int], None]] = None) -> int:
        cur = self.conn.cursor()

        # Desativa temporariamente o trigger do FTS para aceleração brutal em arquivos grandes
        if self._fts_ok:
            try:
                cur.execute("DROP TRIGGER IF EXISTS fts_ai")
            except sqlite3.OperationalError:
                pass

        max_row = self.conn.execute("SELECT MAX(segment_order) FROM segments").fetchone()
        base_order = (max_row[0] + 1) if (max_row and max_row[0] is not None) else 0

        total_inserted = 0
        batch = []

        try:
            for seg in segs:
                seg_order = seg.order if seg.order != 0 else (base_order + total_inserted + len(batch))
                batch.append((
                    seg.tu_id, seg.seg_id, seg.source, seg.target,
                    seg.state.value, seg.origin.value, seg.percent, srclang, tgtlang,
                    _encode_tags(seg.source_tags), _encode_tags(seg.target_tags), seg_order
                ))

                if len(batch) >= batch_size:
                    cur.executemany(
                        "INSERT INTO segments(tu_id,seg_id,source,target,state,origin,percent,srclang,tgtlang,"
                        "source_tags,target_tags,segment_order) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        batch
                    )
                    self.conn.commit()
                    total_inserted += len(batch)
                    batch.clear()
                    if progress_callback:
                        progress_callback(total_inserted)

            if batch:
                cur.executemany(
                    "INSERT INTO segments(tu_id,seg_id,source,target,state,origin,percent,srclang,tgtlang,"
                    "source_tags,target_tags,segment_order) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    batch
                )
                self.conn.commit()
                total_inserted += len(batch)
                if progress_callback:
                    progress_callback(total_inserted)
        finally:
            if self._fts_ok:
                try:
                    cur.execute("""
                        CREATE TRIGGER IF NOT EXISTS fts_ai AFTER INSERT ON segments BEGIN
                          INSERT INTO seg_fts(rowid, source, target) VALUES (new.id, new.source, new.target);
                        END;
                    """)
                    self.conn.commit()
                    self.rebuild_fts()
                except sqlite3.OperationalError:
                    pass

        return total_inserted

    def rebuild_fts(self) -> None:
        if self._fts_ok:
            try:
                self.conn.execute("INSERT INTO seg_fts(seg_fts) VALUES('rebuild')")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass

    def update_target(self, row_id: int, target: str,
                      state: SegState = SegState.TRANSLATED,
                      origin: SegOrigin = SegOrigin.INTERACTIVE) -> None:
        row = self.conn.execute(
            "SELECT source,target,source_tags,target_tags FROM segments WHERE id=?",
            (row_id,),
        ).fetchone()
        if row is None:
            return
        target_tags = _decode_tags(row["target_tags"])
        previous = row["target"] or ""
        if not target_tags:
            target_tags = _decode_tags(row["source_tags"])
            if target_tags:
                previous = row["source"] or ""
        stored_target = merge_inline_tokens(target, previous, target_tags)
        self.conn.execute(
            "UPDATE segments SET target=?,target_tags=?,state=?,origin=? WHERE id=?",
            (stored_target, _encode_tags(target_tags), state.value, origin.value, row_id),
        )
        self.conn.commit()

    def update_source(self, row_id: int, source: str) -> None:
        row = self.conn.execute(
            "SELECT source,source_tags FROM segments WHERE id=?", (row_id,)
        ).fetchone()
        if row is None:
            return
        tags = _decode_tags(row["source_tags"])
        stored_source = merge_inline_tokens(source, row["source"] or "", tags)
        self.conn.execute(
            "UPDATE segments SET source=? WHERE id=?", (stored_source, row_id)
        )
        self.conn.commit()

    def iter_all(self, batch: int = 5000):
        offset = 0
        while True:
            rows = self.conn.execute(
                "SELECT * FROM segments ORDER BY segment_order, id LIMIT ? OFFSET ?",
                (batch, offset),
            ).fetchall()
            if not rows:
                return
            for r in rows:
                yield self._to_segment(r)
            offset += len(rows)

    def langs(self) -> tuple[str, str]:
        r = self.conn.execute(
            "SELECT srclang, tgtlang FROM segments LIMIT 1"
        ).fetchone()
        return (r["srclang"] or "", r["tgtlang"] or "") if r else ("", "")

    # -------------------------------------------------------------------- leitura
    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]

    def count_translated(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM segments WHERE state IN ('translated', 'approved') AND target IS NOT NULL AND trim(target)<>''"
        ).fetchone()[0]

    def count_by_state(self) -> dict[str, int]:
        """Retorna a contagem de segmentos agrupados por estado para o Review Bar."""
        rows = self.conn.execute("SELECT state, COUNT(*) FROM segments GROUP BY state").fetchall()
        result = {"untranslated": 0, "draft": 0, "translated": 0, "approved": 0, "rejected": 0}
        for r in rows:
            st = (r[0] or "untranslated").lower().strip()
            if st in result:
                result[st] += r[1]
            else:
                result["untranslated"] += r[1]
        return result

    def filter_ids(self, query: str = "", field: str = "both",
                   state: Optional[str] = None, case_sensitive: bool = False) -> list[int]:
        """Filtra IDs por texto de busca e estado de revisão com suporte a case-sensitive."""
        conditions = []
        params = []
        
        if query:
            if case_sensitive:
                if field == "source":
                    conditions.append("instr(source, ?) > 0")
                    params.append(query)
                elif field == "target":
                    conditions.append("instr(target, ?) > 0")
                    params.append(query)
                else:
                    conditions.append("(instr(source, ?) > 0 OR instr(target, ?) > 0)")
                    params.extend([query, query])
            else:
                q = f"%{query.lower()}%"
                if field == "source":
                    conditions.append("lower(source) LIKE ?")
                    params.append(q)
                elif field == "target":
                    conditions.append("lower(target) LIKE ?")
                    params.append(q)
                else:
                    conditions.append("(lower(source) LIKE ? OR lower(target) LIKE ?)")
                    params.extend([q, q])
                
        if state and state.lower() not in ("all", "all segments", ""):
            st = state.lower()
            if st in ("untranslated", "not translated"):
                conditions.append("(state = 'untranslated' OR state IS NULL OR state = '')")
            else:
                conditions.append("state = ?")
                params.append(st)
            
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT id FROM segments {where} ORDER BY segment_order, id"
        rows = self.conn.execute(sql, params).fetchall()
        return [r["id"] for r in rows]

    def apply_advanced_filter(self, criteria) -> list[int]:
        """Filtra IDs usando o motor Advanced Display Filter 2.0."""
        from core.advanced_filter import apply_advanced_filter
        return apply_advanced_filter(self.conn, criteria)

    def search_ids(self, query: str = "", field: str = "both") -> list[int]:
        q = f"%{query}%"
        if not query:
            rows = self.conn.execute("SELECT id FROM segments ORDER BY id").fetchall()
        elif field == "source":
            rows = self.conn.execute(
                "SELECT id FROM segments WHERE source LIKE ? ORDER BY id", (q,)
            ).fetchall()
        elif field == "target":
            rows = self.conn.execute(
                "SELECT id FROM segments WHERE target LIKE ? ORDER BY id", (q,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id FROM segments WHERE source LIKE ? OR target LIKE ? ORDER BY id",
                (q, q),
            ).fetchall()
        return [r["id"] for r in rows]

    def bulk_replace(self, find: str, repl: str, field: str = "target",
                     case_sensitive: bool = False, use_regex: bool = False,
                     only_ids: list[int] | None = None) -> int:
        import re

        def make_pattern():
            pat = find if use_regex else re.escape(find)
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.compile(pat, flags)

        rx = make_pattern()
        col = "source" if field == "source" else "target"
        tags_column = "source_tags" if col == "source" else "target_tags"
        cur = self.conn.cursor()
        
        if only_ids is not None:
            ph = ",".join("?" * len(only_ids)) or "NULL"
            sql = (
                f"SELECT id,{col} AS txt,source,target,source_tags,target_tags "
                f"FROM segments WHERE id IN ({ph})"
            )
            params: list = list(only_ids)
        else:
            sql = f"SELECT id,{col} AS txt,source,target,source_tags,target_tags FROM segments"
            params = []

        cur.execute(sql, params)
        changed = 0
        upd = self.conn.cursor()
        
        while True:
            rows = cur.fetchmany(5000)
            if not rows:
                break
                
            for r in rows:
                txt = r["txt"] or ""
                visible = display_text(txt)
                new_visible = rx.sub(repl, visible)
                
                if new_visible != visible:
                    tags = _decode_tags(r[tags_column])
                    previous = txt
                    if col == "target" and not tags:
                        tags = _decode_tags(r["source_tags"])
                        if tags:
                            previous = r["source"] or ""
                    stored = merge_inline_tokens(new_visible, previous, tags)
                    upd.execute(
                        f"UPDATE segments SET {col}=?,{tags_column}=? WHERE id=?",
                        (stored, _encode_tags(tags), r["id"]),
                    )
                    changed += 1
                    
        self.conn.commit()
        return changed

    def set_state(self, ids: list[int], state: SegState) -> int:
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        cur = self.conn.execute(
            f"UPDATE segments SET state=? WHERE id IN ({ph})",
            [state.value, *ids],
        )
        self.conn.commit()
        return cur.rowcount

    def delete_ids(self, ids: list[int]) -> int:
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        cur = self.conn.execute(f"DELETE FROM segments WHERE id IN ({ph})", ids)
        self.conn.commit()
        return cur.rowcount

    def get_row(self, seg_id_row: int) -> Optional[Segment]:
        r = self.conn.execute("SELECT * FROM segments WHERE id=?", (seg_id_row,)).fetchone()
        return self._to_segment(r) if r else None

    def page(self, offset: int, limit: int = 100) -> List[Segment]:
        rows = self.conn.execute(
            "SELECT * FROM segments ORDER BY segment_order, id LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [self._to_segment(r) for r in rows]

    def exact_match(self, source: str) -> Optional[Segment]:
        r = self.conn.execute(
            "SELECT * FROM segments WHERE source=? AND target IS NOT NULL AND target<>''"
            " ORDER BY percent DESC LIMIT 1", (source,)
        ).fetchone()
        return self._to_segment(r) if r else None

    def concordance(self, query: str, limit: int = 50) -> List[Segment]:
        if self._fts_ok:
            try:
                rows = self.conn.execute(
                    "SELECT s.* FROM segments s JOIN seg_fts f ON s.id=f.rowid "
                    "WHERE seg_fts MATCH ? LIMIT ?", (self._fts_escape(query), limit)
                ).fetchall()
                return [self._to_segment(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        
        rows = self.conn.execute(
            "SELECT * FROM segments WHERE source LIKE ? OR target LIKE ? LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [self._to_segment(r) for r in rows]

    @staticmethod
    def _fts_escape(q: str) -> str:
        return '"' + q.replace('"', '""') + '"'

    def _to_segment(self, r: sqlite3.Row) -> Segment:
        return Segment(
            source=r["source"], target=r["target"] or "",
            tu_id=r["tu_id"] or "", seg_id=r["seg_id"] or "",
            row_id=r["id"],
            state=SegState(r["state"]), origin=SegOrigin(r["origin"]),
            percent=r["percent"] or 0,
            source_tags=_decode_tags(r["source_tags"]),
            target_tags=_decode_tags(r["target_tags"]),
            order=r["segment_order"],
        )

    def merge_segments(self, row_id1: int, row_id2: int) -> Optional[int]:
        """Mescla dois segmentos adjacentes, reunificando sentenças quebradas indevidamente."""
        r1 = self.conn.execute("SELECT * FROM segments WHERE id=?", (row_id1,)).fetchone()
        r2 = self.conn.execute("SELECT * FROM segments WHERE id=?", (row_id2,)).fetchone()
        if not r1 or not r2:
            return None

        src1 = r1["source"] or ""
        src2 = r2["source"] or ""
        sep_src = "" if src1.endswith(("-", "—", "/")) else " "
        merged_source = f"{src1}{sep_src}{src2}".strip()

        tgt1 = r1["target"] or ""
        tgt2 = r2["target"] or ""
        if tgt1 and tgt2:
            sep_tgt = "" if tgt1.endswith(("-", "—", "/")) else " "
            merged_target = f"{tgt1}{sep_tgt}{tgt2}".strip()
        elif tgt1:
            merged_target = tgt1
        else:
            merged_target = tgt2

        tags1 = _decode_tags(r1["source_tags"])
        tags2 = _decode_tags(r2["source_tags"])
        merged_source_tags = _encode_tags(tags1 + tags2)

        ttags1 = _decode_tags(r1["target_tags"])
        ttags2 = _decode_tags(r2["target_tags"])
        merged_target_tags = _encode_tags(ttags1 + ttags2)

        new_state = r1["state"] if r1["state"] != SegState.UNTRANSLATED.value else r2["state"]
        if merged_target and new_state == SegState.UNTRANSLATED.value:
            new_state = SegState.TRANSLATED.value

        self.conn.execute(
            "UPDATE segments SET source=?, target=?, source_tags=?, target_tags=?, state=? WHERE id=?",
            (merged_source, merged_target, merged_source_tags, merged_target_tags, new_state, row_id1)
        )
        self.conn.execute("DELETE FROM segments WHERE id=?", (row_id2,))
        self.conn.commit()
        return row_id1

    def split_segment(self, row_id: int, split_char_index: int) -> Optional[tuple[int, int]]:
        """Divide um segmento em dois na posição especificada do cursor."""
        r = self.conn.execute("SELECT * FROM segments WHERE id=?", (row_id,)).fetchone()
        if not r:
            return None

        src = r["source"] or ""
        if split_char_index <= 0 or split_char_index >= len(src):
            return None

        part1_src = src[:split_char_index].strip()
        part2_src = src[split_char_index:].strip()

        self.conn.execute("UPDATE segments SET source=? WHERE id=?", (part1_src, row_id))

        current_order = r["segment_order"]
        self.conn.execute(
            "UPDATE segments SET segment_order = segment_order + 1 WHERE segment_order > ?",
            (current_order,)
        )

        cur = self.conn.execute(
            "INSERT INTO segments(tu_id, seg_id, source, target, state, origin, percent, srclang, tgtlang, segment_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["tu_id"], f"{r['seg_id']}_b" if r["seg_id"] else "",
                part2_src, "", SegState.UNTRANSLATED.value,
                r["origin"], 0, r["srclang"], r["tgtlang"], current_order + 1
            )
        )
        self.conn.commit()
        return row_id, cur.lastrowid

    def heal_broken_segmentation(self) -> int:
        """Examina e cura automaticamente quebras de sentenças indevidas em toda a TM."""
        from core.segmenter import SmartSentenceSegmenter
        all_segs = list(self.iter_all(batch=50000))
        healed_segs, count = SmartSentenceSegmenter.heal_broken_segments(all_segs)
        if count > 0:
            self.conn.execute("DELETE FROM segments")
            self.add_many(healed_segs, self.langs()[0], self.langs()[1])
            self.rebuild_fts()
        return count

    def close(self) -> None:
        self.conn.close()

def _encode_tags(tags: list[InlineTag]) -> str:
    return json.dumps(
        [{"code": tag.code, "placeholder": tag.placeholder} for tag in tags],
        ensure_ascii=False,
    )

def _decode_tags(value: str | None) -> list[InlineTag]:
    if not value or not str(value).strip():
        return []
    try:
        raw = json.loads(value)
        if not isinstance(raw, list):
            return []
        return [InlineTag(**item) for item in raw if isinstance(item, dict)]
    except Exception:
        return []