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


import re


SDLTM_FULL_SCHEMA = """
CREATE TABLE IF NOT EXISTS fuzzy_index1(
    translation_memory_id INT NOT NULL CONSTRAINT FK_fi1_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
    feature TEXT NOT NULL,
    length INT NOT NULL,
    translation_unit_id INT NOT NULL
);
CREATE INDEX IF NOT EXISTS fi1_tuid ON fuzzy_index1(translation_unit_id);

CREATE TABLE IF NOT EXISTS fuzzy_index2(
    translation_memory_id INT NOT NULL CONSTRAINT FK_fi2_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
    feature TEXT NOT NULL,
    length INT NOT NULL,
    translation_unit_id INT NOT NULL
);
CREATE INDEX IF NOT EXISTS fi2_tuid ON fuzzy_index2(translation_unit_id);

CREATE TABLE IF NOT EXISTS fuzzy_index4(
    translation_memory_id INT NOT NULL CONSTRAINT FK_fi4_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
    feature TEXT NOT NULL,
    length INT NOT NULL,
    translation_unit_id INT NOT NULL
);
CREATE INDEX IF NOT EXISTS fi4_tuid ON fuzzy_index4(translation_unit_id);

CREATE TABLE IF NOT EXISTS resources(
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    guid BLOB NOT NULL,
    type INT NOT NULL,
    language TEXT,
    data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_Resources1 ON resources (type, language);
CREATE INDEX IF NOT EXISTS idx_Resources2 ON resources (id);

CREATE TABLE IF NOT EXISTS tm_resources(
    tm_id INT NOT NULL CONSTRAINT FK_tr_t REFERENCES translation_memories(id) ON DELETE CASCADE,
    resource_id INT NOT NULL CONSTRAINT FK_tr_r REFERENCES resources(id) ON DELETE CASCADE,
    CONSTRAINT PK_tr PRIMARY KEY (tm_id, resource_id)
);

CREATE TABLE IF NOT EXISTS translation_memories(
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

CREATE TABLE IF NOT EXISTS parameters(
    translation_memory_id INT NULL CONSTRAINT FK_p_tm REFERENCES translation_memories ON DELETE CASCADE,
    name TEXT NOT NULL,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS p_main ON parameters(translation_memory_id, name);

CREATE TABLE IF NOT EXISTS translation_units(
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    guid BLOB NOT NULL,
    translation_memory_id INT NOT NULL CONSTRAINT FK_tu_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS tus_main ON translation_units(translation_memory_id, source_hash);
CREATE INDEX IF NOT EXISTS idx_tus_align_model_date ON translation_units(align_model_date);
CREATE INDEX IF NOT EXISTS idx_tus_insert_dates ON translation_units(insert_date);
CREATE INDEX IF NOT EXISTS idx_tus_toksighash ON translation_units(tokenization_sig_hash);

CREATE TABLE IF NOT EXISTS translation_unit_contexts(
    translation_unit_id INT NOT NULL CONSTRAINT FK_tuc_tu REFERENCES translation_units(id) ON DELETE CASCADE,
    left_source_context INTEGER NOT NULL,
    left_target_context INTEGER NOT NULL,
    CONSTRAINT PK_tuc PRIMARY KEY (translation_unit_id, left_source_context, left_target_context)
);
CREATE INDEX IF NOT EXISTS idx_translation_unit_contexts ON translation_unit_contexts (translation_unit_id);
CREATE INDEX IF NOT EXISTS idx_ctx1 ON translation_unit_contexts(left_source_context);
CREATE INDEX IF NOT EXISTS idx_ctx2 ON translation_unit_contexts(left_target_context);

CREATE TABLE IF NOT EXISTS attributes(
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    guid BLOB NOT NULL,
    name TEXT NOT NULL,
    type INT NOT NULL,
    tm_id INT NOT NULL,
    CONSTRAINT CK_a UNIQUE (name, tm_id)
);
CREATE INDEX IF NOT EXISTS idx_attributes1 ON attributes (tm_id);
CREATE INDEX IF NOT EXISTS idx_attributes2 ON attributes (name, type);

CREATE TABLE IF NOT EXISTS string_attributes(
    translation_unit_id INT NOT NULL CONSTRAINT FK_sa_tu REFERENCES translation_units(id) ON DELETE CASCADE,
    attribute_id INT NOT NULL CONSTRAINT FK_sa_a REFERENCES attributes(id) ON DELETE CASCADE,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_string_attributes ON string_attributes (translation_unit_id, attribute_id);

CREATE TABLE IF NOT EXISTS numeric_attributes(
    translation_unit_id INT NOT NULL CONSTRAINT FK_na_tu REFERENCES translation_units(id) ON DELETE CASCADE,
    attribute_id INT NOT NULL CONSTRAINT FK_na_a REFERENCES attributes(id) ON DELETE CASCADE,
    value INT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_numeric_attributes ON numeric_attributes (translation_unit_id, attribute_id);

CREATE TABLE IF NOT EXISTS date_attributes(
    translation_unit_id INT NOT NULL CONSTRAINT FK_da_tu REFERENCES translation_units(id) ON DELETE CASCADE,
    attribute_id INT NOT NULL CONSTRAINT FK_da_a REFERENCES attributes(id) ON DELETE CASCADE,
    value DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_date_attributes ON date_attributes (translation_unit_id, attribute_id);

CREATE TABLE IF NOT EXISTS picklist_values(
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    guid BLOB NOT NULL,
    attribute_id INT NOT NULL CONSTRAINT FK_pv_a REFERENCES attributes(id) ON DELETE CASCADE,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS picklist_attributes(
    translation_unit_id INT NOT NULL CONSTRAINT FK_pa_tu REFERENCES translation_units(id) ON DELETE CASCADE,
    picklist_value_id INT NOT NULL CONSTRAINT FK_pa_pv REFERENCES picklist_values(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_picklist_attributes ON picklist_attributes (translation_unit_id);

CREATE TABLE IF NOT EXISTS fuzzy_data(
    translation_memory_id INT NOT NULL CONSTRAINT FK_fi1_tm REFERENCES translation_memories(id) ON DELETE CASCADE,
    translation_unit_id INT NOT NULL,
    fi1 TEXT,
    fi2 TEXT,
    fi4 TEXT,
    fi8 TEXT,
    CONSTRAINT PK_fi1 PRIMARY KEY (translation_memory_id, translation_unit_id)
);

CREATE TABLE IF NOT EXISTS vocab_src(id INT NOT NULL, vocab TEXT NOT NULL, freq INT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_vocab_src ON vocab_src (vocab);

CREATE TABLE IF NOT EXISTS vocab_trg(id INT NOT NULL, vocab TEXT NOT NULL, freq INT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_vocab_trg ON vocab_trg (vocab);

CREATE TABLE IF NOT EXISTS vocabfilter(token TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_vocabfilter ON vocabfilter (token);

CREATE TABLE IF NOT EXISTS trans_model(
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    sourcekey INTEGER NOT NULL,
    targetkey INTEGER NOT NULL,
    floatval REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trans_model_sourcekey ON trans_model (sourcekey);
CREATE INDEX IF NOT EXISTS idx_trans_model_targetkey ON trans_model (targetkey);

CREATE TABLE IF NOT EXISTS trans_model_rev(
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    sourcekey INTEGER NOT NULL,
    targetkey INTEGER NOT NULL,
    floatval REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trans_model_rev_sourcekey ON trans_model_rev (sourcekey);
CREATE INDEX IF NOT EXISTS idx_trans_model_rev_targetkey ON trans_model_rev (targetkey);

CREATE TABLE IF NOT EXISTS translation_unit_fragments(
    translation_unit_id INT NOT NULL CONSTRAINT FK_tuf_tu REFERENCES translation_units(id) ON DELETE CASCADE,
    fragment_hash INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tufragments_ids ON translation_unit_fragments(translation_unit_id);
CREATE INDEX IF NOT EXISTS idx_tufragments_hashes ON translation_unit_fragments(fragment_hash);

CREATE TABLE IF NOT EXISTS translation_unit_idcontexts(
    translation_unit_id INT NOT NULL CONSTRAINT FK_translation_unit_idcontexts REFERENCES translation_units(id) ON DELETE CASCADE,
    idcontext TEXT NOT NULL,
    CONSTRAINT PK_tuidc PRIMARY KEY (translation_unit_id, idcontext)
);
CREATE INDEX IF NOT EXISTS idx_tus_idcontexts ON translation_unit_idcontexts(translation_unit_id, idcontext);
"""

DEFAULT_SIG_HASH = 7319895137155145109


def _java_hash(s: str) -> int:
    """Hash inteiro assinado de 32 bits (h = 31 * h + c) usado nos índices fuzzy do SDLTM."""
    h = 0
    for c in s:
        h = (31 * h + ord(c)) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def _compute_fuzzy_features(text: str) -> Tuple[str, int, str, int]:
    """Calcula features de palavras (fi1) e bigramas de caracteres (fi2/fi4) compatíveis com SDLTM."""
    clean = display_text(text).lower()
    words = re.findall(r"\w+", clean, flags=re.UNICODE)
    word_hashes = sorted({_java_hash(w) for w in words if w})
    fi1_str = "|".join(str(x) for x in word_hashes)

    bigrams = set()
    for w in words:
        for i in range(len(w) - 1):
            bg = 31 * ord(w[i]) + ord(w[i + 1])
            bigrams.add(bg)
    sorted_bg = sorted(bigrams)
    fi2_str = "|".join(str(x) for x in sorted_bg)
    return fi1_str, len(word_hashes), fi2_str, len(sorted_bg)


def _build_token_blob(text: str) -> bytes:
    """Gera o BLOB binário source_token_data / target_token_data esperado pelo esquema SDLTM."""
    clean = display_text(text)
    tokens = re.findall(r"\S+|\s+", clean)
    if not tokens:
        return b"\x02\x00\x00"

    buf = bytearray([0x02])
    buf.extend(len(tokens).to_bytes(2, "little"))
    # Primeiro token
    buf.extend(b"\x01\x00\x00\x00")
    buf.append(min(255, len(tokens[0])))

    for tok in tokens[1:]:
        if tok.isspace():
            buf.append(0xAC)
        else:
            buf.append(0x81 if tok[0].isupper() else 0xC1)
            buf.append(min(255, len(tok)))
    return bytes(buf)


def write_sdltm(tm, out_path: str, src_lang: str = "en-US", tgt_lang: str = "pt-BR",
                tm_name: Optional[str] = None) -> int:
    """
    Exporta segmentos da TM para um ficheiro .sdltm 100% compatível com SDL Trados Studio.
    Cria todas as 22 tabelas relacionais, índices fuzzy, BLOBs de tokens e metadados.
    """
    out_file = Path(out_path)
    if out_file.exists():
        out_file.unlink()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    name = tm_name or out_file.stem
    conn = sqlite3.connect(str(out_file))
    cur = conn.cursor()

    cur.executescript(SDLTM_FULL_SCHEMA)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exp_str = "9999-12-31 23:59:59"
    tm_guid = uuid.uuid4().bytes

    cur.execute(
        """
        INSERT INTO translation_memories (
            id, guid, name, source_language, target_language, copyright, description,
            settings, creation_user, creation_date, expiration_date, fuzzy_indexes,
            flags, tucount, fga_support, data_version, text_context_match_type, id_context_match
        ) VALUES (1, ?, ?, ?, ?, '', '', 63, 'CAT Workspace', ?, ?, 7, 0, 0, 1, 1, 1, 0)
        """,
        (tm_guid, name, src_lang, tgt_lang, now_str, exp_str)
    )

    count = 0
    for seg in tm.iter_all():
        tu_guid = uuid.uuid4().bytes
        src_xml = build_sdltm_segment_xml(seg.source, seg.source_tags, src_lang)
        tgt_xml = build_sdltm_segment_xml(seg.target, seg.target_tags, tgt_lang) if seg.target else ""

        src_clean = display_text(seg.source)
        tgt_clean = display_text(seg.target) if seg.target else ""

        src_hash = zlib.crc32(src_clean.encode("utf-8"))
        tgt_hash = zlib.crc32(tgt_clean.encode("utf-8")) if tgt_clean else 0

        src_tok = _build_token_blob(src_clean)
        tgt_tok = _build_token_blob(tgt_clean)

        cur.execute(
            """
            INSERT INTO translation_units (
                guid, translation_memory_id, source_hash, source_segment,
                target_hash, target_segment, creation_date, creation_user,
                change_date, change_user, last_used_date, last_used_user,
                usage_counter, flags, source_token_data, target_token_data,
                insert_date, tokenization_sig_hash
            ) VALUES (?, 1, ?, ?, ?, ?, ?, 'CAT Workspace', ?, 'CAT Workspace', ?, 'CAT Workspace', 0, 1, ?, ?, ?, ?)
            """,
            (tu_guid, src_hash, src_xml, tgt_hash, tgt_xml, now_str, now_str, now_str, src_tok, tgt_tok, now_str, DEFAULT_SIG_HASH)
        )
        tu_id = cur.lastrowid

        fi1_s, fi1_len, fi2_s, fi2_len = _compute_fuzzy_features(src_clean)
        _, _, fi4_s, fi4_len = _compute_fuzzy_features(tgt_clean)

        cur.execute(
            "INSERT OR REPLACE INTO fuzzy_data (translation_memory_id, translation_unit_id, fi1, fi2, fi4, fi8) VALUES (1, ?, ?, ?, ?, NULL)",
            (tu_id, fi1_s, fi2_s, fi4_s)
        )
        if fi1_s:
            cur.execute(
                "INSERT INTO fuzzy_index1 (translation_memory_id, feature, length, translation_unit_id) VALUES (1, ?, ?, ?)",
                (fi1_s, fi1_len, tu_id)
            )
        if fi2_s:
            cur.execute(
                "INSERT INTO fuzzy_index2 (translation_memory_id, feature, length, translation_unit_id) VALUES (1, ?, ?, ?)",
                (fi2_s, fi2_len, tu_id)
            )
        if fi4_s:
            cur.execute(
                "INSERT INTO fuzzy_index4 (translation_memory_id, feature, length, translation_unit_id) VALUES (1, ?, ?, ?)",
                (fi4_s, fi4_len, tu_id)
            )
        cur.execute(
            "INSERT INTO translation_unit_fragments (translation_unit_id, fragment_hash) VALUES (?, ?)",
            (tu_id, src_hash)
        )
        count += 1

    cur.executemany(
        "INSERT INTO parameters (translation_memory_id, name, value) VALUES (?, ?, ?)",
        [
            (None, "FREQUENCYTOP", "1000"),
            (None, "VERSION", "8.06"),
            (None, "LAST_ANALYZE", str(count)),
            (None, "TokenDataVersion", "1"),
            (None, "AlignmentDataVersion", "1"),
            (None, "VERSION_CREATED", "8.10"),
        ]
    )

    cur.execute("UPDATE translation_memories SET tucount = ? WHERE id = 1", (count,))
    conn.commit()
    conn.close()

    return count


def insert_or_update_sdltm_unit(sdltm_path: str, source: str, target: str,
                                src_lang: str = "en-US", tgt_lang: str = "pt-PT") -> bool:
    """Insere ou atualiza uma unidade de tradução na base nativa .sdltm mantendo índices fuzzy e tokens."""
    if not os.path.exists(sdltm_path):
        return False
    try:
        conn = sqlite3.connect(sdltm_path, timeout=10.0)
        cur = conn.cursor()
        # Garante que todas as tabelas do esquema oficial existam
        cur.executescript(SDLTM_FULL_SCHEMA)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        detected_src, detected_tgt = detect_sdltm_langs(sdltm_path)
        s_lang = detected_src or src_lang
        t_lang = detected_tgt or tgt_lang

        src_clean = display_text(source)
        tgt_clean = display_text(target)

        src_xml = build_sdltm_segment_xml(source, [], s_lang)
        tgt_xml = build_sdltm_segment_xml(target, [], t_lang)
        src_hash = zlib.crc32(src_clean.encode("utf-8"))
        tgt_hash = zlib.crc32(tgt_clean.encode("utf-8"))
        src_tok = _build_token_blob(src_clean)
        tgt_tok = _build_token_blob(tgt_clean)

        pat = f"%<Value>{escape(src_clean)}</Value>%"
        row = cur.execute(
            "SELECT id FROM translation_units WHERE source_hash = ? OR source_segment LIKE ? LIMIT 1",
            (src_hash, pat)
        ).fetchone()

        fi1_s, fi1_len, fi2_s, fi2_len = _compute_fuzzy_features(src_clean)
        _, _, fi4_s, fi4_len = _compute_fuzzy_features(tgt_clean)

        if row:
            tu_id = row[0]
            cur.execute(
                """
                UPDATE translation_units
                SET target_hash = ?, target_segment = ?, change_date = ?, last_used_date = ?,
                    usage_counter = usage_counter + 1, target_token_data = ?
                WHERE id = ?
                """,
                (tgt_hash, tgt_xml, now_str, now_str, tgt_tok, tu_id)
            )
            cur.execute("DELETE FROM fuzzy_index4 WHERE translation_unit_id = ?", (tu_id,))
            if fi4_s:
                cur.execute(
                    "INSERT INTO fuzzy_index4 (translation_memory_id, feature, length, translation_unit_id) VALUES (1, ?, ?, ?)",
                    (fi4_s, fi4_len, tu_id)
                )
            cur.execute(
                "INSERT OR REPLACE INTO fuzzy_data (translation_memory_id, translation_unit_id, fi1, fi2, fi4, fi8) VALUES (1, ?, ?, ?, ?, NULL)",
                (tu_id, fi1_s, fi2_s, fi4_s)
            )
        else:
            tu_guid = uuid.uuid4().bytes
            cur.execute(
                """
                INSERT INTO translation_units (
                    guid, translation_memory_id, source_hash, source_segment,
                    target_hash, target_segment, creation_date, creation_user,
                    change_date, change_user, last_used_date, last_used_user,
                    usage_counter, flags, source_token_data, target_token_data,
                    insert_date, tokenization_sig_hash
                ) VALUES (?, 1, ?, ?, ?, ?, ?, 'CAT Workspace', ?, 'CAT Workspace', ?, 'CAT Workspace', 1, 1, ?, ?, ?, ?)
                """,
                (tu_guid, src_hash, src_xml, tgt_hash, tgt_xml, now_str, now_str, now_str, src_tok, tgt_tok, now_str, DEFAULT_SIG_HASH)
            )
            tu_id = cur.lastrowid
            cur.execute("UPDATE translation_memories SET tucount = tucount + 1 WHERE id = 1")
            cur.execute(
                "INSERT OR REPLACE INTO fuzzy_data (translation_memory_id, translation_unit_id, fi1, fi2, fi4, fi8) VALUES (1, ?, ?, ?, ?, NULL)",
                (tu_id, fi1_s, fi2_s, fi4_s)
            )
            if fi1_s:
                cur.execute(
                    "INSERT INTO fuzzy_index1 (translation_memory_id, feature, length, translation_unit_id) VALUES (1, ?, ?, ?)",
                    (fi1_s, fi1_len, tu_id)
                )
            if fi2_s:
                cur.execute(
                    "INSERT INTO fuzzy_index2 (translation_memory_id, feature, length, translation_unit_id) VALUES (1, ?, ?, ?)",
                    (fi2_s, fi2_len, tu_id)
                )
            if fi4_s:
                cur.execute(
                    "INSERT INTO fuzzy_index4 (translation_memory_id, feature, length, translation_unit_id) VALUES (1, ?, ?, ?)",
                    (fi4_s, fi4_len, tu_id)
                )
            cur.execute(
                "INSERT INTO translation_unit_fragments (translation_unit_id, fragment_hash) VALUES (?, ?)",
                (tu_id, src_hash)
            )

        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def create_empty_sdltm(path: str, src_lang: str = "en-US", tgt_lang: str = "pt-PT", name: str = "") -> str:
    """Cria uma nova base de memória .sdltm vazia com o esquema oficial completo pronta para o Trados Studio."""
    out_file = Path(path)
    if out_file.exists():
        out_file.unlink()

    out_file.parent.mkdir(parents=True, exist_ok=True)
    tm_name = name or out_file.stem
    conn = sqlite3.connect(str(out_file))
    cur = conn.cursor()

    cur.executescript(SDLTM_FULL_SCHEMA)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exp_str = "9999-12-31 23:59:59"
    tm_guid = uuid.uuid4().bytes

    cur.execute(
        """
        INSERT INTO translation_memories (
            id, guid, name, source_language, target_language, copyright, description,
            settings, creation_user, creation_date, expiration_date, fuzzy_indexes,
            flags, tucount, fga_support, data_version, text_context_match_type, id_context_match
        ) VALUES (1, ?, ?, ?, ?, '', '', 63, 'CAT Workspace', ?, ?, 7, 0, 0, 1, 1, 1, 0)
        """,
        (tm_guid, tm_name, src_lang, tgt_lang, now_str, exp_str)
    )

    cur.executemany(
        "INSERT INTO parameters (translation_memory_id, name, value) VALUES (?, ?, ?)",
        [
            (None, "FREQUENCYTOP", "1000"),
            (None, "VERSION", "8.06"),
            (None, "LAST_ANALYZE", "0"),
            (None, "TokenDataVersion", "1"),
            (None, "AlignmentDataVersion", "1"),
            (None, "VERSION_CREATED", "8.10"),
        ]
    )

    conn.commit()
    conn.close()
    return path

