"""Regression tests for hidden inline codes and XML-safe export."""
from __future__ import annotations

import os
import tempfile
import xml.etree.ElementTree as ET

from PySide6.QtCore import QCoreApplication

from core.segment import SegState, display_text
from core.tm import TranslationMemory
from io_layer.sdlxliff import iter_sdlxliff
from io_layer.sdlxliff_writer import write_sdlxliff
from io_layer.tmx import iter_tmx
from io_layer.tmx_writer import write_tmx
from ui.segments_model import SegmentsModel
from ui.tm_model import TmEditorModel


def test_inline_tags_stay_hidden_and_export_as_elements() -> None:
    _app = QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory() as directory:
        source_tmx = os.path.join(directory, "source.tmx")
        output_tmx = os.path.join(directory, "output.tmx")
        source_sdl = os.path.join(directory, "source.sdlxliff")
        output_sdl = os.path.join(directory, "output.sdlxliff")
        database = os.path.join(directory, "segments.db")

        with open(source_tmx, "w", encoding="utf-8") as file:
            file.write(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<tmx version="1.4"><body><tu>'
                '<tuv xml:lang="en"><seg><bpt i="1">&lt;b&gt;</bpt>'
                'Hello<ept i="1">&lt;/b&gt;</ept></seg></tuv>'
                '<tuv xml:lang="pt"><seg>Olá</seg></tuv>'
                '</tu></body></tmx>'
            )

        tm = TranslationMemory(database)
        tm.add_many(iter_tmx(source_tmx, "en", "pt"), "en", "pt")
        segment = tm.page(0, 1)[0]
        assert display_text(segment.source) == "Hello"
        assert "{" not in display_text(segment.source)
        editor_model = SegmentsModel(tm)
        assert editor_model.data(editor_model.index(0, 0)) == "Hello"
        memory_model = TmEditorModel(tm)
        assert memory_model.data(memory_model.index(0, 1)) == "Hello"

        tm.update_target(segment.row_id, "Olá {1} mundo", SegState.TRANSLATED)
        saved = tm.get_row(segment.row_id)
        assert saved is not None
        assert display_text(saved.target) == "Olá {1} mundo"
        assert len(saved.target_tags) == 2

        write_tmx(tm, output_tmx, "en", "pt")
        tm.close()
        tmx_segment = next(iter_tmx(output_tmx, "en", "pt"))
        assert display_text(tmx_segment.source) == "Hello"
        assert display_text(tmx_segment.target) == "Olá {1} mundo"
        assert len(tmx_segment.source_tags) == 2
        assert len(tmx_segment.target_tags) == 2

        with open(source_sdl, "w", encoding="utf-8") as file:
            file.write(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" '
                'xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" version="1.2">'
                '<file source-language="en" target-language="pt"><body>'
                '<trans-unit id="unit-1"><seg-source><mrk mtype="seg" mid="1">'
                '<g id="bold">Hello</g></mrk></seg-source><target/>'
                '<sdl:seg-defs><sdl:seg id="1" conf="Unspecified"/></sdl:seg-defs>'
                '</trans-unit></body></file></xliff>'
            )

        sdl_tm = TranslationMemory(os.path.join(directory, "sdl.db"))
        sdl_tm.add_many(iter_sdlxliff(source_sdl), "en", "pt")
        sdl_segment = sdl_tm.page(0, 1)[0]
        assert display_text(sdl_segment.source) == "Hello"
        assert len(sdl_segment.source_tags) == 2
        sdl_model = SegmentsModel(sdl_tm)
        assert sdl_model.data(sdl_model.index(0, 0)) == "Hello"
        sdl_tm.update_target(sdl_segment.row_id, "Olá", SegState.TRANSLATED)
        write_sdlxliff(sdl_tm, output_sdl, "en", "pt")
        sdl_tm.close()

        tree = ET.parse(output_sdl)
        ns = {"x": "urn:oasis:names:tc:xliff:document:1.2"}
        target_mrk = tree.find(".//x:target/x:mrk", ns)
        assert target_mrk is not None
        assert "".join(target_mrk.itertext()) == "Olá"
        assert len(list(target_mrk)) == 1
        assert target_mrk[0].tag.endswith("}g")
        assert display_text(next(iter_sdlxliff(output_sdl)).target) == "Olá"


if __name__ == "__main__":
    test_inline_tags_stay_hidden_and_export_as_elements()
    print("Inline tag safety OK")
