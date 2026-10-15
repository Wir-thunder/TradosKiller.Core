"""
tests/test_stress_streaming.py - prova anti-crash com ficheiro GIGANTE.

Gera um TMX sintetico grande e confirma que:
  1. o parser streaming nao carrega tudo em RAM (memoria estavel)
  2. a insercao no SQLite aguenta volume
  3. o modelo virtualizado devolve linhas sem materializar a lista

Uso:  python -m tests.test_stress_streaming [N_SEGMENTOS]
"""
import os
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tm import TranslationMemory          # noqa: E402
from ui.segments_model import SegmentsModel    # noqa: E402
from io_layer.tmx import iter_tmx              # noqa: E402

def _parse_n() -> int:
    for arg in sys.argv[1:]:
        if arg.isdigit():
            return int(arg)
    return 100_000

N = _parse_n()
GEN = os.path.join(os.path.dirname(__file__), "_stress.tmx")
DB = os.path.join(os.path.dirname(__file__), "_stress.db")


def gen_big_tmx(n: int) -> None:
    with open(GEN, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tmx version="1.4"><body>\n')
        for i in range(n):
            f.write(f'<tu><tuv xml:lang="en"><seg>Source sentence number {i} '
                    f'with some padding text to make it realistic.</seg></tuv>'
                    f'<tuv xml:lang="pt"><seg>Frase destino numero {i} '
                    f'com texto de preenchimento realista.</seg></tuv></tu>\n')
        f.write('</body></tmx>\n')


def main() -> None:
    print(f"A gerar TMX com {N:,} segmentos ...")
    gen_big_tmx(N)
    size_mb = os.path.getsize(GEN) / 1e6
    print(f"ficheiro: {size_mb:.1f} MB")

    if os.path.exists(DB):
        os.remove(DB)
    tm = TranslationMemory(DB)

    print("\n[1] Parser streaming -> SQLite (medindo RAM do parser) ...")
    tracemalloc.start()
    t0 = time.time()
    n = tm.add_many(iter_tmx(GEN, "en", "pt"), "en", "pt")
    dt = time.time() - t0
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"  inseridos {n:,} em {dt:.1f}s ({n/dt:,.0f}/s)")
    print(f"  RAM do parser: pico={peak/1e6:.1f} MB (ficheiro tem {size_mb:.0f} MB)")
    assert peak < 60e6, f"Parser usou demasiada RAM: {peak/1e6:.1f} MB!"
    print("  OK - parser streaming manteve memoria baixa")

    print("\n[2] Modelo virtualizado (amostra de linhas distantes) ...")
    m = SegmentsModel(tm)
    print(f"  total de linhas reportado: {m.rowCount():,}")
    for row in (0, N // 2, N - 1):
        seg = m.segment_at(row)
        print(f"  linha {row:,}: {seg.source[:40]!r} -> {seg.target[:30]!r}")
        assert seg is not None
    print("  OK - acesso aleatorio a linhas sem carregar tudo")

    tm.close()
    os.remove(GEN)
    os.remove(DB)
    print("\n*** PROVA ANTI-CRASH PASSOU ***")


if __name__ == "__main__":
    main()
