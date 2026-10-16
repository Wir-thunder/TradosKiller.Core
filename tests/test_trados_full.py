"""
tests.test_trados_full - Testes automatizados da fachada Trados Studio, Xbench QA e TM Utility.
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.segment import Segment, SegState, SegOrigin
from core.xbench_qa import XbenchQAEngine
from core.project import Project, is_project_file
from core.config import Config
from core.tm import TranslationMemory, _decode_tags
from io_layer.sdlproj import parse_sdlproj, is_sdlproj_file
from io_layer.sdlxliff import iter_sdlxliff


class TestTradosFull(unittest.TestCase):

    def test_xbench_qa_engine(self):
        engine = XbenchQAEngine()
        segs = [
            Segment(source="Total: 100 items", target="Total: 200 items", state=SegState.TRANSLATED),
            Segment(source="Untranslated text", target="", state=SegState.UNTRANSLATED),
            Segment(source="Sentence ending with dot.", target="Sentence without dot", state=SegState.TRANSLATED),
            Segment(source="Text with  double  space", target="Texto com  espaço  duplo", state=SegState.TRANSLATED),
            Segment(source="Consistent source", target="Translation A", state=SegState.TRANSLATED),
            Segment(source="Consistent source", target="Translation B", state=SegState.TRANSLATED),
        ]
        issues = engine.run_qa(segs)
        types = {i.issue_type for i in issues}
        self.assertIn("Numeric Mismatch", types)
        self.assertIn("Untranslated Segment", types)
        self.assertIn("Trailing Punctuation", types)
        self.assertIn("Double Spaces", types)
        self.assertIn("Source Inconsistency", types)

    def test_safe_config_and_project_load(self):
        # Empty file / non-json must not throw JSONDecodeError
        p = Project.load("non_existent_file.catproj")
        self.assertIsNotNone(p)
        c = Config.load("non_existent_config.json")
        self.assertIsNotNone(c)
        tags = _decode_tags("")
        self.assertEqual(tags, [])
        tags_invalid = _decode_tags("{invalid json")
        self.assertEqual(tags_invalid, [])

    def test_load_real_sdlproj_and_sdlxliff(self):
        sdlproj_path = r"C:\Users\Icaro\Documents\Studio 2021\Projects\Samples\SampleProject\Sample Project.sdlproj"
        sdlxliff_path = r"C:\Users\Icaro\Documents\Studio 2021\Projects\Samples\SampleProject\en-US\SecondSample.docx.sdlxliff"

        if os.path.exists(sdlproj_path):
            self.assertTrue(is_sdlproj_file(sdlproj_path))
            self.assertTrue(is_project_file(sdlproj_path))
            proj = Project.load(sdlproj_path)
            self.assertIsNotNone(proj)
            self.assertGreater(len(proj.files), 0)

        if os.path.exists(sdlxliff_path):
            segs = list(iter_sdlxliff(sdlxliff_path))
            self.assertGreater(len(segs), 0)
            self.assertTrue(any(s.source for s in segs))

    def test_advanced_display_filter(self):
        from core.advanced_filter import AdvancedFilterCriteria, apply_advanced_filter
        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "test_adf.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        tm = TranslationMemory(db_file)
        segs = [
            Segment(source="First line", target="Primeira linha", state=SegState.TRANSLATED, percent=100),
            Segment(source="Second line 123", target="", state=SegState.UNTRANSLATED, percent=0),
            Segment(source="Third line", target="Terceira linha", state=SegState.DRAFT, percent=85),
        ]
        tm.add_many(segs, "en", "pt")

        # 1. Test untranslated filter
        c1 = AdvancedFilterCriteria(statuses={"untranslated"})
        ids1 = tm.apply_advanced_filter(c1)
        self.assertEqual(len(ids1), 1)

        # 2. Test regex filter
        c2 = AdvancedFilterCriteria(source_text=r"\d+", source_mode="regex")
        ids2 = tm.apply_advanced_filter(c2)
        self.assertEqual(len(ids2), 1)

        # 3. Test percent range
        c3 = AdvancedFilterCriteria(filter_by_percent=True, min_percent=80, max_percent=90)
        ids3 = tm.apply_advanced_filter(c3)
        self.assertEqual(len(ids3), 1)

        # 4. Test reverse
        c4 = AdvancedFilterCriteria(statuses={"untranslated"}, reverse=True)
        ids4 = tm.apply_advanced_filter(c4)
        self.assertEqual(len(ids4), 2)

        # 5. Test OR operator
        c5 = AdvancedFilterCriteria(statuses={"untranslated"}, filter_by_percent=True, min_percent=100, max_percent=100, operator="OR")
        ids5 = tm.apply_advanced_filter(c5)
        self.assertEqual(len(ids5), 2)

        tm.close()
        if os.path.exists(db_file):
            os.remove(db_file)

    def test_trados_display_filter_and_reset(self):
        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "test_df.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        tm = TranslationMemory(db_file)
        segs = [
            Segment(source="Hello World", target="Olá Mundo", state=SegState.TRANSLATED),
            Segment(source="Hello Galaxy", target="", state=SegState.UNTRANSLATED),
            Segment(source="Goodbye World", target="Adeus Mundo", state=SegState.DRAFT),
            Segment(source="Special Approved Text", target="Texto Aprovado Especial", state=SegState.APPROVED),
            Segment(source="Bad Translation", target="Tradução Ruim", state=SegState.REJECTED),
        ]
        tm.add_many(segs, "en", "pt")

        from ui.segments_model import SegmentsModel
        model = SegmentsModel(tm)
        self.assertEqual(model.rowCount(), 5)

        # 1. Filter by status: Not Translated / untranslated
        count_untrans = model.apply_filter(query="", field="both", state="untranslated")
        self.assertEqual(count_untrans, 1)

        # 2. Filter by status: Draft
        count_draft = model.apply_filter(query="", field="both", state="draft")
        self.assertEqual(count_draft, 1)

        # 3. Filter by query in source (case insensitive)
        count_query = model.apply_filter(query="hello", field="source", state="all")
        self.assertEqual(count_query, 2)

        # 4. Filter by query in source (case sensitive)
        count_case = model.apply_filter(query="HELLO", field="source", state="all", case_sensitive=True)
        self.assertEqual(count_case, 0)

        count_case_match = model.apply_filter(query="Hello", field="source", state="all", case_sensitive=True)
        self.assertEqual(count_case_match, 2)

        # 5. Clear filter / reset
        model.clear_filter()
        self.assertEqual(model.rowCount(), 5)

        tm.close()
        if os.path.exists(db_file):
            os.remove(db_file)

    def test_ribbon_review_tab_and_display_filter_signals(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ui.ribbon import RibbonBar
        r = RibbonBar()
        r.set_view_context("editor")

        # Tabs must include Home, Review, View & TMs
        tab_names = [r.tabText(i) for i in range(r.count())]
        self.assertIn("Home", tab_names)
        self.assertIn("Review", tab_names)

        # Verify Display Filter controls exist on RibbonBar
        self.assertTrue(hasattr(r, "df_combo_status"))
        self.assertTrue(hasattr(r, "df_combo_field"))
        self.assertTrue(hasattr(r, "df_search_input"))
        self.assertTrue(hasattr(r, "df_chk_case"))
        self.assertTrue(hasattr(r, "df_btn_refresh"))
        self.assertTrue(hasattr(r, "df_btn_reset"))
        self.assertTrue(hasattr(r, "df_btn_adf"))

        # Verify items in combo boxes
        status_items = [r.df_combo_status.itemText(i) for i in range(r.df_combo_status.count())]
        self.assertIn("All segments", status_items)
        self.assertIn("Not Translated", status_items)
        self.assertIn("Draft", status_items)
        self.assertIn("Translated", status_items)
        self.assertIn("Translation Approved", status_items)
        self.assertIn("Translation Rejected", status_items)

        # Test trigger signal
        emitted_signals = []
        r.display_filter_changed.connect(lambda q, f, s, c: emitted_signals.append((q, f, s, c)))

        r.df_search_input.setText("test query")
        r.df_combo_field.setCurrentIndex(1) # In Target
        r.df_combo_status.setCurrentIndex(1) # Not Translated
        r.df_chk_case.setChecked(True)

        self.assertGreater(len(emitted_signals), 0)
        last_sig = emitted_signals[-1]
        self.assertEqual(last_sig[0], "test query")
        self.assertEqual(last_sig[1], "In Target")
        self.assertEqual(last_sig[2], "Not Translated")
        self.assertTrue(last_sig[3])

        # Test reset signal
        reset_emitted = []
        r.display_filter_reset.connect(lambda: reset_emitted.append(True))
        r._on_display_filter_reset()
        self.assertTrue(reset_emitted)
        self.assertEqual(r.df_search_input.text(), "")
        self.assertEqual(r.df_combo_status.currentIndex(), 0)
        self.assertFalse(r.df_chk_case.isChecked())

    def test_editor_screen_display_filter(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ui.screens.editor_screen import EditorScreen
        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "test_editor_df.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        tm = TranslationMemory(db_file)
        segs = [
            Segment(source="Alpha source", target="Alpha target", state=SegState.TRANSLATED),
            Segment(source="Beta source", target="", state=SegState.UNTRANSLATED),
            Segment(source="Gamma source", target="Gamma draft", state=SegState.DRAFT),
        ]
        tm.add_many(segs, "en", "pt")

        editor = EditorScreen()
        editor._on_file_loaded(tm, "en", "pt", 3)

        self.assertEqual(editor.model.rowCount(), 3)
        self.assertFalse(editor.adv_filter.isVisible())

        # Test apply_display_filter with status string
        cnt = editor.apply_display_filter(query="", field="In Both", status_str="Not Translated")
        self.assertEqual(cnt, 1)
        self.assertEqual(editor.model.rowCount(), 1)
        self.assertEqual(editor._current_row, 0)

        # Test reset_display_filter
        editor.reset_display_filter()
        self.assertEqual(editor.model.rowCount(), 3)

        # Test search query
        cnt2 = editor.apply_display_filter(query="alpha", field="In Source", status_str="All segments")
        self.assertEqual(cnt2, 1)

        # Toggle ADF panel
        self.assertTrue(editor.adv_filter.isHidden())
        editor.toggle_advanced_filter()
        self.assertFalse(editor.adv_filter.isHidden())
        editor.toggle_advanced_filter()
        self.assertTrue(editor.adv_filter.isHidden())

        tm.close()
        if os.path.exists(db_file):
            os.remove(db_file)

    def test_batch_tasks_engine_and_dialog(self):
        from core.batch_tasks import BatchTaskEngine, count_words, count_chars
        from core.segment import Segment, SegState
        import tempfile

        # 1. Word and char count
        self.assertEqual(count_words("Hello world! This is a test."), 6)
        self.assertEqual(count_chars("Test"), 4)

        # 2. Pretranslate
        db_file = os.path.join(tempfile.gettempdir(), "test_bt_tm.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        tm = TranslationMemory(db_file)
        tm_segs = [
            Segment(source="Exact Match", target="Correspondência Exata", state=SegState.TRANSLATED),
        ]
        tm.add_many(tm_segs, "en", "pt")

        untranslated = [
            Segment(source="Exact Match", target="", state=SegState.UNTRANSLATED),
            Segment(source="Unknown sentence", target="", state=SegState.UNTRANSLATED),
        ]
        cnt = BatchTaskEngine.pretranslate_segments(untranslated, tm, confirm=True)
        self.assertEqual(cnt, 1)
        self.assertEqual(untranslated[0].target, "Correspondência Exata")
        self.assertEqual(untranslated[0].state, SegState.TRANSLATED)

        # 3. Batch Tasks Dialog instantiation
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ui.batch_tasks_dialog import BatchTasksDialog
        dialog = BatchTasksDialog(current_tm=tm, initial_task="analyze")
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.task_combo.currentIndex(), 0)

        # Switch to pretranslate
        dialog.task_combo.setCurrentIndex(1)
        self.assertFalse(dialog.options_frame.isHidden())

        tm.close()
        if os.path.exists(db_file):
            os.remove(db_file)

    def test_smart_sentence_segmenter(self):
        from core.segmenter import SmartSentenceSegmenter
        segmenter = SmartSentenceSegmenter()

        # 1. Abbreviations & Titles (Dr., Mr., Mrs., etc., U.S.)
        text1 = "Dr. Smith visited the U.S. embassy. He met Mr. Doe and Mrs. Doe at 10 a.m. sharp."
        sents1 = segmenter.split_into_sentences(text1)
        self.assertEqual(len(sents1), 2)
        self.assertEqual(sents1[0], "Dr. Smith visited the U.S. embassy.")
        self.assertEqual(sents1[1], "He met Mr. Doe and Mrs. Doe at 10 a.m. sharp.")

        # 2. Currency, Decimals, Versions
        text2 = "The total price is $19.99 per item. Version v2.1.0 was released yesterday."
        sents2 = segmenter.split_into_sentences(text2)
        self.assertEqual(len(sents2), 2)
        self.assertEqual(sents2[0], "The total price is $19.99 per item.")
        self.assertEqual(sents2[1], "Version v2.1.0 was released yesterday.")

        # 3. Portuguese Corporate / Legal
        text3 = "A empresa XPTO Ltda. foi notificada pelo Dr. Carlos. O processo nº 123 corre no tribunal."
        sents3 = segmenter.split_into_sentences(text3)
        self.assertEqual(len(sents3), 2)
        self.assertEqual(sents3[0], "A empresa XPTO Ltda. foi notificada pelo Dr. Carlos.")
        self.assertEqual(sents3[1], "O processo nº 123 corre no tribunal.")

        # 4. Auto-healing broken segments from legacy Trados rules
        broken_segs = [
            Segment(source="Please contact Dr.", target="Por favor contate o Dr.", state=SegState.TRANSLATED),
            Segment(source="Smith for details.", target="Smith para detalhes.", state=SegState.TRANSLATED),
            Segment(source="This is a second sentence.", target="Esta é uma segunda frase.", state=SegState.TRANSLATED),
            Segment(source="A empresa XPTO Ltda.", target="A empresa XPTO Ltda.", state=SegState.TRANSLATED),
            Segment(source="apresentou recurso hoje.", target="apresentou recurso hoje.", state=SegState.TRANSLATED),
        ]
        healed, count = SmartSentenceSegmenter.heal_broken_segments(broken_segs)
        self.assertEqual(count, 2)
        self.assertEqual(len(healed), 3)
        self.assertEqual(healed[0].source, "Please contact Dr. Smith for details.")
        self.assertEqual(healed[0].target, "Por favor contate o Dr. Smith para detalhes.")
        self.assertEqual(healed[1].source, "This is a second sentence.")
        self.assertEqual(healed[2].source, "A empresa XPTO Ltda. apresentou recurso hoje.")

    def test_tm_merge_split_and_heal(self):
        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "test_merge_split.db")
        if os.path.exists(db_file):
            os.remove(db_file)

        tm = TranslationMemory(db_file)
        segs = [
            Segment(source="First part.", target="Primeira parte.", state=SegState.TRANSLATED),
            Segment(source="Second part.", target="Segunda parte.", state=SegState.TRANSLATED),
            Segment(source="Third sentence.", target="Terceira frase.", state=SegState.TRANSLATED),
        ]
        tm.add_many(segs, "en", "pt")
        rows = list(tm.iter_all())
        self.assertEqual(len(rows), 3)

        id1, id2, id3 = rows[0].row_id, rows[1].row_id, rows[2].row_id

        # Merge row 1 and row 2
        merged_id = tm.merge_segments(id1, id2)
        self.assertEqual(merged_id, id1)

        rows_after_merge = list(tm.iter_all())
        self.assertEqual(len(rows_after_merge), 2)
        self.assertEqual(rows_after_merge[0].source, "First part. Second part.")
        self.assertEqual(rows_after_merge[0].target, "Primeira parte. Segunda parte.")

        # Split row 1 at "First part."
        split_res = tm.split_segment(id1, len("First part."))
        self.assertIsNotNone(split_res)
        rows_after_split = list(tm.iter_all())
        self.assertEqual(len(rows_after_split), 3)
        self.assertEqual(rows_after_split[0].source, "First part.")
        self.assertEqual(rows_after_split[1].source, "Second part.")

        # Test heal_broken_segmentation on TM
        broken_tm_file = os.path.join(tempfile.gettempdir(), "test_heal_tm.db")
        if os.path.exists(broken_tm_file):
            os.remove(broken_tm_file)
        broken_tm = TranslationMemory(broken_tm_file)
        broken_tm.add_many([
            Segment(source="Dr.", target="Dr.", state=SegState.TRANSLATED),
            Segment(source="Watson arrived.", target="Watson chegou.", state=SegState.TRANSLATED),
        ], "en", "pt")

        healed_count = broken_tm.heal_broken_segmentation()
        self.assertEqual(healed_count, 1)
        healed_rows = list(broken_tm.iter_all())
        self.assertEqual(len(healed_rows), 1)
        self.assertEqual(healed_rows[0].source, "Dr. Watson arrived.")

        tm.close()
        broken_tm.close()
        if os.path.exists(db_file):
            os.remove(db_file)
        if os.path.exists(broken_tm_file):
            os.remove(broken_tm_file)

    def test_editor_merge_and_split(self):
        from ui.screens.editor_screen import EditorScreen
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        import tempfile
        db_file = os.path.join(tempfile.gettempdir(), "test_editor_ms.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        tm = TranslationMemory(db_file)
        segs = [
            Segment(source="Hello world.", target="Olá mundo.", state=SegState.TRANSLATED),
            Segment(source="How are you?", target="Como vai?", state=SegState.TRANSLATED),
        ]
        tm.add_many(segs, "en", "pt")

        editor = EditorScreen()
        editor._on_file_loaded(tm, "en", "pt", 2)
        self.assertEqual(editor.model.rowCount(), 2)

        # Merge first with next
        editor._current_row = 0
        success = editor.merge_with_next_segment()
        self.assertTrue(success)
        self.assertEqual(editor.model.rowCount(), 1)
        self.assertEqual(editor.model.segment_at(0).source, "Hello world. How are you?")

        tm.close()
        if os.path.exists(db_file):
            os.remove(db_file)

    def test_adf_panel_and_generate_dialog(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from ui.advanced_display_filter import AdvancedDisplayFilterPanel
        from ui.generate_filtered_dialog import GenerateFilteredDialog
        import tempfile

        panel = AdvancedDisplayFilterPanel()
        self.assertIsNotNone(panel)
        self.assertGreater(panel.list_available.count(), 5)

        # Add "Not Translated" attribute
        panel._add_attribute("Not Translated")
        self.assertEqual(panel.list_selected.count(), 1)
        self.assertIn("Not Translated", panel.txt_filters_applied.text())

        # Test criteria generated
        crit = panel.get_criteria()
        self.assertIn("untranslated", crit.statuses)
        self.assertEqual(crit.operator, "AND")

        # Test reverse toggle
        panel.toggle_reverse()
        self.assertTrue(panel._is_reversed)
        self.assertIn("[REVERSE]", panel.txt_filters_applied.text())

        # Test clear
        panel.clear_filter()
        self.assertEqual(panel.list_selected.count(), 0)
        self.assertFalse(panel._is_reversed)

        # Test GenerateFilteredDialog exports
        filtered_segs = [
            Segment(source="Hello world", target="Olá mundo", state=SegState.TRANSLATED, percent=100, row_id=1),
            Segment(source="Pending item", target="", state=SegState.UNTRANSLATED, percent=0, row_id=2),
        ]
        dialog = GenerateFilteredDialog(
            segments=filtered_segs,
            total_segments_count=5,
            filter_summary="Untranslated",
            src_lang="en-US",
            tgt_lang="pt-PT",
            source_file_name="Sample.docx"
        )
        self.assertIsNotNone(dialog)

        # 1. Test CSV Excel export
        csv_path = os.path.join(tempfile.gettempdir(), "test_gen_export.csv")
        dialog._write_csv(csv_path)
        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("Hello world", content)
            self.assertIn("Olá mundo", content)
        os.remove(csv_path)

        # 2. Test SDLXLIFF export with segments
        from io_layer.sdlxliff_writer import write_sdlxliff
        sdlxliff_path = os.path.join(tempfile.gettempdir(), "test_gen_export.sdlxliff")
        cnt = write_sdlxliff(out_path=sdlxliff_path, segments=filtered_segs)
        self.assertEqual(cnt, 2)
        self.assertTrue(os.path.exists(sdlxliff_path))
        os.remove(sdlxliff_path)

        # 3. Test TMX export with segments
        from io_layer.tmx_writer import write_tmx
        tmx_path = os.path.join(tempfile.gettempdir(), "test_gen_export.tmx")
        cnt_tmx = write_tmx(out_path=tmx_path, segments=filtered_segs)
        self.assertEqual(cnt_tmx, 2)
        self.assertTrue(os.path.exists(tmx_path))
        os.remove(tmx_path)


    def test_attached_tm_lifecycle(self):
        import tempfile
        from core.attached_tm import AttachedTMConfig, AttachedTMManager
        from io_layer.sdltm import create_empty_sdltm, insert_or_update_sdltm_unit

        sdltm_path = os.path.join(tempfile.gettempdir(), "test_lifecycle.sdltm")
        if os.path.exists(sdltm_path):
            os.remove(sdltm_path)

        # 1. Cria nova memória SDLTM vazia
        ok_create = create_empty_sdltm(sdltm_path, src_lang="en-US", tgt_lang="pt-PT")
        self.assertTrue(ok_create)
        self.assertTrue(os.path.exists(sdltm_path))

        # 2. Insere unidade na memória
        ok_ins = insert_or_update_sdltm_unit(sdltm_path, "Welcome to SDL Trados", "Bem-vindo ao SDL Trados", "en-US", "pt-PT")
        self.assertTrue(ok_ins)

        # 3. Cria configuração de TM anexada
        tm_cfg = AttachedTMConfig(path=sdltm_path, name="TestTM", enabled=True, lookup=True, concordance=True, update=True, penalty=0)
        self.assertEqual(tm_cfg.file_type, "File-based SDLTM")

        # 4. Consulta correspondência exata (100%)
        matches = AttachedTMManager.query_matches("Welcome to SDL Trados", [tm_cfg])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].percent, 100)
        self.assertEqual(matches[0].target, "Bem-vindo ao SDL Trados")
        self.assertTrue(matches[0].is_exact)

        # 5. Testa penalidade (penalty=5%)
        tm_cfg_pen = AttachedTMConfig(path=sdltm_path, name="PenTM", penalty=5)
        matches_pen = AttachedTMManager.query_matches("Welcome to SDL Trados", [tm_cfg_pen])
        self.assertEqual(len(matches_pen), 1)
        self.assertEqual(matches_pen[0].percent, 95)

        # 6. Testa correspondência parcial (Fuzzy)
        matches_fuzzy = AttachedTMManager.query_matches("Welcome to the SDL Trados Studio", [tm_cfg], min_match=60)
        self.assertGreater(len(matches_fuzzy), 0)
        self.assertGreaterEqual(matches_fuzzy[0].percent, 60)

        # 7. Testa atualização em tempo real (Update)
        cnt_upd = AttachedTMManager.update_tms("New source phrase", "Nova frase traduzida", [tm_cfg], "en-US", "pt-PT")
        self.assertEqual(cnt_upd, 1)

        # Verifica se a nova frase foi gravada e é encontrada com 100%
        matches_new = AttachedTMManager.query_matches("New source phrase", [tm_cfg])
        self.assertEqual(len(matches_new), 1)
        self.assertEqual(matches_new[0].target, "Nova frase traduzida")

        # 8. Testa busca de concordância (F3)
        conc = AttachedTMManager.concordance_search("Trados", [tm_cfg])
        self.assertGreaterEqual(len(conc), 1)
        self.assertTrue(any("Trados" in c.source for c in conc))

        if os.path.exists(sdltm_path):
            os.remove(sdltm_path)

    def test_editor_screen_tm_association(self):
        import tempfile
        from PySide6.QtWidgets import QApplication
        from ui.screens.editor_screen import EditorScreen
        from core.segment import Segment, SegState
        from core.tm import TranslationMemory
        from io_layer.sdltm import create_empty_sdltm, insert_or_update_sdltm_unit

        app = QApplication.instance()
        if not app:
            app = QApplication([])

        editor = EditorScreen()
        self.assertEqual(len(editor.attached_tms), 0)
        self.assertIn("Nenhuma TM associada", editor.lbl_attached_tm.text())

        # Cria TM temporária e popula
        sdltm_path = os.path.join(tempfile.gettempdir(), "test_editor_assoc.sdltm")
        if os.path.exists(sdltm_path):
            os.remove(sdltm_path)
        create_empty_sdltm(sdltm_path, "en-US", "pt-PT")
        insert_or_update_sdltm_unit(sdltm_path, "File settings", "Configurações de ficheiro", "en-US", "pt-PT")

        # Associa ao EditorScreen
        editor.attach_tm(sdltm_path, lookup=True, concordance=True, update=True)
        self.assertEqual(len(editor.attached_tms), 1)
        self.assertIn("TM Ativa", editor.lbl_attached_tm.text())

        # Carrega um TranslationMemory local com um segmento para teste
        db_path = os.path.join(tempfile.gettempdir(), "test_editor_local.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        tm_local = TranslationMemory(db_path)
        tm_local.add_many([Segment(source="File settings", target="", state=SegState.UNTRANSLATED)], "en-US", "pt-PT")
        editor._on_file_loaded(tm_local, "en-US", "pt-PT", 1)

        # Verifica correspondência de TM
        self.assertIn("Configurações de ficheiro", editor.fuzzy_edit.toPlainText())

        # Testa aplicar correspondência (Ctrl+T)
        editor._apply_best_match()
        self.assertEqual(editor.tgt_edit.toPlainText(), "Configurações de ficheiro")

        # Grava e confirma segmento (Ctrl+Enter / save_current)
        editor.tgt_edit.setPlainText("Configurações atualizadas")
        editor.save_current()

        # Verifica se o arquivo .sdltm anexado foi atualizado com o novo target
        from core.attached_tm import AttachedTMManager
        updated_matches = AttachedTMManager.query_matches("File settings", editor.attached_tms)
        self.assertEqual(len(updated_matches), 1)
        self.assertEqual(updated_matches[0].target, "Configurações atualizadas")

        # Limpeza
        tm_local.close()
        if os.path.exists(sdltm_path):
            os.remove(sdltm_path)
        if os.path.exists(db_path):
            os.remove(db_path)

    def test_projects_screen_trados_layout(self):
        from PySide6.QtWidgets import QApplication
        from ui.screens.projects_screen import ProjectsScreen
        from core.project import Project

        app = QApplication.instance() or QApplication([])
        screen = ProjectsScreen()

        # 1. Verifica painel de filtro esquerdo
        self.assertIsNotNone(screen.left_filter_panel)
        self.assertIsNotNone(screen.txt_filter_name)
        self.assertIsNotNone(screen.combo_filter_status)
        self.assertIsNotNone(screen.combo_filter_type)

        # 2. Verifica 9 colunas da tabela de projetos (incluindo Progress bar)
        self.assertEqual(screen.table_projects.columnCount(), 9)
        cols = [screen.table_projects.horizontalHeaderItem(i).text() for i in range(9)]
        self.assertEqual(cols, ["Name", "Status", "Progress", "Due Date", "Created At", "Type", "Location", "Server", "Organization"])

        # 3. Verifica abas inferiores de detalhes (5 abas South)
        self.assertEqual(screen.tab_details.count(), 5)
        tab_names = [screen.tab_details.tabText(i) for i in range(5)]
        self.assertTrue(any("Project Details" in t for t in tab_names))
        self.assertTrue(any("Confirmation Statistics" in t for t in tab_names))
        self.assertTrue(any("Analysis Statistics" in t for t in tab_names))
        self.assertTrue(any("Task History" in t for t in tab_names))
        self.assertTrue(any("Project Attributes" in t for t in tab_names))

        # 4. Testa atualização dos detalhes
        test_proj = Project(name="Toyota_Test_Project", location="C:/Projects", source_lang="en-US", target_lang="pt-BR")
        screen._update_details_panel(test_proj)
        self.assertIn("Toyota_Test_Project", screen.lbl_details_title.text())
        self.assertGreater(screen.table_prop_details.rowCount(), 5)

        # 5. Testa filtro por nome
        screen.txt_filter_name.setText("NonExistentProjectNameXYZ")
        self.assertEqual(screen.table_projects.rowCount(), 0)
        screen.txt_filter_name.setText("")
        self.assertGreaterEqual(screen.table_projects.rowCount(), 1)

    def test_files_screen_trados_layout(self):
        from PySide6.QtWidgets import QApplication
        from ui.screens.files_screen import FilesScreen, ProgressBarCellWidget
        from core.project import Project, ProjectFile

        app = QApplication.instance() or QApplication([])
        screen = FilesScreen()

        # 1. Verifica painel lateral esquerdo
        self.assertIsNotNone(screen.left_filter_panel)
        self.assertIsNotNone(screen.txt_filter_name)
        self.assertIsNotNone(screen.combo_filter_lang)
        self.assertIsNotNone(screen.tree_folders)

        # 2. Verifica 10 colunas da tabela de ficheiros (incluindo Segments e Words)
        self.assertEqual(screen.table_files.columnCount(), 10)
        cols = [screen.table_files.horizontalHeaderItem(i).text() for i in range(10)]
        self.assertEqual(cols, ["Name", "Segments", "Words", "Status", "Progress", "Size", "Usage", "File Type Ident.", "Path", "Cloud Task"])

        # 3. Verifica 5 abas inferiores
        self.assertEqual(screen.tab_details.count(), 5)
        tab_names = [screen.tab_details.tabText(i) for i in range(5)]
        self.assertTrue(any("File Details" in t for t in tab_names))
        self.assertTrue(any("Analysis Statistics" in t for t in tab_names))
        self.assertTrue(any("Confirmation Statistics" in t for t in tab_names))
        self.assertTrue(any("Task History" in t for t in tab_names))
        self.assertTrue(any("File Attributes" in t for t in tab_names))

        # 4. Popula projeto com ficheiro de teste
        proj = Project(name="Sample_Toyota", source_lang="en-US", target_lang="pt-BR")
        f1 = ProjectFile(
            path="C:/Projects/Sample_Toyota/pt-BR/sample.xlsx.sdlxliff",
            words=648,
            segment_count=100,
            translated_count=38,
            status="In Translation",
            usage="Translatable",
            file_type_ident="SpreadsheetML v. 1"
        )
        proj.files.append(f1)
        screen.set_project(proj)

        # 5. Verifica dados renderizados na tabela
        self.assertEqual(screen.table_files.rowCount(), 1)
        self.assertIn("sample.xlsx.sdlxliff", screen.table_files.item(0, 0).text())
        self.assertEqual(screen.table_files.item(0, 1).text(), "100")  # Segments
        self.assertEqual(screen.table_files.item(0, 2).text(), "648")  # Words
        self.assertEqual(screen.table_files.item(0, 3).text(), "In Translation")  # Status

        # Verifica célula com ProgressBarCellWidget (coluna 4)
        cell_widget = screen.table_files.cellWidget(0, 4)
        self.assertIsInstance(cell_widget, ProgressBarCellWidget)
        self.assertEqual(cell_widget.bar.value(), 38)

        # 6. Verifica atualização dos detalhes do ficheiro
        screen.table_files.selectRow(0)
        self.assertIn("sample.xlsx.sdlxliff", screen.lbl_details_title.text())
        self.assertGreater(screen.table_prop_details.rowCount(), 5)

    def test_slm_modelfile_and_dataset_export(self):
        from core.slm import SLMTrainer, OllamaClient
        import tempfile
        import json

        pairs = [
            ("Disconnect the cable from the battery negative terminal.", "Desconecte o cabo do terminal negativo da bateria."),
            ("Inspect the engine oil level.", "Inspecione o nível do óleo do motor."),
            ("Tighten the bolt to 25 N*m.", "Aperte o parafuso a 25 N*m.")
        ]

        # 1. Test Modelfile generation
        modelfile = SLMTrainer.build_modelfile(
            base_model="llama3.2:latest",
            few_shot_pairs=pairs,
            temperature=0.1
        )
        self.assertIn("FROM llama3.2:latest", modelfile)
        self.assertIn("PARAMETER temperature 0.1", modelfile)
        self.assertIn("Disconnect the cable from the battery negative terminal.", modelfile)
        self.assertIn("Desconecte o cabo do terminal negativo da bateria.", modelfile)
        self.assertIn("MESSAGE user", modelfile)
        self.assertIn("MESSAGE assistant", modelfile)

        # 2. Test Alpaca dataset export
        out_jsonl = os.path.join(tempfile.gettempdir(), "test_alpaca_dataset.jsonl")
        count = SLMTrainer.export_alpaca_dataset(pairs, out_jsonl)
        self.assertEqual(count, 3)
        self.assertTrue(os.path.exists(out_jsonl))
        
        with open(out_jsonl, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]
        self.assertEqual(len(lines), 3)
        self.assertIn("instruction", lines[0])
        self.assertIn("input", lines[0])
        self.assertIn("output", lines[0])
        self.assertEqual(lines[0]["output"], "Desconecte o cabo do terminal negativo da bateria.")
        os.remove(out_jsonl)

    def test_slm_pretranslate_integration(self):
        from core.batch_tasks import BatchTaskEngine
        from unittest.mock import patch, MagicMock

        segs = [
            Segment(source="Hello world", target="", state=SegState.UNTRANSLATED),
            Segment(source="Existing text", target="Texto existente", state=SegState.TRANSLATED),
        ]

        with patch("core.batch_tasks.OllamaClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.translate.return_value = "Olá mundo"
            mock_client_cls.return_value = mock_client

            cnt = BatchTaskEngine.pretranslate_segments(
                segments=segs,
                reference_tm=None,
                confirm=True,
                use_slm=True,
                slm_model="toyotao:latest"
            )

            self.assertEqual(cnt, 1)
            self.assertEqual(segs[0].target, "Olá mundo")
            self.assertEqual(segs[0].state, SegState.TRANSLATED)
            self.assertEqual(segs[0].origin, SegOrigin.MT)
            self.assertEqual(segs[0].percent, 85)

    def test_slm_studio_dialog_and_ribbon(self):
        from PySide6.QtWidgets import QApplication
        from ui.ribbon import RibbonBar
        from ui.slm_studio_dialog import SLMStudioDialog
        from ui.screens.editor_screen import EditorScreen

        app = QApplication.instance() or QApplication([])

        # Ribbon signals
        ribbon = RibbonBar()
        self.assertTrue(hasattr(ribbon, "slm_studio_requested"))
        self.assertTrue(hasattr(ribbon, "slm_translate_requested"))

        # Editor screen SLM methods
        editor = EditorScreen()
        self.assertTrue(hasattr(editor, "translate_current_with_slm"))
        self.assertTrue(hasattr(editor, "show_slm_studio"))
        self.assertTrue(hasattr(editor, "set_active_slm_model"))
        editor.set_active_slm_model("toyotao:latest")
        self.assertEqual(editor._active_slm_model, "toyotao:latest")

        # SLM Studio Dialog
        dialog = SLMStudioDialog()
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.tabs.count(), 2)
        self.assertIsNotNone(dialog.txt_model_name)
        self.assertIsNotNone(dialog.combo_base_model)
        self.assertIsNotNone(dialog.combo_active_model)

    def test_progress_percentage_and_bounds(self):
        from core.project import ProjectFile, Project
        # 1. Normal file with words and segments
        f1 = ProjectFile(
            path="file1.sdlxliff",
            words=1000,
            segment_count=50,
            translated_words=500,
            approved_words=0,
            translated_count=25,
            approved_count=0
        )
        self.assertEqual(f1.progress, 50.0)

        # 2. File with mixed words but segment fallback
        f2 = ProjectFile(
            path="file2.sdlxliff",
            words=0,
            segment_count=10,
            translated_count=3,
            approved_count=2
        )
        self.assertEqual(f2.progress, 50.0)

        # 3. File with words where words >> segments: MUST NEVER exceed 100%
        f3 = ProjectFile(
            path="file3.sdlxliff",
            words=23302,
            segment_count=2700,
            translated_words=23302,
            approved_words=0,
            translated_count=2700,
            approved_count=0
        )
        self.assertEqual(f3.progress, 100.0)

        # 4. Overall project progress
        proj = Project(name="TestProj", files=[f1, f2, f3])
        prog = proj.overall_progress()
        self.assertGreaterEqual(prog, 0.0)
        self.assertLessEqual(prog, 100.0)

    def test_sdlproj_statistics_integrity(self):
        sdlproj_path = r"C:\Users\Icaro\Documents\Studio 2021\Projects\Samples\SampleProject\Sample Project.sdlproj"
        if os.path.exists(sdlproj_path):
            proj = parse_sdlproj(sdlproj_path)
            self.assertIsNotNone(proj)
            for f in proj.files:
                # Progress must strictly be between 0.0% and 100.0%
                self.assertGreaterEqual(f.progress, 0.0, f"Progress below 0% for {f.path}")
                self.assertLessEqual(f.progress, 100.0, f"Progress above 100% for {f.path}")
                # Translated segments must not exceed total segments
                if f.segment_count > 0:
                    self.assertLessEqual(f.translated_count + f.approved_count, f.segment_count)
                # Translated words must not exceed total words
                if f.words > 0:
                    self.assertLessEqual(f.translated_words + f.approved_words, f.words)
            overall = proj.overall_progress()
            self.assertGreaterEqual(overall, 0.0)
            self.assertLessEqual(overall, 100.0)

    def test_tm_count_translated_integrity(self):
        import tempfile
        db_path = os.path.join(tempfile.gettempdir(), "test_tm_counts.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        tm = TranslationMemory(db_path)
        segs = [
            Segment(source="Hello", target="Olá", state=SegState.TRANSLATED),
            Segment(source="Approved text", target="Texto aprovado", state=SegState.APPROVED),
            Segment(source="Draft text", target="Texto rascunho", state=SegState.DRAFT),
            Segment(source="Untranslated with target copy", target="Untranslated with target copy", state=SegState.UNTRANSLATED),
            Segment(source="Empty target", target="", state=SegState.UNTRANSLATED),
        ]
        tm.add_many(segs, "en", "pt")
        # count() is total: 5
        self.assertEqual(tm.count(), 5)
        # count_translated() must only count TRANSLATED and APPROVED: 2
        self.assertEqual(tm.count_translated(), 2)
        # count_by_state()
        st = tm.count_by_state()
        self.assertEqual(st["translated"], 1)
        self.assertEqual(st["approved"], 1)
        self.assertEqual(st["draft"], 1)
        self.assertEqual(st["untranslated"], 2)
        tm.close()
        if os.path.exists(db_path):
            os.remove(db_path)

    def test_sdlxliff_structural_filtering(self):
        """Verifica que trans-units estruturais sem seg-source não são tratadas como segmentos não traduzidos."""
        import tempfile
        from io_layer.sdlxliff import iter_sdlxliff
        content = """<?xml version="1.0" encoding="utf-8"?>
<xliff xmlns:sdl="http://sdl.com/FileTypes/SdlXliff/1.0" xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2" sdl:version="1.0">
  <file original="test.xml" datatype="x-sdlfilterframework2" source-language="en-US" target-language="pt-BR">
    <body>
      <!-- 1. Trans-unit estrutural com translate="no" e apenas tags de marcação -->
      <trans-unit id="struct-1" translate="no">
        <source><x id="0"/><x id="1"/></source>
      </trans-unit>
      <!-- 2. Trans-unit traduzida real com seg-source -->
      <trans-unit id="trans-1">
        <source>Engine control</source>
        <seg-source>
          <mrk mtype="seg" mid="1">Engine control</mrk>
        </seg-source>
        <target>
          <mrk mtype="seg" mid="1">Controle do motor</mrk>
        </target>
        <sdl:seg-defs>
          <sdl:seg id="1" conf="Translated" origin="tm" percent="100"/>
        </sdl:seg-defs>
      </trans-unit>
      <!-- 3. Outra trans-unit estrutural que não deve inflar o contador para 50% -->
      <trans-unit id="struct-2" translate="no">
        <source><x id="2"/></source>
      </trans-unit>
    </body>
  </file>
</xliff>"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "test_structural.sdlxliff")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            segs = list(iter_sdlxliff(path))
            # Deve ter exatamente 1 segmento traduzível, e 0 segmentos estruturais fantasmas
            self.assertEqual(len(segs), 1)
            self.assertEqual(segs[0].source, "Engine control")
            self.assertEqual(segs[0].target, "Controle do motor")
            self.assertEqual(segs[0].state, SegState.TRANSLATED)

    def test_words_counting_and_model_editing(self):
        """Verifica a contagem precisa de palavras e a edição direta in-cell no modelo da grelha."""
        import tempfile
        from ui.segments_model import SegmentsModel
        from PySide6.QtCore import Qt
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = os.path.join(tmp_dir, "test_words.db")
            tm = TranslationMemory(db_path)
            segs = [
                Segment(source="One two three four five", target="Um dois três quatro cinco", state=SegState.TRANSLATED),
                Segment(source="Ten twenty thirty", target="", state=SegState.UNTRANSLATED),
            ]
            tm.add_many(segs, "en", "pt")
            self.assertEqual(tm.total_words(), 8)
            self.assertEqual(tm.translated_words(), 5)

            model = SegmentsModel(tm)
            self.assertEqual(model.flags(model.index(0, 1)) & Qt.ItemIsEditable, Qt.ItemIsEditable)
            self.assertEqual(model.flags(model.index(0, 0)) & Qt.ItemIsEditable, Qt.NoItemFlags)

            # Teste de edição direta na célula Tradução (coluna 1)
            res = model.setData(model.index(1, 1), "Dez vinte trinta", Qt.EditRole)
            self.assertTrue(res)
            self.assertEqual(tm.count_translated(), 2)
            self.assertEqual(tm.translated_words(), 8)
            tm.close()

    def test_universal_file_importer(self):
        """Verifica a conversão universal de arquivos de texto/office para SDLXLIFF traduzível."""
        import tempfile
        from core.file_importer import (
            is_cat_native_file,
            convert_to_sdlxliff,
            SUPPORTED_FORMATS,
        )

        self.assertTrue(is_cat_native_file("test.sdlxliff"))
        self.assertTrue(is_cat_native_file("test.sdltm"))
        self.assertTrue(is_cat_native_file("test.sdlproj"))
        self.assertFalse(is_cat_native_file("test.docx"))
        self.assertFalse(is_cat_native_file("test.txt"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Arquivo de texto puro
            txt_path = os.path.join(tmp_dir, "documento_teste.txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("Primeiro parágrafo do documento de teste.\n\nSegundo parágrafo com duas frases. Aqui está a segunda frase.")

            sdlxliff_out, seg_count = convert_to_sdlxliff(txt_path, src_lang="pt-BR", tgt_lang="en-US")
            self.assertTrue(os.path.exists(sdlxliff_out))
            self.assertTrue(sdlxliff_out.endswith(".sdlxliff"))
            self.assertGreaterEqual(seg_count, 2)

            segs = list(iter_sdlxliff(sdlxliff_out))
            self.assertGreaterEqual(len(segs), 2)
            self.assertIn("Primeiro parágrafo", segs[0].source)
            self.assertEqual(segs[0].target, "")
            self.assertEqual(segs[0].state, SegState.UNTRANSLATED)

            # 2. Arquivo Markdown
            md_path = os.path.join(tmp_dir, "readme.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("# Título do Guia\n\nEste é um guia rápido para tradutores profissionais.")

            sdlxliff_md, md_count = convert_to_sdlxliff(md_path, src_lang="pt-BR", tgt_lang="es-ES")
            self.assertTrue(os.path.exists(sdlxliff_md))
            self.assertGreaterEqual(md_count, 1)
            segs_md = list(iter_sdlxliff(sdlxliff_md))
            self.assertGreaterEqual(len(segs_md), 1)

    def test_quick_start_dialog_and_welcome_screen(self):
        """Verifica a inicialização da tela Welcome e do diálogo QuickStart sem erros de UI."""
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ui.screens.welcome_screen import WelcomeScreen
        from ui.quick_start_dialog import QuickStartDialog

        welcome = WelcomeScreen()
        self.assertIsNotNone(welcome.drop_zone)

        dialog = QuickStartDialog(
            file_path="C:\\sample\\test_file.docx",
            segment_count=42,
            default_src_lang="en-US",
            default_tgt_lang="pt-BR"
        )
        self.assertEqual(dialog.source_lang, "en-US")
        self.assertEqual(dialog.target_lang, "pt-BR")
        self.assertFalse(dialog.confirmed)

        # Test TM addition with an existing file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".sdltm", delete=False) as tf:
            tm_temp = tf.name
        try:
            dialog._add_tm_path(tm_temp)
            self.assertIn(tm_temp, dialog.selected_tms)
        finally:
            if os.path.exists(tm_temp):
                os.remove(tm_temp)

    def test_pdf_engine_and_tofu_detection(self):
        """Verifica detecção de tofu/caracteres corrompidos e motor limpo de PDF."""
        from core.pdf_engine import is_text_garbled_or_tofu, clean_extracted_text

        # 1. Casos com tofu e lixo de CMap corrompido (como visto na imagem do usuário)
        sample_tofu = "Install SanDisk Software □□□□□□□□□□□□□□□□□□□□"
        sample_garbled = "* □□□□□X□□XYa□c□ ¡□¢m£¥f§¤'a"
        self.assertTrue(is_text_garbled_or_tofu(sample_tofu))
        self.assertTrue(is_text_garbled_or_tofu(sample_garbled))

        # 2. Casos normais e texto limpo
        sample_clean_en = "Install SanDisk Software on your desktop or portable drive."
        sample_clean_zh = "简体中文: 软件安装说明"
        sample_clean_pt = "Instalação do Software no seu computador."
        self.assertFalse(is_text_garbled_or_tofu(sample_clean_en))
        self.assertFalse(is_text_garbled_or_tofu(sample_clean_zh))
        self.assertFalse(is_text_garbled_or_tofu(sample_clean_pt))

        # 3. Higienização de texto
        dirty_text = "Palavra inter-\nnacional com espaço   extra e □ tofu."
        cleaned = clean_extracted_text(dirty_text)
        self.assertNotIn("□", cleaned)
        self.assertIn("internacional", cleaned)
        self.assertNotIn("   ", cleaned)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestTradosFull)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)



