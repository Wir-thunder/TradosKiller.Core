"""
tests/test_parsers_real.py - valida os parsers contra ficheiros REAIS do Trados.

Corre com:  python -m tests.test_parsers_real
(ou python tests/test_parsers_real.py a partir da raiz do projeto)
"""
import os
import sys
import time

# permitir correr de qualquer lado
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.segment import SegState          # noqa: E402
from core.tm import TranslationMemory      # noqa: E402
from io_layer.tmx import iter_tmx, detect_tmx_langs            # noqa: E402
from io_layer.sdlxliff import iter_sdlxliff, detect_sdlxliff_langs  # noqa: E402

SAMPLES = r"C:\Users\Icaro\Documents\Studio 2021\Projects\Samples\SampleProject"
TMX_REAL = r"C:\Users\Icaro\Documents\converter_TMX.tmx"
DB = os.path.join(os.path.dirname(__file__), "_tm_test.db")


def hr(t):
    print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)


def test_sdlxliff():
    hr("SDLXLIFF (ficheiro real .docx do Trados)")
    f = os.path.join(SAMPLES, "en-US", "SecondSample.docx.sdlxliff")
    src, tgt = detect_sdlxliff_langs(f)
    print(f"idiomas detectados: source={src} target={tgt}")
    t0 = time.time()
    segs = list(iter_sdlxliff(f))
    dt = time.time() - t0
    print(f"segmentos lidos: {len(segs)} em {dt:.3f}s")
    translated = sum(1 for s in segs if s.target)
    print(f"com traducao: {translated}")
    for s in segs[:3]:
        print(f"  tu={s.tu_id[:8]}.. seg={s.seg_id} state={s.state.value} "
              f"origin={s.origin.value} | src={s.source[:45]!r} tgt={s.target[:30]!r}")
    assert len(segs) > 0, "SDLXLIFF nao produziu segmentos!"
    print("OK - SDLXLIFF valido")


def test_sdlxliff_traduzido():
    hr("SDLXLIFF traduzido (de-DE, com targets preenchidos)")
    f = os.path.join(SAMPLES, "de-DE", "SamplePresentation.pptx.sdlxliff")
    segs = list(iter_sdlxliff(f))
    print(f"segmentos: {len(segs)}")
    tr = [s for s in segs if s.target]
    print(f"traduzidos: {len(tr)}")
    for s in tr[:3]:
        print(f"  state={s.state.value} origin={s.origin.value} pct={s.percent} "
              f"| {s.source[:30]!r} -> {s.target[:30]!r}")
    print("OK - targets e metadados lidos correctamente")


def test_tmx_real():
    hr("TMX real teu (converter_TMX.tmx, tuid ausente)")
    src, tgt = detect_tmx_langs(TMX_REAL)
    print(f"idiomas: source={src} target={tgt}")
    segs = list(iter_tmx(TMX_REAL))
    print(f"segmentos: {len(segs)}")
    for s in segs[:2]:
        print(f"  tu={s.tu_id} | {s.source[:35]!r} -> {s.target[:35]!r}")
    assert all(s.tu_id for s in segs), "tuid auto-gerado falhou!"
    assert any(s.target for s in segs), "TMX sem traducao lida!"
    print("OK - TMX real valido, tuid auto-gerado com sucesso")


def test_tm_roundtrip():
    hr("TM SQLite: inserir em lote + match exacto + concordancia")
    if os.path.exists(DB):
        os.remove(DB)
    tm = TranslationMemory(DB)
    segs = list(iter_sdlxliff(os.path.join(SAMPLES, "de-DE", "SamplePresentation.pptx.sdlxliff")))
    n = tm.add_many(segs, srclang="en-US", tgtlang="de-DE")
    print(f"inseridos: {n}; count()={tm.count()}")
    tm.rebuild_fts()
    # match exacto
    probe = next((s for s in segs if s.source), None)
    if probe:
        m = tm.exact_match(probe.source)
        tgt_preview = m.target[:25] if m else None
        print(f"exact_match({probe.source[:25]!r}) -> {tgt_preview!r}")
        assert m is not None, "exact_match falhou!"
    # pagina (virtualizacao)
    page = tm.page(0, 5)
    print(f"page(0,5) -> {len(page)} segmentos (amostra para a UI)")
    tm.close()
    print("OK - TM SQLite funcional")


if __name__ == "__main__":
    test_sdlxliff()
    test_sdlxliff_traduzido()
    test_tmx_real()
    test_tm_roundtrip()
    print("\n*** TODOS OS TESTES PASSARAM ***")
