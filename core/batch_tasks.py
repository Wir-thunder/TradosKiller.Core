"""
core.batch_tasks - Motor de Tarefas em Lote (Batch Tasks) estilo SDL Trados Studio.

Tarefas disponíveis:
1. Analyze Files: Contagem de palavras, repetições e correspondências de TM (100%, Fuzzy, Novo).
2. Pre-translate Files: Aplicação automática de correspondências da TM e TMs de referência.
3. Verify Files: Verificação de qualidade (QA) estilo ApSIC Xbench em todos os ficheiros.
4. Update Main Translation Memories: Consolidação de traduções confirmadas na base .sdltm.
5. Generate Target Translations: Exportação de ficheiros finais traduzidos.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any

from core.segment import Segment, SegState, SegOrigin, display_text
from core.xbench_qa import XbenchQAEngine, QAIssue
from io_layer.sdlxliff import iter_sdlxliff
from io_layer.tmx import iter_tmx
from io_layer.sdltm import write_sdltm
from core.slm import OllamaClient


def count_words(text: str) -> int:
    """Conta palavras de forma consistente com CAT tools."""
    if not text:
        return 0
    clean = display_text(text)
    return len(re.findall(r'\b[\w\'-]+\b', clean))


def count_chars(text: str) -> int:
    """Conta caracteres (sem tags inline)."""
    if not text:
        return 0
    return len(display_text(text))


@dataclass
class FileAnalysisResult:
    """Resultado da análise de um ficheiro individual."""
    file_path: str
    file_name: str
    total_segments: int = 0
    total_words: int = 0
    total_chars: int = 0
    repetitions_segments: int = 0
    repetitions_words: int = 0
    match_100_segments: int = 0
    match_100_words: int = 0
    fuzzy_95_99_segments: int = 0
    fuzzy_95_99_words: int = 0
    fuzzy_85_94_segments: int = 0
    fuzzy_85_94_words: int = 0
    fuzzy_75_84_segments: int = 0
    fuzzy_75_84_words: int = 0
    fuzzy_50_74_segments: int = 0
    fuzzy_50_74_words: int = 0
    new_segments: int = 0
    new_words: int = 0

    @property
    def total_match_words(self) -> int:
        return (self.repetitions_words + self.match_100_words +
                self.fuzzy_95_99_words + self.fuzzy_85_94_words +
                self.fuzzy_75_84_words + self.fuzzy_50_74_words)

    @property
    def leverage_percent(self) -> float:
        if self.total_words == 0:
            return 0.0
        return (self.total_match_words / self.total_words) * 100.0


@dataclass
class BatchAnalysisReport:
    """Relatório consolidado de análise de ficheiros (Trados Analysis Report)."""
    project_name: str
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    source_lang: str = "en-US"
    target_lang: str = "pt-PT"
    files: List[FileAnalysisResult] = field(default_factory=list)

    @property
    def totals(self) -> FileAnalysisResult:
        t = FileAnalysisResult(file_path="", file_name="Total do Projeto")
        for f in self.files:
            t.total_segments += f.total_segments
            t.total_words += f.total_words
            t.total_chars += f.total_chars
            t.repetitions_segments += f.repetitions_segments
            t.repetitions_words += f.repetitions_words
            t.match_100_segments += f.match_100_segments
            t.match_100_words += f.match_100_words
            t.fuzzy_95_99_segments += f.fuzzy_95_99_segments
            t.fuzzy_95_99_words += f.fuzzy_95_99_words
            t.fuzzy_85_94_segments += f.fuzzy_85_94_segments
            t.fuzzy_85_94_words += f.fuzzy_85_94_words
            t.fuzzy_75_84_segments += f.fuzzy_75_84_segments
            t.fuzzy_75_84_words += f.fuzzy_75_84_words
            t.fuzzy_50_74_segments += f.fuzzy_50_74_segments
            t.fuzzy_50_74_words += f.fuzzy_50_74_words
            t.new_segments += f.new_segments
            t.new_words += f.new_words
        return t

    def to_html(self) -> str:
        """Gera relatório HTML estilo SDL Trados Studio."""
        t = self.totals
        rows_html = ""
        for f in self.files:
            rows_html += f"""
            <tr>
                <td style="font-weight:bold; color:#8eb4f3;">{f.file_name}</td>
                <td align="right">{f.total_segments:,}</td>
                <td align="right">{f.total_words:,}</td>
                <td align="right">{f.repetitions_words:,}</td>
                <td align="right">{f.match_100_words:,}</td>
                <td align="right">{f.fuzzy_95_99_words + f.fuzzy_85_94_words + f.fuzzy_75_84_words:,}</td>
                <td align="right" style="color:#e67e22; font-weight:bold;">{f.new_words:,}</td>
                <td align="right" style="color:#2ecc71;">{f.leverage_percent:.1f}%</td>
            </tr>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Relatório de Análise — {self.project_name}</title>
<style>
    body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background: #1e1e1e; color: #ddd; padding: 20px; }}
    h1 {{ color: #007acc; font-size: 20px; border-bottom: 2px solid #007acc; padding-bottom: 8px; }}
    .meta {{ font-size: 12px; color: #aaa; margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }}
    th {{ background: #2d2d30; color: #8eb4f3; padding: 8px; border: 1px solid #3e3e42; text-align: left; }}
    td {{ padding: 6px 8px; border: 1px solid #333333; }}
    tr:nth-child(even) {{ background: #252526; }}
    tr.total {{ background: #007acc; color: white; font-weight: bold; }}
    tr.total td {{ border-color: #005999; }}
</style>
</head>
<body>
<h1>Relatório de Análise de Ficheiros (Trados Studio Analysis)</h1>
<div class="meta">
    <strong>Projeto:</strong> {self.project_name} | 
    <strong>Data:</strong> {self.created_at} | 
    <strong>Idiomas:</strong> {self.source_lang} ➔ {self.target_lang}
</div>

<table>
    <thead>
        <tr>
            <th>Ficheiro</th>
            <th align="right">Segmentos</th>
            <th align="right">Total Palavras</th>
            <th align="right">Repetições</th>
            <th align="right">100% Matches</th>
            <th align="right">Fuzzy (75-99%)</th>
            <th align="right">Novo / Pendente</th>
            <th align="right">Aproveitamento</th>
        </tr>
    </thead>
    <tbody>
        {rows_html}
        <tr class="total">
            <td>TOTAL GERAL</td>
            <td align="right">{t.total_segments:,}</td>
            <td align="right">{t.total_words:,}</td>
            <td align="right">{t.repetitions_words:,}</td>
            <td align="right">{t.match_100_words:,}</td>
            <td align="right">{t.fuzzy_95_99_words + t.fuzzy_85_94_words + t.fuzzy_75_84_words:,}</td>
            <td align="right">{t.new_words:,}</td>
            <td align="right">{t.leverage_percent:.1f}%</td>
        </tr>
    </tbody>
</table>
</body>
</html>"""


class BatchTaskEngine:
    """Motor de execução das tarefas em lote do SDL Trados Studio."""

    @staticmethod
    def extract_segments_from_file(file_path: str) -> List[Segment]:
        """Extrai todos os segmentos de um ficheiro bilingue (.sdlxliff, .tmx, .sdltm)."""
        if not os.path.exists(file_path):
            return []
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".sdlxliff", ".xlf", ".xliff"):
            return list(iter_sdlxliff(file_path))
        elif ext == ".tmx":
            return list(iter_tmx(file_path))
        return []

    @classmethod
    def analyze_project(cls, project_name: str, file_paths: List[str],
                        src_lang: str = "en-US", tgt_lang: str = "pt-PT",
                        reference_tm=None) -> BatchAnalysisReport:
        """Executa a análise completa de palavras e aproveitamento de TM (Analyze Files)."""
        report = BatchAnalysisReport(
            project_name=project_name,
            source_lang=src_lang,
            target_lang=tgt_lang
        )

        seen_sources: set[str] = set()

        for path in file_paths:
            f_res = FileAnalysisResult(file_path=path, file_name=os.path.basename(path))
            segs = cls.extract_segments_from_file(path)
            f_res.total_segments = len(segs)

            for s in segs:
                clean_src = display_text(s.source).strip()
                w_count = count_words(clean_src)
                c_count = count_chars(clean_src)

                f_res.total_words += w_count
                f_res.total_chars += c_count

                if not clean_src:
                    continue

                # 1. Repetição dentro do projeto
                if clean_src in seen_sources:
                    f_res.repetitions_segments += 1
                    f_res.repetitions_words += w_count
                    continue

                seen_sources.add(clean_src)

                # 2. Match contra TM se disponível
                if reference_tm is not None:
                    exact = reference_tm.exact_match(clean_src)
                    if exact:
                        f_res.match_100_segments += 1
                        f_res.match_100_words += w_count
                        continue

                    # Concordance / fuzzy check
                    fuzzy = reference_tm.concordance(clean_src[:25], limit=1)
                    if fuzzy:
                        f_res.fuzzy_75_84_segments += 1
                        f_res.fuzzy_75_84_words += w_count
                        continue

                # Se já tiver percent no ficheiro (ex: sdlxliff pré-analisado)
                if s.percent >= 100:
                    f_res.match_100_segments += 1
                    f_res.match_100_words += w_count
                elif s.percent >= 95:
                    f_res.fuzzy_95_99_segments += 1
                    f_res.fuzzy_95_99_words += w_count
                elif s.percent >= 85:
                    f_res.fuzzy_85_94_segments += 1
                    f_res.fuzzy_85_94_words += w_count
                elif s.percent >= 75:
                    f_res.fuzzy_75_84_segments += 1
                    f_res.fuzzy_75_84_words += w_count
                elif s.percent > 0:
                    f_res.fuzzy_50_74_segments += 1
                    f_res.fuzzy_50_74_words += w_count
                else:
                    f_res.new_segments += 1
                    f_res.new_words += w_count

            report.files.append(f_res)

        return report

    @classmethod
    def pretranslate_segments(cls, segments: List[Segment], reference_tm,
                              min_match_percent: int = 100,
                              confirm: bool = True,
                              use_slm: bool = False,
                              slm_model: Optional[str] = None,
                              progress_callback=None) -> int:
        """Aplica traduções da TM e opcionalmente SLM Neural aos segmentos não traduzidos (Pre-translate Files)."""
        slm_client = OllamaClient() if use_slm else None
        pretranslated_count = 0
        total_segs = len(segments)

        for idx, seg in enumerate(segments):
            if progress_callback and idx % 20 == 0:
                progress_callback(idx, total_segs)

            # Apenas pré-traduz segmentos pendentes ou vazios
            if seg.state != SegState.UNTRANSLATED and seg.target.strip():
                continue

            clean_src = display_text(seg.source).strip()
            if not clean_src:
                continue

            # 1. Busca exata 100% na TM de referência
            tgt = ""
            if reference_tm is not None:
                match = reference_tm.exact_match(clean_src)
                tgt = match.target if match else ""
                if not tgt:
                    tgt = reference_tm.get_reference_match(clean_src)

            if tgt:
                seg.target = tgt
                seg.state = SegState.TRANSLATED if confirm else SegState.DRAFT
                seg.origin = SegOrigin.TM
                seg.percent = 100
                pretranslated_count += 1
            elif use_slm and slm_client is not None:
                try:
                    slm_tgt = slm_client.translate(
                        clean_src,
                        model=slm_model or "toyotao:latest",
                        temperature=0.1
                    )
                    if slm_tgt and not slm_tgt.startswith("[Erro"):
                        seg.target = slm_tgt
                        seg.state = SegState.TRANSLATED if confirm else SegState.DRAFT
                        seg.origin = SegOrigin.MT
                        seg.percent = 85
                        pretranslated_count += 1
                except Exception:
                    pass

        return pretranslated_count

    @classmethod
    def verify_project_files(cls, file_paths: List[str]) -> List[QAIssue]:
        """Executa a auditoria completa de QA em todos os ficheiros (Verify Files F8)."""
        engine = XbenchQAEngine()
        all_issues: List[QAIssue] = []

        for path in file_paths:
            segs = cls.extract_segments_from_file(path)
            file_name = os.path.basename(path)
            issues = engine.run_qa(segs)
            for iss in issues:
                iss.file_name = file_name
                all_issues.append(iss)

        return all_issues

    @classmethod
    def update_main_tm(cls, segments: List[Segment], target_sdltm_path: str,
                       src_lang: str = "en-US", tgt_lang: str = "pt-PT") -> int:
        """Grava e consolida traduções confirmadas na base de memória .sdltm (Update Main TMs)."""
        valid_segs = [
            s for s in segments
            if s.target.strip() and s.state in (SegState.TRANSLATED, SegState.APPROVED)
        ]
        if not valid_segs:
            return 0

        from core.tm import TranslationMemory
        import tempfile
        tmp_db = os.path.join(tempfile.gettempdir(), f"batch_upd_{os.getpid()}.db")
        if os.path.exists(tmp_db):
            os.remove(tmp_db)

        tm = TranslationMemory(tmp_db)
        tm.add_many(valid_segs, src_lang, tgt_lang)
        count = write_sdltm(tm, target_sdltm_path, src_lang, tgt_lang)
        tm.close()
        if os.path.exists(tmp_db):
            os.remove(tmp_db)

        return count

    @classmethod
    def heal_segmentation_for_files(cls, file_paths: List[str], current_tm=None) -> tuple[int, List[str]]:
        """Aplica o algoritmo inteligente de recombinação de quebras indevidas."""
        from core.segmenter import SmartSentenceSegmenter
        total_healed = 0
        details = []

        for path in file_paths:
            if current_tm and getattr(current_tm, "db_path", None) and os.path.abspath(path) == os.path.abspath(current_tm.db_path):
                cnt = current_tm.heal_broken_segmentation()
                total_healed += cnt
                details.append(f"{os.path.basename(path)}: {cnt} quebras corrigidas na memória ativa")
            elif path.endswith(".db"):
                from core.tm import TranslationMemory
                temp_tm = TranslationMemory(path)
                cnt = temp_tm.heal_broken_segmentation()
                temp_tm.close()
                total_healed += cnt
                details.append(f"{os.path.basename(path)}: {cnt} quebras corrigidas no ficheiro de projeto")
            else:
                segs = cls.extract_segments_from_file(path)
                healed_segs, cnt = SmartSentenceSegmenter.heal_broken_segments(segs)
                total_healed += cnt
                details.append(f"{os.path.basename(path)}: {cnt} quebras identificadas e recombinadas")

        return total_healed, details

