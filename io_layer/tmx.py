"""
io_layer.tmx - parser TMX 1.4b em STREAMING (lxml.iterparse).

Nunca carrega a arvore DOM inteira: processa cada <tu> e descarta-a.
Lida com:
  - tuid ausente (gera id incremental, como nos teus ficheiros reais)
  - varias <tuv> por <tu>; escolhe fonte/alvo por xml:lang
  - Level 1 (texto simples) e Level 2 (tags inline <ph>/<bpt>/<ept>/<it>)
"""
from __future__ import annotations

from typing import Iterator, Optional

from lxml import etree as ET

from core.segment import Segment, SegState, InlineTag, inline_token

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# tags inline do TMX Level 2 (conteudo nao traduzivel, so preservar)
_INLINE = {"ph", "bpt", "ept", "it", "hi"}


def _seg_text_with_tags(seg_el) -> tuple[str, list[InlineTag]]:
    """Extrai texto legivel + guarda as tags inline como placeholders."""
    parts: list[str] = []
    tags: list[InlineTag] = []
    idx = 0

    def add_child(child) -> None:
        nonlocal idx
        if not isinstance(child.tag, str):
            if child.tail:
                parts.append(child.tail)
            return
        tag = ET.QName(child).localname
        if tag in {"g", "hi"} and (child.text or len(child)):
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
        elif tag in _INLINE:
            add_as_token(child)
        elif child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)

    def add_as_token(child) -> None:
        nonlocal idx
        idx += 1
        code = ET.tostring(child, encoding="unicode", with_tail=False).strip()
        token = inline_token(idx)
        tags.append(InlineTag(code=code, placeholder=token))
        parts.append(token)

    if seg_el.text:
        parts.append(seg_el.text)
    for child in seg_el:
        add_child(child)
    return "".join(parts), tags


def iter_tmx(path: str, source_lang: Optional[str] = None,
             target_lang: Optional[str] = None) -> Iterator[Segment]:
    """
    Gera Segment por <tu>. Se source/target lang nao dados, infere:
      - fonte  = 1.o idioma encontrado
      - alvo   = 2.o idioma encontrado
    """
    ctx = ET.iterparse(path, events=("end",), tag=("{*}tu",))
    order = 0
    auto_id = 0
    seen_langs: list[str] = []

    for _, tu in ctx:
        tuid = tu.get("tuid") or ""
        tuvs = {}
        for tuv in tu:
            if not isinstance(tuv.tag, str):
                continue
            if ET.QName(tuv).localname != "tuv":
                continue
            lang = tuv.get(XML_LANG) or tuv.get("lang") or ""
            if lang and lang not in seen_langs:
                seen_langs.append(lang)
            seg_el = None
            for c in tuv:
                if isinstance(c.tag, str) and ET.QName(c).localname == "seg":
                    seg_el = c
                    break
            if seg_el is not None:
                tuvs[lang] = _seg_text_with_tags(seg_el)

        src_lang = source_lang or (seen_langs[0] if seen_langs else "")
        tgt_lang = target_lang or (seen_langs[1] if len(seen_langs) > 1 else "")

        if not tuid:
            auto_id += 1
            tuid = f"auto_{auto_id}"

        src_txt, src_tags = tuvs.get(src_lang, ("", []))
        tgt_txt, tgt_tags = tuvs.get(tgt_lang, ("", [])) if tgt_lang else ("", [])

        state = SegState.TRANSLATED if tgt_txt else SegState.UNTRANSLATED
        yield Segment(
            source=src_txt, target=tgt_txt, tu_id=tuid, seg_id=tuid,
            state=state, source_tags=src_tags, target_tags=tgt_tags, order=order,
        )
        order += 1
        # libertar memoria do no processado
        tu.clear()
        while tu.getprevious() is not None:
            del tu.getparent()[0]


def detect_tmx_langs(path: str) -> tuple[Optional[str], Optional[str]]:
    """Le rapido os primeiros <tuv> para descobrir os idiomas presentes."""
    langs: list[str] = []
    ctx = ET.iterparse(path, events=("end",), tag=("{*}tuv",))
    for _, tuv in ctx:
        lang = tuv.get(XML_LANG) or tuv.get("lang")
        if lang and lang not in langs:
            langs.append(lang)
        tuv.clear()
        if len(langs) >= 2:
            break
    return (langs[0] if langs else None, langs[1] if len(langs) > 1 else None)
