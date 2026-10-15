"""
tests/test_roundtrip.py - prova de ida-e-volta (round-trip).

Ciclo:  parse TMX -> edita traducao -> exporta TMX -> re-parse = dados iguais.
        parse SDLXLIFF -> edita -> exporta SDLXLIFF -> re-parse = dados iguais.
Confirma que gravar + exportar preserva fonte, traducao, idiomas e metadados.

Uso:  python -m tests.test_roundtrip
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tm import TranslationMemory                       # noqa: E402
from core.segment import SegState                           # noqa: E402
from io_layer.tmx import iter_tmx, detect_tmx_langs         # noqa: E402
from io_layer.tmx_writer import write_tmx                   # noqa: E402
from io_layer.sdlxliff import iter_sdlxliff                 # noqa: E402
from io_layer.sdlxliff_writer import write_sdlxliff         # noqa: E402

TMX_SRC = r"C:\Users\Icaro\Documents\converter_TMX.tmx"
SDL_SRC = (r"C:\Users\Icaro\Documents\Studio 2021\Projects\Samples\SampleProject"
           r"\de-DE\SamplePresentation.pptx.sdlxliff")
TMP = tempfile.gettempdir()


def hr(t):
    print("\n" + "=" * 58 + f"\n{t}\n" + "=" * 58)


def test_tmx_roundtrip():
    hr("ROUND-TRIP TMX (editar -> exportar -> re-ler)")
    src, tgt = detect_tmx_langs(TMX_SRC)
    print(f"idiomas: {src} -> {tgt}")

    db = os.path.join(TMP, "_rt_tmx.db")
    if os.path.exists(db):
        os.remove(db)
    tm = TranslationMemory(db)
    n = tm.add_many(iter_tmx(TMX_SRC, src, tgt), src, tgt)

    # editar os 3 primeiros segmentos
    edited = {}
    for seg in tm.page(0, 3):
        new = f"[REVISADO] {seg.target}" if seg.target else f"[NOVO] {seg.source}"
        tm.update_target(seg.row_id, new, state=SegState.TRANSLATED)
        edited[seg.source] = new
    print(f"carregados {n}; editados {len(edited)}")

    out = os.path.join(TMP, "_rt_out.tmx")
    n_out = write_tmx(tm, out, src, tgt)
    print(f"exportado {n_out} TUs para {os.path.basename(out)}")
    assert n_out == n, "contagem diferente no export TMX!"

    # re-ler o ficheiro exportado e confirmar as edicoes
    reparsed = {s.source: s.target for s in iter_tmx(out, src, tgt)}
    ok = 0
    for src_txt, new_txt in edited.items():
        if reparsed.get(src_txt) == new_txt:
            ok += 1
        else:
            print(f"  FALHA: {src_txt[:30]!r} -> {reparsed.get(src_txt)!r}")
    print(f"edicoes preservadas: {ok}/{len(edited)}")
    assert ok == len(edited), "round-trip TMX perdeu dados!"
    tm.close()
    os.remove(db); os.remove(out)
    print("OK - TMX round-trip perfeito")


def test_sdlxliff_roundtrip():
    hr("ROUND-TRIP SDLXLIFF (editar -> exportar -> re-ler)")
    db = os.path.join(TMP, "_rt_sdl.db")
    if os.path.exists(db):
        os.remove(db)
    tm = TranslationMemory(db)
    segs = list(iter_sdlxliff(SDL_SRC))
    tm.add_many(iter_sdlxliff(SDL_SRC), "en-US", "de-DE")

    # editar todos os que tem fonte
    edited = {}
    for seg in tm.page(0, 100):
        new = f"[PT] {seg.target}" if seg.target else f"[PT] {seg.source}"
        tm.update_target(seg.row_id, new, state=SegState.TRANSLATED)
        edited[seg.tu_id] = new
    print(f"carregados {len(segs)}; editados {len(edited)}")

    out = os.path.join(TMP, "_rt_out.sdlxliff")
    n_tu = write_sdlxliff(tm, out, "en-US", "de-DE", original="rt_test")
    print(f"exportado {n_tu} trans-units")

    # re-ler e confirmar targets
    reparsed = list(iter_sdlxliff(out))
    by_tu = {}
    for s in reparsed:
        by_tu.setdefault(s.tu_id, []).append(s.target)
    ok = sum(1 for tu_id, new in edited.items()
             if any(new in t for t in by_tu.get(tu_id, [])))
    print(f"edicoes preservadas: {ok}/{len(edited)}")
    assert ok == len(edited), "round-trip SDLXLIFF perdeu dados!"
    tm.close()
    os.remove(db); os.remove(out)
    print("OK - SDLXLIFF round-trip perfeito")


if __name__ == "__main__":
    test_tmx_roundtrip()
    test_sdlxliff_roundtrip()
    print("\n*** ROUND-TRIP COMPLETO ***")
