from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List
from xml.sax.saxutils import escape


class SegState(Enum):
    UNTRANSLATED = "untranslated"
    TRANSLATED = "translated"
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class SegOrigin(Enum):
    NONE = "none"
    INTERACTIVE = "interactive"
    TM = "tm"
    MT = "mt"
    MANUAL = "manual"
    AUTO = "auto"


@dataclass
class InlineTag:
    code: str
    placeholder: str = ""


@dataclass
class Segment:
    source: str
    target: str = ""
    tu_id: str = ""
    seg_id: str = ""
    row_id: int = 0
    state: SegState = SegState.UNTRANSLATED
    origin: SegOrigin = SegOrigin.NONE
    percent: int = 0
    source_tags: List[InlineTag] = field(default_factory=list)
    target_tags: List[InlineTag] = field(default_factory=list)
    order: int = 0


TOKEN_PREFIX = "\ue000"
TOKEN_SUFFIX = "\ue001"
TOKEN_REGEX = re.compile(rf"{TOKEN_PREFIX}(\d+){TOKEN_SUFFIX}")


def inline_token(index: int) -> str:
    """Retorna um marcador de tag inline que não colide com texto nem com '{N}'."""
    return f"{TOKEN_PREFIX}{index}{TOKEN_SUFFIX}"


def display_text(text: str) -> str:
    """Remove os marcadores internos de tags inline para exibição limpa na interface."""
    if not text:
        return ""
    return TOKEN_REGEX.sub("", text)


def merge_inline_tokens(new_text: str, old_text: str, tags: List[InlineTag]) -> str:
    """
    Preserva/re-injeta os marcadores de tags inline ao atualizar texto editado pelo usuário.
    Se o novo texto já contiver marcadores, preserva-os. Caso contrário, re-anexa as tags
    de abertura e fecho (ou todas as tags não presentes).
    """
    if not tags:
        return new_text

    present = {tag.placeholder for tag in tags if tag.placeholder in new_text}
    missing = [tag for tag in tags if tag.placeholder not in present]
    if not missing:
        return new_text

    prefix_tokens: list[str] = []
    suffix_tokens: list[str] = []

    # Determina se a tag estava no início ou no fim do texto antigo
    for tag in missing:
        tok = tag.placeholder
        pos = old_text.find(tok)
        code = tag.code.strip()
        # Se for tag de fecho ou se estava depois da primeira ocorrência de texto visível
        if code.startswith("</") or code.startswith("<ept") or (pos != -1 and pos > len(old_text) // 2):
            suffix_tokens.append(tok)
        else:
            prefix_tokens.append(tok)

    return "".join(prefix_tokens) + new_text + "".join(suffix_tokens)


def inline_xml_content(text: str, tags: List[InlineTag]) -> str:
    """
    Substitui os placeholders pelas tags XML reais (sem re-escapar as tags),
    garantindo que o texto circundante esteja devidamente protegido com escape XML.
    """
    if not text:
        return ""

    if not tags:
        return escape(text)

    tag_map = {tag.placeholder: tag.code for tag in tags}

    parts = []
    last_end = 0
    for match in TOKEN_REGEX.finditer(text):
        token_str = match.group(0)
        parts.append(escape(text[last_end:match.start()]))
        if token_str in tag_map:
            parts.append(tag_map[token_str])
        last_end = match.end()

    parts.append(escape(text[last_end:]))
    return "".join(parts)