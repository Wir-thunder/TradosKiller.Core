"""
io_layer.tmx_writer - exporta a TM (SQLite) de volta para TMX 1.4b.

Escreve em streaming (nunca acumula a lista inteira em RAM).
Recompoe as tags inline a partir dos placeholders {N} + codigos originais.
"""
from __future__ import annotations

import datetime
from xml.sax.saxutils import escape

from core.tm import TranslationMemory
from core.segment import inline_xml_content


def write_tmx(tm: Optional[TranslationMemory] = None, out_path: str = "",
              src_lang: str = "en", tgt_lang: str = "pt",
              segments: Optional[Iterable[Segment]] = None) -> int:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n = 0
    seg_source = segments if segments is not None else (tm.iter_all() if tm else [])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE tmx PUBLIC "-//LISA OSCAR:1998//DTD for '
                'Translation Memory eXchange//EN" "tmx14.dtd">\n')
        f.write('<tmx version="1.4">\n')
        f.write(f'  <header creationtool="CAT Tool" creationtoolversion="0.2" '
                f'srclang="{escape(src_lang)}" adminlang="{escape(src_lang)}" '
                f'datatype="unknown" segtype="sentence" '
                f'creationdate="{now}" o-tmf="CAT Tool">\n')
        f.write('  </header>\n  <body>\n')
        for seg in seg_source:
            src = inline_xml_content(seg.source, seg.source_tags)
            tgt = inline_xml_content(seg.target, seg.target_tags) if seg.target else ""
            f.write('    <tu>\n')
            f.write(f'      <tuv xml:lang="{escape(src_lang)}"><seg>{src}</seg></tuv>\n')
            f.write(f'      <tuv xml:lang="{escape(tgt_lang)}"><seg>{tgt}</seg></tuv>\n')
            f.write('    </tu>\n')
            n += 1
        f.write('  </body>\n</tmx>\n')
    return n
