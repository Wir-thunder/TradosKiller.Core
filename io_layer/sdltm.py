"""
io_layer.sdltm - Parser e Escritor de Translation Memory do SDL Trados Studio (.sdltm).

O formato .sdltm é uma base de dados SQLite com esquema específico do RWS Trados:
  - translation_memories: metadados da TM (idiomas, nome, configurações)
  - translation_units: pares fonte/alvo armazenados em XML proprietário (<Segment><Elements>...)
  - parameters, attributes, fuzzy_index, etc.

Este módulo permite:
  - Detectar os idiomas da TM (.sdltm)
  - Ler segmentos em streaming (iter_sdltm)
  - Converter o XML interno da RWS para texto limpo e InlineTags
  - Exportar TMs para o formato .sdltm compatível com o SDL Trados Studio
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
import zlib
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, Tuple
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from core.segment import Segment, SegState, SegOrigin, InlineTag, inline_token, TOKEN_REGEX, display_text


def detect_sdltm_langs(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Detecta os idiomas de origem e destino configurados na base .sdltm."""
    if not os.path.exists(path):
        return None, None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT source_language, target_language FROM translation_memories LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0], row[1]
    except Exception:
        pass
    return None, None


def parse_sdltm_segment_xml(xml_content: str) -> Tuple[str, list[InlineTag]]:
    """
    Converte o XML <Segment><Elements>... do Trados para texto com tokens internos e lista de InlineTag.
    """
    if not xml_content:
        return "", []

    try:
        root = ET.fromstring(xml_content)
    except Exception:
        return xml_content, []

    elements = root.find("Elements")
    if elements is None:
        # Se não tiver Elements, tenta pegar todos os Values
        values = [v.text for v in root.findall(".//Value") if v.text]
        return "".join(values), []

    parts: list[str] = []
    tags: list[InlineTag] = []
    idx = 0

    for el in elements:
        tag_name = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag_name == "Text":
            val_el = el.find("Value")
            if val_el is not None and val_el.text:
                parts.append(val_el.text)
        elif tag_name == "Tag":
            idx += 1
            tok = inline_token(idx)
            raw_tag_xml = ET.tostring(el, encoding="unicode").strip()
            tags.append(InlineTag(code=raw_tag_xml, placeholder=tok))
            parts.append(tok)
        else:
            # Outros tipos de elementos como placeholders ou sub-estruturas
            val_el = el.find("Value")
            if val_el is not None and val_el.text:
                parts.append(val_el.text)

    return "".join(parts), tags


def build_sdltm_segment_xml(text: str, tags: list[InlineTag], culture: str = "en-US") -> str:
    """
    Gera a representação XML <Segment><Elements>... a partir de texto com tokens e lista de InlineTag.
    """
    xml_parts = [
        '<Segment xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema"><Elements>'
    ]

    tag_map = {tag.placeholder: tag.code for tag in tags}
    last_end = 0

    tag_counter = 1
    for match in TOKEN_REGEX.finditer(text):
        token_str = match.group(0)
        plain = text[last_end:match.start()]
        if plain:
            xml_parts.append(f"<Text><Value>{escape(plain)}</Value></Text>")

        if token_str in tag_map:
            code = tag_map[token_str]
            # Se já for um <Tag> do Trados, usa-o diretamente
            if code.startswith("<Tag") and code.endswith("</Tag>"):
                xml_parts.append(code)
            else:
                # Transforma tag genérica em estrutura de Tag válida do Trados
                xml_parts.append(
                    f"<Tag><Type>Standalone</Type><Anchor>{tag_counter}</Anchor>"
                    f"<AlignmentAnchor>{tag_counter}</AlignmentAnchor>"
                    f"<TagID>{tag_counter}</TagID><CanHide>false</CanHide></Tag>"
                )
                tag_counter += 1
        last_end = match.end()

    trailing = text[last_end:]
    if trailing:
        xml_parts.append(f"<Text><Value>{escape(trailing)}</Value></Text>")

    xml_parts.append(f"</Elements><CultureName>{escape(culture)}</CultureName></Segment>")
    return "".join(xml_parts)


def iter_sdltm(path: str, source_lang: Optional[str] = None, target_lang: Optional[str] = None) -> Iterator[Segment]:
    """
    Gera Segment por unidade de tradução a partir de um ficheiro .sdltm.
    Executa leitura em streaming (fetchmany) para não carregar a base toda em RAM.
    """
    detected_src, detected_tgt = detect_sdltm_langs(path)
    src_culture = source_lang or detected_src or "en-US"
    tgt_culture = target_lang or detected_tgt or "pt-BR"

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT id, guid, source_segment, target_segment, creation_date, change_date "
        "FROM translation_units ORDER BY id"
    )

    batch_size = 1000
    order = 0

    while True:
        rows = cur.fetchmany(batch_size)
        if not rows:
            break

        for r in rows:
            tu_id = str(r["id"])
            src_raw = r["source_segment"] or ""
            tgt_raw = r["target_segment"] or ""

            src_txt, src_tags = parse_sdltm_segment_xml(src_raw)
            tgt_txt, tgt_tags = parse_sdltm_segment_xml(tgt_raw)

            state = SegState.TRANSLATED if tgt_txt else SegState.UNTRANSLATED

            yield Segment(
                source=src_txt,
                target=tgt_txt,
                tu_id=tu_id,
                seg_id=tu_id,
                state=state,
                origin=SegOrigin.TM,
                percent=100 if tgt_txt else 0,
                source_tags=src_tags,
                target_tags=tgt_tags,
                order=order,
            )
            order += 1

    conn.close()


def write_sdltm(tm, out_path: str, src_lang: str = "en-US", tgt_lang: str = "pt-BR",
                tm_name: Optional[str] = None) -> int:
    """
    Exporta segmentos da TM para um ficheiro .sdltm compatível com SDL Trados Studio.
    Cria tabelas necessárias, índices e metadados.
    """
    out_file = Path(out_path)
    if out_file.exists():
        out_file.unlink()

    name = tm_name or out_file.stem
    conn = sqlite3.connect(str(out_file))
    cur = conn.cursor()

    # Criação do esquema compatível com Trados Studio
    cur.executescript("""
        CREATE TABLE translation_memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            guid BLOB NOT NULL,
            name TEXT NOT NULL UNIQUE,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            copyright TEXT,
            description TEXT,
            settings INT NOT NULL,
            creation_user TEXT NOT NULL,
            creation_date DATETIME NOT NULL,
            expiration_date DATETIME,
            fuzzy_indexes INT NOT NULL,
            last_recompute_date DATETIME,
            last_recompute_size INT,
            flags INT NOT NULL DEFAULT 0,
            tucount INT NOT NULL DEFAULT 0,
            fga_support int not null default 1,
            data_version INTEGER NOT NULL DEFAULT 1,
            text_context_match_type INTEGER NOT NULL DEFAULT 1,
            id_context_match BIT DEFAULT 0
        );

        CREATE TABLE parameters(
            translation_memory_id INT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL
        );

        CREATE TABLE translation_units(
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            guid BLOB NOT NULL,
            translation_memory_id INT NOT NULL,
            source_hash INTEGER,
            source_segment TEXT,
            target_hash INTEGER,
            target_segment TEXT,
            creation_date DATETIME NOT NULL,
            creation_user TEXT NOT NULL,
            change_date DATETIME NOT NULL,
            change_user TEXT NOT NULL,
            last_used_date DATETIME NOT NULL,
            last_used_user TEXT NOT NULL,
            usage_counter INT NOT NULL,
            flags INT,
            source_token_data BLOB,
            target_token_data BLOB,
            alignment_data BLOB,
            align_model_date DATETIME,
            insert_date DATETIME,
            tokenization_sig_hash INTEGER
        );

        CREATE INDEX idx_tu_tm ON translation_units(translation_memory_id);
    """)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tm_guid = uuid.uuid4().bytes

    cur.execute(
        """
        INSERT INTO translation_memories (
            id, guid, name, source_language, target_language, settings,
            creation_user, creation_date, fuzzy_indexes, flags, tucount
        ) VALUES (1, ?, ?, ?, ?, 63, 'CAT Tool', ?, 7, 0, 0)
        """,
        (tm_guid, name, src_lang, tgt_lang, now_str)
    )

    cur.executemany(
        "INSERT INTO parameters (translation_memory_id, name, value) VALUES (?, ?, ?)",
        [
            (None, "FREQUENCYTOP", "1000"),
            (None, "VERSION", "8.06"),
            (None, "TokenDataVersion", "1"),
            (None, "AlignmentDataVersion", "1"),
            (None, "VERSION_CREATED", "8.10"),
        ]
    )

    count = 0
    batch_rows = []

    for seg in tm.iter_all():
        tu_guid = uuid.uuid4().bytes
        src_xml = build_sdltm_segment_xml(seg.source, seg.source_tags, src_lang)
        tgt_xml = build_sdltm_segment_xml(seg.target, seg.target_tags, tgt_lang) if seg.target else ""

        src_hash = zlib.crc32(seg.source.encode("utf-8"))
        tgt_hash = zlib.crc32(seg.target.encode("utf-8")) if seg.target else 0

        batch_rows.append((
            tu_guid, 1, src_hash, src_xml, tgt_hash, tgt_xml,
            now_str, "CAT Tool", now_str, "CAT Tool", now_str, "CAT Tool", 0, 1, now_str
        ))
        count += 1

        if len(batch_rows) >= 1000:
            cur.executemany(
                """
                INSERT INTO translation_units (
                    guid, translation_memory_id, source_hash, source_segment,
                    target_hash, target_segment, creation_date, creation_user,
                    change_date, change_user, last_used_date, last_used_user,
                    usage_counter, flags, insert_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch_rows
            )
            batch_rows.clear()

    if batch_rows:
        cur.executemany(
            """
            INSERT INTO translation_units (
                guid, translation_memory_id, source_hash, source_segment,
                target_hash, target_segment, creation_date, creation_user,
                change_date, change_user, last_used_date, last_used_user,
                usage_counter, flags, insert_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch_rows
        )

    cur.execute("UPDATE translation_memories SET tucount = ? WHERE id = 1", (count,))
    conn.commit()
    conn.close()

    return count


def insert_or_update_sdltm_unit(sdltm_path: str, source: str, target: str,
                                src_lang: str = "en-US", tgt_lang: str = "pt-PT") -> bool:
    """Insere ou atualiza uma unidade de tradução na base nativa .sdltm do Trados."""
    if not os.path.exists(sdltm_path):
        return False
    try:
        conn = sqlite3.connect(sdltm_path)
        cur = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        src_xml = build_sdltm_segment_xml(source, [], src_lang)
        tgt_xml = build_sdltm_segment_xml(target, [], tgt_lang)
        src_hash = zlib.crc32(source.encode("utf-8"))
        tgt_hash = zlib.crc32(target.encode("utf-8"))

        row = cur.execute(
            "SELECT id FROM translation_units WHERE source_hash = ? LIMIT 1", (src_hash,)
        ).fetchone()

        if row:
            tu_id = row[0]
            cur.execute(
                """
                UPDATE translation_units
                SET target_hash = ?, target_segment = ?, change_date = ?, last_used_date = ?,
                    usage_counter = usage_counter + 1
                WHERE id = ?
                """,
                (tgt_hash, tgt_xml, now_str, now_str, tu_id)
            )
        else:
            tu_guid = uuid.uuid4().bytes
            cur.execute(
                """
                INSERT INTO translation_units (
                    guid, translation_memory_id, source_hash, source_segment,
                    target_hash, target_segment, creation_date, creation_user,
                    change_date, change_user, last_used_date, last_used_user,
                    usage_counter, flags, insert_date
                ) VALUES (?, 1, ?, ?, ?, ?, ?, 'CAT Tool', ?, 'CAT Tool', ?, 'CAT Tool', 1, 1, ?)
                """,
                (tu_guid, src_hash, src_xml, tgt_hash, tgt_xml, now_str, now_str, now_str, now_str)
            )
            cur.execute("UPDATE translation_memories SET tucount = tucount + 1 WHERE id = 1")

        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def create_empty_sdltm(path: str, src_lang: str = "en-US", tgt_lang: str = "pt-PT", name: str = "") -> str:
    """Cria uma nova base de memória .sdltm vazia pronta para uso no Trados Studio."""
    out_file = Path(path)
    if out_file.exists():
        out_file.unlink()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    tm_name = name or out_file.stem
    conn = sqlite3.connect(str(out_file))
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE translation_memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            guid BLOB NOT NULL,
            name TEXT NOT NULL UNIQUE,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            copyright TEXT,
            description TEXT,
            settings INT NOT NULL,
            creation_user TEXT NOT NULL,
            creation_date DATETIME NOT NULL,
            expiration_date DATETIME,
            fuzzy_indexes INT NOT NULL,
            last_recompute_date DATETIME,
            last_recompute_size INT,
            flags INT NOT NULL DEFAULT 0,
            tucount INT NOT NULL DEFAULT 0,
            fga_support int not null default 1,
            data_version INTEGER NOT NULL DEFAULT 1,
            text_context_match_type INTEGER NOT NULL DEFAULT 1,
            id_context_match BIT DEFAULT 0
        );

        CREATE TABLE parameters(
            translation_memory_id INT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL
        );

        CREATE TABLE translation_units(
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            guid BLOB NOT NULL,
            translation_memory_id INT NOT NULL,
            source_hash INTEGER,
            source_segment TEXT,
            target_hash INTEGER,
            target_segment TEXT,
            creation_date DATETIME NOT NULL,
            creation_user TEXT NOT NULL,
            change_date DATETIME NOT NULL,
            change_user TEXT NOT NULL,
            last_used_date DATETIME NOT NULL,
            last_used_user TEXT NOT NULL,
            usage_counter INT NOT NULL,
            flags INT,
            source_token_data BLOB,
            target_token_data BLOB,
            alignment_data BLOB,
            align_model_date DATETIME,
            insert_date DATETIME,
            tokenization_sig_hash INTEGER
        );

        CREATE INDEX idx_tu_tm ON translation_units(translation_memory_id);
    """)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tm_guid = uuid.uuid4().bytes

    cur.execute(
        """
        INSERT INTO translation_memories (
            id, guid, name, source_language, target_language, settings,
            creation_user, creation_date, fuzzy_indexes, flags, tucount
        ) VALUES (1, ?, ?, ?, ?, 63, 'CAT Tool', ?, 7, 0, 0)
        """,
        (tm_guid, tm_name, src_lang, tgt_lang, now_str)
    )

    cur.executemany(
        "INSERT INTO parameters (translation_memory_id, name, value) VALUES (?, ?, ?)",
        [
            (None, "FREQUENCYTOP", "1000"),
            (None, "VERSION", "8.06"),
            (None, "TokenDataVersion", "1"),
            (None, "AlignmentDataVersion", "1"),
            (None, "VERSION_CREATED", "8.10"),
        ]
    )

    conn.commit()
    conn.close()
    return path
