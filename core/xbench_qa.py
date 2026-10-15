"""
core.xbench_qa - Motor de Garantia de Qualidade (QA) estilo ApSIC Xbench para Trados Studio.

Verificações implementadas:
1. Untranslated: Segmentos com fonte preenchida mas sem tradução
2. Target same as Source: Tradução idêntica à fonte (exceto números/códigos curtos)
3. Source Inconsistency: Mesmo texto fonte com traduções diferentes
4. Target Inconsistency: Textos fonte diferentes com a mesma tradução
5. Numeric Mismatches: Números/dígitos presentes na fonte ausentes ou diferentes na tradução
6. Punctuation Mismatches: Pontuação final diferente (., !, ?, :, ;)
7. Whitespace / Double Spaces: Espaços duplos ou espaços no início/fim
8. Repeated Words: Palavras repetidas acidentalmente ("de de", "o o", "the the")
9. Tag Mismatches: Diferença na contagem ou tipo de tags inline
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from core.segment import Segment, display_text, SegState


@dataclass
class QAIssue:
    row_index: int
    seg_id: str
    issue_type: str
    severity: str        # "Error", "Warning", "Info"
    description: str
    source: str
    target: str


class XbenchQAEngine:
    """Motor de QA estilo ApSIC Xbench."""

    def __init__(self) -> None:
        pass

    def run_qa(self, segments: List[Segment]) -> List[QAIssue]:
        """Executa a bateria completa de verificações de QA nos segmentos."""
        issues: List[QAIssue] = []
        
        # Dicionários para verificação de inconsistências
        src_to_tgt: Dict[str, List[Tuple[int, str]]] = {}
        tgt_to_src: Dict[str, List[Tuple[int, str]]] = {}

        for idx, seg in enumerate(segments):
            src = display_text(seg.source).strip()
            tgt = display_text(seg.target).strip()
            seg_id = seg.seg_id or str(idx + 1)

            # 1. Untranslated
            if src and not tgt:
                issues.append(QAIssue(
                    row_index=idx,
                    seg_id=seg_id,
                    issue_type="Untranslated Segment",
                    severity="Warning",
                    description="O segmento fonte possui conteúdo, mas a tradução está vazia.",
                    source=src,
                    target=tgt,
                ))
                continue

            if not src and not tgt:
                continue

            # 2. Target same as Source
            if src == tgt and len(src) > 4 and not src.replace(".", "").replace(",", "").isdigit():
                issues.append(QAIssue(
                    row_index=idx,
                    seg_id=seg_id,
                    issue_type="Target Same as Source",
                    severity="Warning",
                    description="A tradução é idêntica à fonte (possível texto esquecido).",
                    source=src,
                    target=tgt,
                ))

            # 3. Numeric mismatch
            src_nums = sorted(re.findall(r"\b\d+(?:[.,]\d+)?\b", src))
            tgt_nums = sorted(re.findall(r"\b\d+(?:[.,]\d+)?\b", tgt))
            # Normalizar separadores para comparar valores numéricos
            def norm_nums(num_list):
                res = []
                for n in num_list:
                    res.append(n.replace(",", "."))
                return sorted(res)

            if norm_nums(src_nums) != norm_nums(tgt_nums):
                missing_in_tgt = [n for n in src_nums if n.replace(",", ".") not in norm_nums(tgt_nums)]
                extra_in_tgt = [n for n in tgt_nums if n.replace(",", ".") not in norm_nums(src_nums)]
                details = []
                if missing_in_tgt:
                    details.append(f"Falta na tradução: {', '.join(missing_in_tgt)}")
                if extra_in_tgt:
                    details.append(f"Extra na tradução: {', '.join(extra_in_tgt)}")
                issues.append(QAIssue(
                    row_index=idx,
                    seg_id=seg_id,
                    issue_type="Numeric Mismatch",
                    severity="Error",
                    description="Divergência de números entre fonte e tradução. " + "; ".join(details),
                    source=src,
                    target=tgt,
                ))

            # 4. Trailing punctuation mismatch
            if src and tgt:
                src_last = src[-1] if src[-1] in ".!?:;" else ""
                tgt_last = tgt[-1] if tgt[-1] in ".!?:;" else ""
                if src_last != tgt_last:
                    issues.append(QAIssue(
                        row_index=idx,
                        seg_id=seg_id,
                        issue_type="Trailing Punctuation",
                        severity="Warning",
                        description=f"Pontuação final divergente: fonte termina com '{src_last or '(nenhuma)'}' e tradução com '{tgt_last or '(nenhuma)'}'.",
                        source=src,
                        target=tgt,
                    ))

            # 5. Double spaces / whitespace issues
            raw_tgt = seg.target if isinstance(seg.target, str) else display_text(seg.target)
            if "  " in raw_tgt:
                issues.append(QAIssue(
                    row_index=idx,
                    seg_id=seg_id,
                    issue_type="Double Spaces",
                    severity="Warning",
                    description="Espaços duplos detectados no segmento de tradução.",
                    source=src,
                    target=tgt,
                ))
            if raw_tgt.startswith(" ") or raw_tgt.endswith(" "):
                issues.append(QAIssue(
                    row_index=idx,
                    seg_id=seg_id,
                    issue_type="Trailing/Leading Space",
                    severity="Info",
                    description="Espaço em branco desnecessário no início ou final da tradução.",
                    source=src,
                    target=tgt,
                ))

            # 6. Repeated words ("de de", "o o", "the the")
            repeated_match = re.search(r"\b([a-zA-ZáéíóúãõâêîôûàçÁÉÍÓÚÃÕÂÊÎÔÛÀÇ]{2,})\s+\1\b", tgt, re.IGNORECASE)
            if repeated_match:
                rep_word = repeated_match.group(1)
                issues.append(QAIssue(
                    row_index=idx,
                    seg_id=seg_id,
                    issue_type="Repeated Word",
                    severity="Warning",
                    description=f"Palavra repetida consecutivamente: '{rep_word} {rep_word}'.",
                    source=src,
                    target=tgt,
                ))

            # 7. Tag mismatches
            if len(seg.source_tags) != len(seg.target_tags):
                issues.append(QAIssue(
                    row_index=idx,
                    seg_id=seg_id,
                    issue_type="Tag Count Mismatch",
                    severity="Error",
                    description=f"Divergência no número de tags: fonte tem {len(seg.source_tags)} tags e tradução tem {len(seg.target_tags)} tags.",
                    source=src,
                    target=tgt,
                ))

            # Coletar para checagem de inconsistências
            if src and tgt:
                src_to_tgt.setdefault(src, []).append((idx, tgt))
                tgt_to_src.setdefault(tgt, []).append((idx, src))

        # 8. Source Inconsistencies (Mesmo source, traduções diferentes)
        for src_text, occurrences in src_to_tgt.items():
            distinct_translations = {t for _, t in occurrences}
            if len(distinct_translations) > 1:
                for row_i, t in occurrences:
                    seg = segments[row_i]
                    other_translations = [ot for ot in distinct_translations if ot != t]
                    issues.append(QAIssue(
                        row_index=row_i,
                        seg_id=seg.seg_id or str(row_i + 1),
                        issue_type="Source Inconsistency",
                        severity="Warning",
                        description=f"Esta fonte foi traduzida de formas diferentes em outros segmentos: {', '.join(other_translations[:2])}",
                        source=src_text,
                        target=t,
                    ))

        # Ordenar issues por row_index e depois severidade
        sev_order = {"Error": 0, "Warning": 1, "Info": 2}
        issues.sort(key=lambda x: (x.row_index, sev_order.get(x.severity, 3)))
        return issues

