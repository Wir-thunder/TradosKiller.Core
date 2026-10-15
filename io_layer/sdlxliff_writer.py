"""
io_layer.sdlxliff_writer - exporta a TM de volta para SDLXLIFF.

Reproduz a estrutura validada em ficheiros reais do Trados:
  - namespace sdl + XLIFF 1.2
  - trans-unit/@id = GUID (usa tu_id; gera se faltar)
  - segmentacao <seg-source><mrk mtype="seg" mid=N"> + <sdl:seg conf=...>
Escreve em streaming.
"""
from __future__ import annotations

import datetime
import uuid
from xml.sax.saxutils import escape

from core.tm import TranslationMemory
from core.segment import Segment, SegState, SegOrigin, inline_xml_content

XLIFF = "urn:oasis:names:tc:xliff:document:1.2"
SDL = "http://sdl.com/FileTypes/SdlXliff/1.0"

# estado interno -> 'conf' do SDL
_CONF_OUT = {
    SegState.TRANSLATED: "Translated",
    SegState.APPROVED: "ApprovedTranslation",
    SegState.DRAFT: "Draft",
    SegState.REJECTED: "RejectedTranslation",
    SegState.UNTRANSLATED: "Unspecified",
}

_ORIGIN_OUT = {
    SegOrigin.TM: "tm",
    SegOrigin.MT: "mt",
    SegOrigin.INTERACTIVE: "interactive",
    SegOrigin.MANUAL: "manual",
    SegOrigin.AUTO: "auto-propagated",
    SegOrigin.NONE: "interactive",
}


def _group_by_tu(segs):
    """Agrupa segmentos por tu_id, preservando ordem, para reconstruir trans-units."""
    order: list[str] = []
    groups: dict[str, list[Segment]] = {}
    for s in segs:
        key = s.tu_id or s.seg_id or str(s.row_id)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(s)
    for k in order:
        yield k, groups[k]


def write_sdlxliff(tm: Optional[TranslationMemory] = None, out_path: str = "",
                   src_lang: str = "en-US", tgt_lang: str = "pt-BR",
                   original: str = "exported",
                   segments: Optional[Iterable[Segment]] = None) -> int:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    n_tu = 0
    seg_source = segments if segments is not None else (tm.iter_all() if tm else [])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(f'<xliff xmlns:sdl="{SDL}" xmlns="{XLIFF}" version="1.2" sdl:version="1.0">\n')
        f.write(f'  <file original="{escape(original)}" datatype="x-sdlfilterframework2" '
                f'source-language="{escape(src_lang)}" target-language="{escape(tgt_lang)}">\n')
        f.write('    <sdl:filetype-info></sdl:filetype-info>\n')
        f.write('    <body>\n')

        for tu_id, segs in _group_by_tu(seg_source):
            guid = tu_id if _looks_guid(tu_id) else str(uuid.uuid4())
            f.write(f'      <trans-unit id="{guid}" translate="no">\n')
            f.write('        <source>\n')
            for s in segs:
                source_xml = inline_xml_content(s.source, s.source_tags)
                f.write(f'          <g id="{_mid(s)}">{source_xml}</g>\n')
            f.write('        </source>\n')
            # seg-source com mrk por segmento
            f.write('        <seg-source>\n')
            for s in segs:
                source_xml = inline_xml_content(s.source, s.source_tags)
                f.write(f'          <mrk mtype="seg" mid="{_mid(s)}">'
                        f'{source_xml}</mrk>\n')
            f.write('        </seg-source>\n')
            # target
            f.write('        <target>\n')
            for s in segs:
                target_xml = inline_xml_content(s.target, s.target_tags)
                f.write(f'          <mrk mtype="seg" mid="{_mid(s)}">'
                        f'{target_xml}</mrk>\n')
            f.write('        </target>\n')
            # seg-defs com metadados
            f.write('        <sdl:seg-defs>\n')
            for s in segs:
                conf = _CONF_OUT.get(s.state, "Unspecified")
                origin = _ORIGIN_OUT.get(s.origin, "interactive")
                f.write(f'          <sdl:seg id="{_mid(s)}" conf="{conf}" '
                        f'origin="{origin}" percent="{s.percent}">\n')
                f.write('          </sdl:seg>\n')
            f.write('        </sdl:seg-defs>\n')
            f.write('      </trans-unit>\n')
            n_tu += 1

        f.write('    </body>\n  </file>\n</xliff>\n')
    return n_tu


def _mid(seg: Segment) -> str:
    return seg.seg_id or str(seg.row_id)


def _looks_guid(s: str) -> bool:
    return len(s) == 36 and s.count("-") == 4
