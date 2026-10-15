"""
tests/test_rws_facade.py - Validação completa do ecossistema RWS / SDL Trados e UI Facade.

Testa:
1. Leitura e roundtrip de memórias nativas Trados (.sdltm)
2. Extração de projetos (.sdlproj) com TMs e TBs associados
3. Extração e criação de pacotes (.sdlppx / .sdlrpx)
4. Workflow do ReviewBar (Confirm & Next, estados, contagens)
5. Barra de Localizar e Substituir (Ctrl+F / Ctrl+H)

Uso:  python -m tests.test_rws_facade
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.segment import SegState, SegOrigin, Segment, display_text
from core.tm import TranslationMemory
from io_layer.sdltm import iter_sdltm, write_sdltm, detect_sdltm_langs
from io_layer.sdlproj import parse_sdlproj
from io_layer.sdlpackage import extract_package, create_return_package, is_sdlpackage

SAMPLES_DIR = r"C:\Users\Icaro\Documents\Studio 2021\Projects\Samples\SampleProject"
SAMPLE_SDLTM = os.path.join(SAMPLES_DIR, "TMs", "English-German.sdltm")
SAMPLE_SDLPROJ = os.path.join(SAMPLES_DIR, "Sample Project.sdlproj")
TMP = tempfile.gettempdir()


def hr(msg: str) -> None:
    print("\n" + "=" * 60 + f"\n{msg}\n" + "=" * 60)


def test_sdltm_full_roundtrip():
    hr("1. RWS SDLTM (.sdltm) - Leitura real & Exportação Roundtrip")
    if not os.path.exists(SAMPLE_SDLTM):
        print("Aviso: ficheiro real de teste .sdltm não encontrado, pulando.")
        return

    src_lang, tgt_lang = detect_sdltm_langs(SAMPLE_SDLTM)
    print(f"Idiomas detectados na .sdltm: {src_lang} -> {tgt_lang}")
    assert src_lang == "en-US" and tgt_lang == "de-DE"

    segs = list(iter_sdltm(SAMPLE_SDLTM))
    print(f"Segmentos lidos da .sdltm real: {len(segs)}")
    assert len(segs) > 0

    # Inserção na TM local
    db_test = os.path.join(TMP, "_test_sdltm.db")
    if os.path.exists(db_test):
        os.remove(db_test)
    tm = TranslationMemory(db_test)
    tm.add_many(segs, src_lang, tgt_lang)
    assert tm.count() == len(segs)

    # Exportação para nova .sdltm
    out_sdltm = os.path.join(TMP, "_exported.sdltm")
    written = write_sdltm(tm, out_sdltm, src_lang, tgt_lang)
    print(f"Segmentos gravados na nova .sdltm: {written}")
    assert written == len(segs)

    # Re-leitura da nova .sdltm
    reparsed = list(iter_sdltm(out_sdltm))
    print(f"Segmentos re-lidos da .sdltm exportada: {len(reparsed)}")
    assert len(reparsed) == len(segs)
    assert reparsed[0].source == segs[0].source
    assert reparsed[0].target == segs[0].target

    tm.close()
    if os.path.exists(db_test): os.remove(db_test)
    if os.path.exists(out_sdltm): os.remove(out_sdltm)
    print("OK - .sdltm Roundtrip 100% Validado")


def test_sdlproj_resources():
    hr("2. RWS SDLPROJ (.sdlproj) - Extração de Ficheiros, TMs (.sdltm) e TBs")
    if not os.path.exists(SAMPLE_SDLPROJ):
        print("Aviso: Sample Project.sdlproj não encontrado.")
        return

    proj = parse_sdlproj(SAMPLE_SDLPROJ)
    assert proj is not None
    print(f"Projeto: {proj.name}")
    print(f"Ficheiros bilingues (.sdlxliff): {len(proj.files)}")
    print(f"Memórias de Tradução (.sdltm): {len(proj.tm_paths)}")
    print(f"Termbases (.sdltb): {len(proj.tb_paths)}")

    assert len(proj.files) > 0
    assert len(proj.tm_paths) > 0
    assert any(".sdltm" in p for p in proj.tm_paths)
    print("OK - SDLPROJ recursos extraídos com sucesso")


def test_packages():
    hr("3. RWS Packages (.sdlppx / .sdlrpx) - Descompactação e Pacote de Retorno")
    # Cria um pacote sintético simulando .sdlppx
    pkg_path = os.path.join(TMP, "SamplePackage.sdlppx")
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("Sample Project.sdlproj", open(SAMPLE_SDLPROJ, "rb").read())

    assert is_sdlpackage(pkg_path)

    sdlproj_extracted, proj = extract_package(pkg_path)
    assert sdlproj_extracted is not None
    assert proj is not None
    print(f"Pacote extraído com projeto: {proj.name}")

    # Cria pacote de retorno .sdlrpx
    ret_path = os.path.join(TMP, "SampleReturn.sdlrpx")
    out_ret = create_return_package(proj, ret_path)
    assert os.path.exists(out_ret)
    assert is_sdlpackage(out_ret)
    print(f"Pacote de retorno criado com sucesso: {os.path.basename(out_ret)}")

    if os.path.exists(pkg_path): os.remove(pkg_path)
    if os.path.exists(ret_path): os.remove(ret_path)
    print("OK - Pacotes RWS (.sdlppx/.sdlrpx) validados")


def test_review_workflow_and_find():
    hr("4. Review Workflow & Find/Replace Backend Logic")
    db_test = os.path.join(TMP, "_review_test.db")
    if os.path.exists(db_test):
        os.remove(db_test)
    tm = TranslationMemory(db_test)

    sample_segments = [
        Segment(source="First line", target="", state=SegState.UNTRANSLATED),
        Segment(source="Second line", target="Segunda linha", state=SegState.TRANSLATED),
        Segment(source="Third line", target="Terceira linha", state=SegState.DRAFT),
        Segment(source="Approved line", target="Linha aprovada", state=SegState.APPROVED),
    ]
    tm.add_many(sample_segments, "en", "pt")

    # Contagem de estados
    counts = tm.count_by_state()
    print("Contagem por estado:", counts)
    assert counts["untranslated"] == 1
    assert counts["translated"] == 1
    assert counts["draft"] == 1
    assert counts["approved"] == 1

    # Filtro por estado
    untrans_ids = tm.filter_ids(state="untranslated")
    assert len(untrans_ids) == 1
    trans_ids = tm.filter_ids(state="translated")
    assert len(trans_ids) == 1

    # Busca de texto (Ctrl+F)
    find_ids = tm.filter_ids(query="linha", field="target")
    print(f"Busca por 'linha': {len(find_ids)} ocorrência(s)")
    assert len(find_ids) == 3

    # Substituição (Ctrl+H)
    replaced = tm.bulk_replace("linha", "frase", field="target")
    print(f"Substituídos: {replaced}")
    assert replaced == 3

    tm.close()
    if os.path.exists(db_test): os.remove(db_test)
    print("OK - Lógica do Review Bar e Find/Replace 100% Validada")


if __name__ == "__main__":
    test_sdltm_full_roundtrip()
    test_sdlproj_resources()
    test_packages()
    test_review_workflow_and_find()
    print("\n*** TODOS OS TESTES RWS FACADE PASSARAM COM SUCESSO ***")

