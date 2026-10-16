"""
io_layer.sdlxliff - parser SDLXLIFF em STREAMING (lxml.iterparse).

Estrutura validada em ficheiros reais do Trados Studio 16:
  - default NS: urn:oasis:names:tc:xliff:document:1.2  (XLIFF 1.2)
  - sdl NS:     http://sdl.com/FileTypes/SdlXliff/1.0
  - trans-unit/@id = GUID; segmentacao via <seg-source><mrk mtype="seg" mid=N">
  - estado em <sdl:seg conf=... origin=... percent=...>

Regra anti-crash:
  - iterparse por <trans-unit>; limpa cada no apos processar.
  - o <internal-file form="base64"> gigante NUNCA e mantido em RAM
    (esta no <header>, fora do <body>; anyway nao o lemos).
"""
from __future__ import annotations

from typing import Iterator, Optional

from lxml import etree as ET

from core.segment import Segment, SegState, SegOrigin, InlineTag, inline_token, display_text

XLIFF = "urn:oasis:names:tc:xliff:document:1.2"
SDL = "http://sdl.com/FileTypes/SdlXliff/1.0"
N = {"x": XLIFF, "sdl": SDL}

_CONF_MAP = {
    "unspecified": SegState.UNTRANSLATED,
    "draft": SegState.DRAFT,
    "translated": SegState.TRANSLATED,
    "approvedtranslation": SegState.APPROVED,
    "approvedsignoff": SegState.APPROVED,
    "approved": SegState.APPROVED,
    "signedoff": SegState.APPROVED,
    "signed off": SegState.APPROVED,
    "rejected": SegState.REJECTED,
    "rejectedtranslation": SegState.REJECTED,
    "rejectedsignoff": SegState.REJECTED,
}
_ORIGIN_MAP = {
    "tm": SegOrigin.TM,
    "mt": SegOrigin.MT,
    "interactive": SegOrigin.INTERACTIVE,
    "manual": SegOrigin.MANUAL,
    "auto-propagated": SegOrigin.AUTO,
    "automatedtranslation": SegOrigin.MT,
}


def _map_conf(v: Optional[str]) -> SegState:
    if not v:
        return SegState.UNTRANSLATED
    return _CONF_MAP.get(v.strip().lower(), SegState.UNTRANSLATED)


def _map_origin(v: Optional[str]) -> SegOrigin:
    if not v:
        return SegOrigin.NONE
    return _ORIGIN_MAP.get(v.strip().lower(), SegOrigin.NONE)


def _mrk_text_with_tags(mrk) -> tuple[str, list[InlineTag]]:
    """Texto de um <mrk>, preservando tags filhas (ph/g/x) como placeholders."""
    parts: list[str] = []
    tags: list[InlineTag] = []
    idx = 0

    def add_child(child) -> None:
        nonlocal idx
        if not isinstance(child.tag, str):
            if child.tail:
                parts.append(child.tail)
            return
        name = ET.QName(child).localname
        if name in {"g", "hi"} and (child.text or len(child)):
            markup = ET.tostring(child, encoding="unicode", with_tail=False).strip()
            end_of_open = markup.find(">")
            start_of_close = markup.rfind("</")
            if end_of_open >= 0 and start_of_close > end_of_open:
                idx += 1
                token = inline_token(idx)
                tags.append(InlineTag(markup[:end_of_open + 1], token))
                parts.append(token)
                if child.text:
                    parts.append(child.text)
                for nested in child:
                    add_child(nested)
                idx += 1
                token = inline_token(idx)
                tags.append(InlineTag(markup[start_of_close:], token))
                parts.append(token)
            else:
                add_as_token(child)
        else:
            add_as_token(child)
        if child.tail:
            parts.append(child.tail)

    def add_as_token(child) -> None:
        nonlocal idx
        idx += 1
        code = ET.tostring(child, encoding="unicode", with_tail=False).strip()
        token = inline_token(idx)
        tags.append(InlineTag(code=code, placeholder=token))
        parts.append(token)

    if mrk.text:
        parts.append(mrk.text)
    for child in mrk:
        add_child(child)
    return "".join(parts), tags


def _seg_defs_meta(tu) -> dict[str, tuple[SegState, SegOrigin, int]]:
    """Le <sdl:seg-defs>/<sdl:seg> -> {seg_id: (state, origin, percent)}."""
    meta: dict[str, tuple[SegState, SegOrigin, int]] = {}
    for seg in tu.findall(".//sdl:seg-defs/sdl:seg", N):
        sid = seg.get("id") or ""
        meta[sid] = (
            _map_conf(seg.get("conf")),
            _map_origin(seg.get("origin")),
            int(seg.get("percent") or 0),
        )
    return meta


def _iter_seg_mrks(container) -> Iterator:
    """Itera os <mrk mtype='seg'> dentro de seg-source/target, por ordem."""
    for mrk in container.findall("x:mrk", N):
        if (mrk.get("mtype") or "") == "seg":
            yield mrk


def iter_sdlxliff(path: str) -> Iterator[Segment]:
    """
    Gera Segment por cada <mrk mtype='seg'> (verdadeira unidade de traducao).
    Um trans-unit pode gerar varios segmentos.
    """
    ctx = ET.iterparse(path, events=("end",), tag=("{%s}trans-unit" % XLIFF,))
    order = 0
    for _, tu in ctx:
        tu_id = tu.get("id") or ""
        meta = _seg_defs_meta(tu)

        seg_source = tu.find("x:seg-source", N)
        target = tu.find("x:target", N)

        # indexar targets por mid para emparelhar
        tgt_by_mid = {}
        if target is not None:
            for mrk in _iter_seg_mrks(target):
                tgt_by_mid[mrk.get("mid") or ""] = mrk

        src_mrks = list(_iter_seg_mrks(seg_source)) if seg_source is not None else []
        if src_mrks:
                src_txt, src_tags = _mrk_text_with_tags(mrk)
                if not display_text(src_txt).strip():
                    continue
                tgt_mrk = tgt_by_mid.get(mid)
                tgt_txt, tgt_tags = _mrk_text_with_tags(tgt_mrk) if tgt_mrk is not None else ("", [])
                if mid in meta:
                    state, origin, percent = meta[mid]
                else:
                    state = SegState.TRANSLATED if tgt_txt.strip() else SegState.UNTRANSLATED
                    origin = SegOrigin.NONE
                    percent = 0
                yield Segment(
                    source=src_txt, target=tgt_txt, tu_id=tu_id, seg_id=mid,
                    state=state, origin=origin, percent=percent,
                    source_tags=src_tags, target_tags=tgt_tags, order=order,
                )
                order += 1
        else:
            # sem seg-source: usar source/target simples (XLIFF puro)
            # Ignora nós estruturais do Trados que contêm apenas tags/placeholders ou translate="no"
            if tu.get("translate") != "no":
                src_txt, src_tags = _plain(tu.find("x:source", N))
                if display_text(src_txt).strip():
                    tgt_txt, tgt_tags = _plain(tu.find("x:target", N))
                    state = SegState.TRANSLATED if tgt_txt.strip() else SegState.UNTRANSLATED
                    yield Segment(
                        source=src_txt, target=tgt_txt, tu_id=tu_id, seg_id="",
                        state=state, source_tags=src_tags, target_tags=tgt_tags, order=order,
                    )
                    order += 1

        tu.clear()
        while tu.getprevious() is not None:
            del tu.getparent()[0]


def _plain(el) -> tuple[str, list[InlineTag]]:
    if el is None:
        return "", []
    if len(el) == 0:
        return (el.text or ""), []
    return _mrk_text_with_tags(el)


def detect_sdlxliff_langs(path: str) -> tuple[Optional[str], Optional[str]]:
    """Le o 1.o <file> para source/target language de forma instantânea sem ler ficheiro inteiro."""
    import re
    # 1. Leitura ultra-rápida dos primeiros 64KB (instantâneo mesmo em ficheiros de 500MB)
    try:
        with open(path, "rb") as fp:
            header_chunk = fp.read(65536).decode("utf-8", errors="ignore")
            m_src = re.search(r'source-language=["\']([^"\']+)', header_chunk)
            m_tgt = re.search(r'target-language=["\']([^"\']+)', header_chunk)
            if m_src and m_tgt:
                return m_src.group(1), m_tgt.group(1)
            elif m_src:
                return m_src.group(1), None
    except Exception:
        pass

    # 2. Fallback: iterparse com evento "start" (para logo no primeiro <file>)
    try:
        ctx = ET.iterparse(path, events=("start",), tag=("{%s}file" % XLIFF))
        for _, f in ctx:
            src = f.get("source-language")
            tgt = f.get("target-language")
            del ctx
            return src, tgt
    except Exception:
        pass

    return None, None

