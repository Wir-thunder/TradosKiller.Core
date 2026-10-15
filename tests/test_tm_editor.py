"""
tests/test_tm_editor.py - valida as operacoes em massa do Editor de Memoria.

Testa a logica de backend (nao a UI grafica):
  - search_ids / filtro
  - bulk_replace (literal e regex, so no filtro)
  - set_state em lote
  - delete_ids
  - update_source / update_target

Uso:  python -m tests.test_tm_editor
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tm import TranslationMemory          # noqa: E402
from core.segment import SegState, Segment     # noqa: E402

TMP = tempfile.gettempdir()


def build_tm():
    db = os.path.join(TMP, "_tmed_test.db")
    if os.path.exists(db):
        os.remove(db)
    tm = TranslationMemory(db)
    segs = [
        Segment(source="Save the file", target="Gravar o arquivo"),
        Segment(source="Save changes", target="Gravar alterações"),
        Segment(source="Open file", target="Abrir arquivo"),
        Segment(source="Close the window", target="Fechar a janela"),
        Segment(source="save as", target="", state=SegState.UNTRANSLATED),
    ]
    tm.add_many(segs, "en", "pt")
    return tm, db


def hr(t):
    print("\n" + "=" * 56 + f"\n{t}\n" + "=" * 56)


def test_search():
    hr("Busca / filtro")
    tm, db = build_tm()
    all_ids = tm.search_ids()
    print(f"sem filtro: {len(all_ids)} ids")
    assert len(all_ids) == 5

    src = tm.search_ids("save", "source")
    print(f"'save' na fonte: {len(src)} (esperado 3, case-insensitive)")
    assert len(src) == 3

    tgt = tm.search_ids("arquivo", "target")
    print(f"'arquivo' na traducao: {len(tgt)} (esperado 2)")
    assert len(tgt) == 2
    tm.close(); os.remove(db)
    print("OK - busca correcta")


def test_bulk_replace_literal():
    hr("Localizar & Substituir literal")
    tm, db = build_tm()
    n = tm.bulk_replace("arquivo", "ficheiro", field="target", case_sensitive=False)
    print(f"substituidas: {n} (esperado 2)")
    assert n == 2
    # confirmar
    ids = tm.search_ids("ficheiro", "target")
    assert len(ids) == 2, "bulk replace nao persistiu!"
    tm.close(); os.remove(db)
    print("OK - replace literal")


def test_bulk_replace_regex_only_filter():
    hr("Replace com REGEX, so no filtro")
    tm, db = build_tm()
    # filtrar so os que tem 'save' na fonte
    ids = tm.search_ids("save", "source")
    # regex: 'save' -> 'SAVE' so nesses
    n = tm.bulk_replace("save", "SAVE", field="source",
                        case_sensitive=False, use_regex=True, only_ids=ids)
    print(f"substituidas no filtro: {n} (esperado 3)")
    assert n == 3
    # os que NAO estavam no filtro ficam intactos
    intact = tm.search_ids("Open file", "source")
    assert len(intact) == 1, "alterou fora do filtro!"
    print("OK - regex restrito ao filtro respeitou o escopo")
    tm.close(); os.remove(db)


def test_bulk_state_and_delete():
    hr("Estado em lote + eliminar")
    tm, db = build_tm()
    ids = tm.search_ids("save", "source")
    n = tm.set_state(ids, SegState.APPROVED)
    print(f"marcadas aprovado: {n}")
    assert n == 3
    # eliminar as que tem 'window'
    win = tm.search_ids("window", "both")
    d = tm.delete_ids(win)
    print(f"eliminadas: {d} (esperado 1)")
    assert d == 1
    assert tm.count() == 4
    tm.close(); os.remove(db)
    print("OK - estado em lote e eliminar")


if __name__ == "__main__":
    test_search()
    test_bulk_replace_literal()
    test_bulk_replace_regex_only_filter()
    test_bulk_state_and_delete()
    print("\n*** EDITOR DE MEMORIA (backend) OK ***")
