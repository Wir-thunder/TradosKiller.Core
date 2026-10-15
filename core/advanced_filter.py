"""
core.advanced_filter - Motor do Advanced Display Filter 2.0 estilo SDL Trados Studio.

Permite filtrar segmentos por múltiplos critérios combinados:
- Conteúdo de texto (Fonte e Tradução com regex, case-sensitive, exato, contém, não contém)
- Estado de confirmação (Untranslated, Draft, Translated, Approved, Rejected)
- Origem da tradução (TM, MT, Manual, None)
- Faixa de % de correspondência (ex: 75% a 99%, exatamente 100%)
- Presença de tags inline
- Tradução vazia ou tradução idêntica à fonte
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Set, List, Optional
from core.segment import display_text


@dataclass
class AdvancedFilterCriteria:
    # 1. Filtro de Texto Fonte
    source_text: str = ""
    source_mode: str = "contains"      # "contains", "exact", "not_contains", "starts_with", "ends_with", "regex"
    source_case: bool = False

    # 2. Filtro de Texto Tradução
    target_text: str = ""
    target_mode: str = "contains"      # "contains", "exact", "not_contains", "starts_with", "ends_with", "regex"
    target_case: bool = False

    # 3. Status de Confirmação (vazio = todos os estados)
    statuses: Set[str] = field(default_factory=set)

    # 4. Origem da Tradução (vazio = todas as origens)
    origins: Set[str] = field(default_factory=set)

    # 5. Faixa de Correspondência %
    filter_by_percent: bool = False
    min_percent: int = 0
    max_percent: int = 100

    # 6. Atributos Especiais
    only_with_tags: bool = False
    only_without_tags: bool = False
    only_target_empty: bool = False
    only_target_equals_source: bool = False

    # 7. Operador lógico e Inversão (Trados ADF 2.0)
    operator: str = "AND"              # "AND" ou "OR"
    reverse: bool = False              # Inverte o resultado do filtro (Reverse)

    def is_empty(self) -> bool:
        """Verifica se nenhum critério de filtro foi configurado."""
        return (
            not self.source_text.strip()
            and not self.target_text.strip()
            and not self.statuses
            and not self.origins
            and not self.filter_by_percent
            and not self.only_with_tags
            and not self.only_without_tags
            and not self.only_target_empty
            and not self.only_target_equals_source
        )


def apply_advanced_filter(conn, criteria: AdvancedFilterCriteria, reverse: Optional[bool] = None) -> List[int]:
    """
    Executa a filtragem combinada e retorna a lista de IDs dos segmentos correspondentes.
    Suporta operadores 'AND' e 'OR', além do modo 'Reverse' (inversão) padrão Trados ADF 2.0.
    """
    rows = conn.execute(
        "SELECT id, state, origin, percent, source, target, source_tags, target_tags "
        "FROM segments ORDER BY segment_order, id"
    ).fetchall()

    all_ids = [r["id"] for r in rows]
    do_reverse = criteria.reverse if reverse is None else reverse

    if criteria.is_empty():
        return [] if do_reverse else all_ids

    # Compiladores e checagem de texto
    def check_text(text: str, query_text: str, mode: str, case: bool) -> bool:
        if not query_text:
            return True
        clean = display_text(text or "")
        q = query_text if case else query_text.lower()
        target = clean if case else clean.lower()

        if mode == "contains":
            return q in target
        elif mode == "not_contains":
            return q not in target
        elif mode == "exact":
            return target.strip() == q.strip()
        elif mode == "starts_with":
            return target.strip().startswith(q.strip())
        elif mode == "ends_with":
            return target.strip().endswith(q.strip())
        elif mode == "regex":
            flags = 0 if case else re.IGNORECASE
            try:
                return bool(re.search(query_text, clean, flags=flags))
            except Exception:
                return False
        return True

    matched_ids: List[int] = []
    is_or = criteria.operator.upper() == "OR"

    for r in rows:
        seg_id = r["id"]
        src = r["source"] or ""
        tgt = r["target"] or ""
        st = r["state"] or ""
        orig = r["origin"] or ""
        pct = r["percent"] or 0
        src_tags = r["source_tags"] or "[]"
        has_tags = src_tags != "[]" and len(src_tags) > 4

        evaluations: List[bool] = []

        # 1. Statuses
        if criteria.statuses:
            evaluations.append(st.lower() in {s.lower() for s in criteria.statuses})

        # 2. Origins
        if criteria.origins:
            evaluations.append(orig.lower() in {o.lower() for o in criteria.origins})

        # 3. Match %
        if criteria.filter_by_percent:
            evaluations.append(criteria.min_percent <= pct <= criteria.max_percent)

        # 4. Target vazio
        if criteria.only_target_empty:
            evaluations.append(not tgt.strip())

        # 5. Target idêntico à fonte
        if criteria.only_target_equals_source:
            evaluations.append(display_text(src).strip() == display_text(tgt).strip())

        # 6. Tags inline
        if criteria.only_with_tags:
            evaluations.append(has_tags)
        if criteria.only_without_tags:
            evaluations.append(not has_tags)

        # 7. Texto Fonte
        if criteria.source_text.strip():
            evaluations.append(check_text(src, criteria.source_text, criteria.source_mode, criteria.source_case))

        # 8. Texto Alvo
        if criteria.target_text.strip():
            evaluations.append(check_text(tgt, criteria.target_text, criteria.target_mode, criteria.target_case))

        if not evaluations:
            is_match = True
        elif is_or:
            is_match = any(evaluations)
        else:
            is_match = all(evaluations)

        if is_match:
            matched_ids.append(seg_id)

    if do_reverse:
        matched_set = set(matched_ids)
        return [i for i in all_ids if i not in matched_set]

    return matched_ids

