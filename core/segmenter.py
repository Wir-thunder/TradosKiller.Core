"""
core.segmenter - Motor inteligente de segmentação de unidades de tradução (Smart Sentence Segmenter).

Resolve definitivamente o problema das regras de segmentação legadas do Trados Studio (Language Resources / SRX)
que quebravam sentenças em locais indevidos:
1. Abreviações protegidas (títulos, empresas, meses, abreviações latinas, técnicas em PT/EN/ES/FR/DE).
2. Números decimais, moedas, preços, versões (ex: 3.14, $1,500.00, R$ 250,50, v2.1.0).
3. URLs, domínios, e-mails e nomes de ficheiros protegidos.
4. Reticências (... e …) e pontuações compostas (?!, !?, etc.).
5. Aspas e parênteses equilibrados (sem deixar aspas órfãs no segmento seguinte).
6. Preservação de tags inline (\ue000N\ue001) e tags XML.
7. Auto-heal: capacidade de detectar e reunificar segmentos quebrados indevidamente por regras antigas.
"""
from __future__ import annotations

import re
from typing import List, Tuple, Set, Optional
from core.segment import Segment, SegState, SegOrigin, display_text, TOKEN_PREFIX, TOKEN_SUFFIX


# Lista exaustiva de abreviações protegidas multilíngues (PT, EN, ES, FR, DE, IT)
COMMON_ABBREVIATIONS: Set[str] = {
    # Títulos e honoríficos
    "mr", "mrs", "ms", "dr", "dra", "prof", "profa", "sr", "sra", "srta", "rev",
    "gen", "col", "sgt", "cpt", "ten", "maj", "eng", "enga", "adv", "exmo", "exma",
    "d", "dom", "dona", "pe", "fr", "mons", "vme", "vcia", "vsa",
    
    # Corporativo / Comercial / Jurídico
    "inc", "ltd", "corp", "co", "llc", "ltda", "sa", "s.a", "s/a", "eireli", "me",
    "epp", "cia", "gmbh", "ag", "sarl", "bv", "pvt", "assoc", "dept", "div",
    
    # Técnicas, acadêmicas e latinas
    "eg", "e.g", "ie", "i.e", "etc", "vs", "v", "al", "et al", "ibid", "op. cit",
    "cf", "ca", "approx", "fig", "figs", "no", "nos", "vol", "vols", "p", "pp",
    "pg", "pag", "pags", "ch", "sec", "min", "hr", "hrs", "art", "arts", "ref",
    "ed", "eds", "trans", "trad", "univ", "inst", "conf", "proc",
    
    # Localização e endereços
    "st", "ave", "av", "rd", "blvd", "dr", "ln", "ct", "pl", "rod", "trav", "al",
    "r", "apt", "apto", "bl", "cj", "sala", "cx",
    
    # Meses
    "jan", "feb", "fev", "mar", "apr", "abr", "may", "mai", "jun", "jul", "aug",
    "ago", "sep", "sept", "set", "oct", "out", "nov", "dec", "dez",
    
    # Unidades e medidas
    "kg", "km", "cm", "mm", "lb", "oz", "ft", "in", "yd", "mph", "km/h",
}

# Regex para proteger sequências que não devem ser quebradas
RE_URL_EMAIL = re.compile(r'(?:https?://|www\.)[^\s<>"]+|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}')
RE_VERSION_NUM = re.compile(r'\bv?\d+(?:\.\d+)+(?:-[a-zA-Z0-9]+)?\b')
RE_CURRENCY_DECIMAL = re.compile(r'\b(?:R\$|\$|€|£|¥)\s*\d+(?:[.,]\d+)+\b|\b\d+[.,]\d+\b')
RE_INITIALS = re.compile(r'\b(?:[A-Z]\.){1,3}\b')
RE_ELLIPSIS = re.compile(r'\.{3,}|…')
RE_INLINE_TAG = re.compile(rf'{TOKEN_PREFIX}\d+{TOKEN_SUFFIX}')


class SmartSentenceSegmenter:
    """Segmentador inteligente de orações para unidades de tradução."""

    def __init__(self, extra_abbreviations: Optional[Set[str]] = None) -> None:
        self.abbreviations = set(COMMON_ABBREVIATIONS)
        if extra_abbreviations:
            self.abbreviations.update(a.lower().rstrip('.') for a in extra_abbreviations)

    def split_into_sentences(self, text: str) -> List[str]:
        """
        Divide um texto em sentenças completas sem quebrar em abreviações,
        decimais, URLs ou tags inline.
        """
        if not text or not text.strip():
            return [text] if text else []

        # Preserva quebras de linha duras como fronteiras naturais de parágrafo
        paragraphs = text.splitlines(keepends=True)
        all_sentences: List[str] = []

        for para in paragraphs:
            para_sentences = self._split_paragraph(para)
            all_sentences.extend(para_sentences)

        return [s for s in all_sentences if s]

    def _split_paragraph(self, para: str) -> List[str]:
        """Processa um parágrafo contínuo com proteção por máscaras."""
        if not para.strip():
            return [para]

        masks: List[Tuple[str, str]] = []
        masked_text = para

        def _make_mask(match: re.Match) -> str:
            val = match.group(0)
            token = f"\ue002M{len(masks)}\ue003"
            masks.append((token, val))
            return token

        # 1. Proteger tags inline
        masked_text = RE_INLINE_TAG.sub(_make_mask, masked_text)

        # 2. Proteger URLs e e-mails
        masked_text = RE_URL_EMAIL.sub(_make_mask, masked_text)

        # 3. Proteger versões e decimais (ex: 3.14, v1.0.4)
        masked_text = RE_VERSION_NUM.sub(_make_mask, masked_text)
        masked_text = RE_CURRENCY_DECIMAL.sub(_make_mask, masked_text)

        # 4. Proteger reticências
        masked_text = RE_ELLIPSIS.sub(_make_mask, masked_text)

        # 5. Proteger iniciais de nomes (ex: J. K. Rowling, F. Kennedy)
        masked_text = RE_INITIALS.sub(_make_mask, masked_text)

        # 6. Proteger abreviações conhecidas
        words = re.split(r'(\s+)', masked_text)
        for idx in range(len(words)):
            w = words[idx]
            if w.endswith('.') and len(w) > 1:
                clean_w = w.rstrip('.').lower().strip()
                if clean_w in self.abbreviations:
                    token = f"\ue002M{len(masks)}\ue003"
                    masks.append((token, w))
                    words[idx] = token
        masked_text = "".join(words)

        # 7. Divisão em sentenças genuínas
        # Critério: [.!?] seguido de espaço e maiúscula (ou aspa/parêntese + maiúscula)
        split_pattern = re.compile(
            r'([.!?]+["\'”’\)\]]*)\s+(?=[A-ZÀ-ÖØ-ß"\'“‘\(\[])'
        )

        parts = split_pattern.split(masked_text)
        raw_sentences: List[str] = []

        if len(parts) == 1:
            raw_sentences = [parts[0]]
        else:
            i = 0
            while i < len(parts):
                if i + 1 < len(parts):
                    # parts[i] é o corpo da sentença, parts[i+1] é a pontuação final
                    raw_sentences.append(parts[i] + parts[i + 1])
                    i += 2
                else:
                    if parts[i]:
                        raw_sentences.append(parts[i])
                    i += 1

        # 8. Desmascarar todas as sentenças
        final_sentences: List[str] = []
        for s in raw_sentences:
            unmasked = s
            for token, orig in reversed(masks):
                unmasked = unmasked.replace(token, orig)
            if unmasked.strip():
                final_sentences.append(unmasked.strip())

        return final_sentences if final_sentences else [para]

    @classmethod
    def is_likely_broken_fragment(cls, seg1: Segment, seg2: Segment) -> bool:
        """
        Determina se seg1 e seg2 formam na verdade uma única sentença que foi
        quebrada indevidamente por regras antigas da TM (ex: após abreviação ou vírgula).
        """
        src1 = display_text(seg1.source).strip()
        src2 = display_text(seg2.source).strip()
        if not src1 or not src2:
            return False

        # Caso A: seg1 termina com uma abreviação protegida (ex: 'Please see Dr.')
        last_word = src1.split()[-1].rstrip('.').lower() if src1.split() else ""
        if last_word in COMMON_ABBREVIATIONS:
            return True

        # Caso B: seg1 termina sem pontuação terminal e seg2 começa com minúscula
        ends_terminal = bool(re.search(r'[.!?]["\'”’\)\]]*$', src1))
        starts_lower = bool(re.match(r'^[a-zà-öø-ÿ]', src2))
        if not ends_terminal and starts_lower:
            return True

        # Caso C: seg1 termina com vírgula, dois-pontos ou hífen
        if re.search(r'[,;:\-–—]$', src1):
            return True

        # Caso D: seg2 começa com fechamento órfão de aspas ou parênteses
        if re.match(r'^["\'”’\)\]]', src2) and not re.search(r'["\'”’\)\]]$', src1):
            return True

        return False

    @classmethod
    def heal_broken_segments(cls, segments: List[Segment]) -> Tuple[List[Segment], int]:
        """
        Reunifica e cura segmentos quebrados indevidamente por regras legadas do Trados.
        Retorna (lista_curada, total_de_unificacoes_feitas).
        """
        if len(segments) <= 1:
            return list(segments), 0

        healed: List[Segment] = []
        healed_count = 0
        i = 0

        while i < len(segments):
            current = segments[i]

            # Tenta combinar sequencialmente enquanto o próximo for um fragmento
            while (i + 1 < len(segments)) and cls.is_likely_broken_fragment(current, segments[i + 1]):
                next_seg = segments[i + 1]

                # Combina fontes com espaço apropriado
                sep_src = "" if current.source.endswith(("-", "—", "/")) else " "
                merged_source = f"{current.source}{sep_src}{next_seg.source}".strip()

                # Combina traduções se ambas existirem
                if current.target and next_seg.target:
                    sep_tgt = "" if current.target.endswith(("-", "—", "/")) else " "
                    merged_target = f"{current.target}{sep_tgt}{next_seg.target}".strip()
                elif current.target:
                    merged_target = current.target
                else:
                    merged_target = next_seg.target

                # Combina tags inline
                merged_src_tags = list(current.source_tags) + list(next_seg.source_tags)
                merged_tgt_tags = list(current.target_tags) + list(next_seg.target_tags)

                # Estado unificado
                st = SegState.TRANSLATED if merged_target else SegState.UNTRANSLATED
                if current.state == SegState.APPROVED and next_seg.state == SegState.APPROVED:
                    st = SegState.APPROVED

                current = Segment(
                    source=merged_source,
                    target=merged_target,
                    tu_id=current.tu_id,
                    seg_id=current.seg_id,
                    row_id=current.row_id,
                    state=st,
                    origin=current.origin,
                    percent=min(current.percent, next_seg.percent) if (current.percent and next_seg.percent) else max(current.percent, next_seg.percent),
                    source_tags=merged_src_tags,
                    target_tags=merged_tgt_tags,
                    order=current.order
                )
                healed_count += 1
                i += 1

            healed.append(current)
            i += 1

        # Reordena a numeração sequencial
        for idx, s in enumerate(healed):
            s.order = idx

        return healed, healed_count

