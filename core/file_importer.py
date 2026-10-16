"""
core.file_importer - Importador universal de ficheiros e gerador de SDLXLIFF para o TradosKiller.

Permite arrastar e soltar QUALQUER formato de arquivo passível de tradução:
- Bilingues / CAT: .sdlxliff, .xliff, .xlf, .tmx, .sdltm, .sdlproj, .sdlppx, .catproj
- Documentos Office: .docx, .xlsx, .pptx
- Adobe PDF: .pdf (extração direta com pypdf + OCR de páginas digitalizadas)
- Imagens / OCR: .png, .jpg, .jpeg, .tiff, .bmp (reconhecimento nativo Windows via winocr / pytesseract)
- Texto / Web: .txt, .md, .html, .htm, .xml, .json, .csv, .po, .rtf

Extrai o texto, executa segmentação inteligente por sentenças e converte instantaneamente
para SDLXLIFF padrão RWS Trados Studio pronto para tradução.
"""
from __future__ import annotations

import csv
import json
import os
import re
import uuid
from pathlib import Path
from typing import List, Tuple, Optional
from xml.sax.saxutils import escape


BILINGUAL_EXTS = {".sdlxliff", ".xliff", ".xlf", ".tmx", ".sdltm"}
PROJECT_EXTS = {".sdlproj", ".sdlppx", ".sdlrpx", ".catproj"}
OFFICE_EXTS = {".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"}
PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
TEXT_EXTS = {".txt", ".md", ".html", ".htm", ".xhtml", ".xml", ".json", ".csv", ".tsv", ".po", ".pot", ".rtf"}

ALL_SUPPORTED_EXTS = (
    BILINGUAL_EXTS | PROJECT_EXTS | OFFICE_EXTS | PDF_EXTS | IMAGE_EXTS | TEXT_EXTS
)
SUPPORTED_FORMATS = ALL_SUPPORTED_EXTS


# Abreviaturas comuns que não devem quebrar segmento
_ABBR_REGEX = re.compile(r"\b(e\.g\.|i\.e\.|etc\.|mr\.|mrs\.|ms\.|dr\.|prof\.|vs\.|fig\.|tab\.|no\.|vol\.|approx\.|dept\.|co\.|ltd\.|inc\.|corp\.)\s*$", re.IGNORECASE)
_NUM_PUNCT_REGEX = re.compile(r"\b\d+\.\d+\b")


def is_supported_file(path: str) -> bool:
    """Verifica se o arquivo é suportado pelo TradosKiller para tradução."""
    ext = os.path.splitext(path)[1].lower()
    return ext in ALL_SUPPORTED_EXTS


def is_cat_native_file(path: str) -> bool:
    """Verifica se o arquivo já é um formato nativo de tradução (SDLXLIFF, XLIFF, SDLPROJ, TMX, SDPTM, etc)."""
    ext = os.path.splitext(path)[1].lower()
    return ext in (BILINGUAL_EXTS | PROJECT_EXTS)


def get_file_type_badge(path: str) -> Tuple[str, str]:
    """Retorna (categoria, ícone) do arquivo."""
    ext = os.path.splitext(path)[1].lower()
    if ext in BILINGUAL_EXTS:
        return "Bilingue Trados", "🗂"
    if ext in PROJECT_EXTS:
        return "Projeto / Pacote Trados", "📦"
    if ext in {".docx", ".doc"}:
        return "Documento Word", "📝"
    if ext in {".xlsx", ".xls"}:
        return "Planilha Excel", "📊"
    if ext in {".pptx", ".ppt"}:
        return "Apresentação PowerPoint", "📽"
    if ext in PDF_EXTS:
        return "Documento PDF", "📑"
    if ext in IMAGE_EXTS:
        return "Imagem (OCR)", "👁"
    if ext in {".html", ".htm", ".xhtml", ".xml"}:
        return "Web / Markup", "🌐"
    if ext in {".json", ".csv", ".tsv", ".po", ".pot"}:
        return "Dados / Localização", "⚙"
    return "Documento de Texto", "📄"


def split_sentences(text: str) -> List[str]:
    """
    Segmentação inteligente de sentenças em português/inglês,
    evitando quebras em números, abreviaturas ou pontuações técnicas.
    """
    if not text:
        return []
    
    clean = text.strip()
    if not clean:
        return []

    # Divide em parágrafos primeiro
    paragraphs = re.split(r"\r?\n+", clean)
    sentences: List[str] = []

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        
        # Se for um item de lista, título curto ou cabeçalho, mantém como segmento único
        if len(p) < 40 or p.startswith(("-", "•", "*", "1.", "2.", "3.", "4.", "5.")):
            sentences.append(p)
            continue

        # Regex para quebra de sentenças por pontuação seguida de espaço e maiúscula
        # mantendo a integridade de números decimais (ex: 3.14) e abreviações
        parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ú"\'(])', p)
        cur = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if cur:
                # Verifica se a parte anterior terminou com abreviatura
                if _ABBR_REGEX.search(cur):
                    cur = f"{cur} {part}"
                    continue
                sentences.append(cur)
            cur = part
        if cur:
            sentences.append(cur)

    return [s for s in sentences if s.strip()]


# =========================================================================
# EXTRATORES POR FORMATO
# =========================================================================

def _extract_docx(path: str) -> List[str]:
    """Extrai parágrafos e células de tabelas de documentos Word (.docx)."""
    import docx
    doc = docx.Document(path)
    segments = []
    
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            segments.extend(split_sentences(txt))
            
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                txt = cell.text.strip()
                if txt and txt not in segments:
                    segments.extend(split_sentences(txt))
                    
    return segments


def _extract_xlsx(path: str) -> List[str]:
    """Extrai textos e células de planilhas Excel (.xlsx)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    segments = []
    seen = set()
    
    for sheetname in wb.sheetnames:
        sheet = wb[sheetname]
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                if cell is not None and isinstance(cell, str):
                    val = cell.strip()
                    # Ignora números puros ou fórmulas
                    if val and not val.startswith("=") and len(val) > 1:
                        if val not in seen:
                            seen.add(val)
                            segments.extend(split_sentences(val))
    wb.close()
    return segments


def _extract_pptx(path: str) -> List[str]:
    """Extrai caixas de texto e tabelas de apresentações PowerPoint (.pptx)."""
    import pptx
    prs = pptx.Presentation(path)
    segments = []
    
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    txt = paragraph.text.strip()
                    if txt:
                        segments.extend(split_sentences(txt))
            if shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        txt = cell.text.strip()
                        if txt:
                            segments.extend(split_sentences(txt))
    return segments


def _extract_pdf(path: str) -> List[str]:
    """Extrai texto limpo de PDFs nativos e digitalizados via core.pdf_engine (Zero Tofu / OCR Fallback)."""
    try:
        from core.pdf_engine import extract_pdf_clean
        clean_segs = extract_pdf_clean(path)
        if clean_segs:
            return clean_segs
    except Exception:
        pass

    # Fallback seguro caso pdf_engine encontre problemas
    import pypdf
    segments = []
    try:
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            txt = page.extract_text()
            if txt and txt.strip():
                segments.extend(split_sentences(txt.strip()))
    except Exception:
        pass
    return segments


def _extract_image_ocr(path: str) -> List[str]:
    """Extrai texto de imagens via OCR nativo do Windows (winocr)."""
    segments = []
    try:
        from PIL import Image
        import winocr
        import asyncio

        img = Image.open(path)
        # Redimensiona se for muito pequena para melhorar o OCR
        if img.width < 1000 or img.height < 1000:
            scale = max(2, int(1500 / max(img.width, img.height)))
            img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)

        # Tenta com pt-BR (instalado no Windows) ou fallback
        res = None
        try:
            res = asyncio.run(winocr.recognize_pil(img, "pt-BR"))
        except Exception:
            try:
                # Tenta sem especificar idioma se suportado
                from winrt.windows.media.ocr import OcrEngine
                eng = OcrEngine.try_create_from_user_profile_languages()
                if eng:
                    res = asyncio.run(winocr.recognize_pil(img, eng.recognizer_language.language_tag))
            except Exception:
                pass

        if res and res.text:
            segments.extend(split_sentences(res.text))
        img.close()
    except Exception as e:
        segments.append(f"[OCR Aviso: Não foi possível ler a imagem: {e}]")
    return segments


def _extract_text_file(path: str) -> List[str]:
    """Extrai sentenças de arquivos de texto (.txt, .md, .csv, .json, .html, .xml, .po)."""
    ext = os.path.splitext(path)[1].lower()
    
    # JSON
    if ext == ".json":
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            segments = []
            def _walk(obj):
                if isinstance(obj, str) and obj.strip():
                    segments.extend(split_sentences(obj.strip()))
                elif isinstance(obj, dict):
                    for v in obj.values():
                        _walk(v)
                elif isinstance(obj, list):
                    for item in obj:
                        _walk(item)
            _walk(data)
            return segments
        except Exception:
            pass

    # CSV / TSV
    if ext in (".csv", ".tsv"):
        delimiter = "\t" if ext == ".tsv" else ","
        try:
            segments = []
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)
                for row in reader:
                    for cell in row:
                        val = cell.strip()
                        if val and len(val) > 1 and not val.replace(".", "").isdigit():
                            segments.extend(split_sentences(val))
            return segments
        except Exception:
            pass

    # HTML / XML
    if ext in (".html", ".htm", ".xhtml", ".xml"):
        try:
            from lxml import etree
            parser = etree.HTMLParser() if "htm" in ext else etree.XMLParser(recover=True)
            tree = etree.parse(path, parser)
            segments = []
            for el in tree.iter():
                # Ignora tags de script/style
                if el.tag in ("script", "style", "head"):
                    continue
                if el.text and el.text.strip():
                    segments.extend(split_sentences(el.text.strip()))
                if el.tail and el.tail.strip():
                    segments.extend(split_sentences(el.tail.strip()))
            return segments
        except Exception:
            pass

    # Texto simples / Markdown / PO
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return split_sentences(content)


def extract_segments(path: str) -> List[str]:
    """
    Roteador universal que extrai a lista de segmentos traduzíveis
    de qualquer formato de ficheiro suportado.
    """
    if not os.path.exists(path):
        return []
        
    ext = os.path.splitext(path)[1].lower()
    
    if ext in {".docx", ".doc"}:
        return _extract_docx(path)
    elif ext in {".xlsx", ".xls"}:
        return _extract_xlsx(path)
    elif ext in {".pptx", ".ppt"}:
        return _extract_pptx(path)
    elif ext in PDF_EXTS:
        return _extract_pdf(path)
    elif ext in IMAGE_EXTS:
        return _extract_image_ocr(path)
    else:
        return _extract_text_file(path)


# =========================================================================
# CONVERSOR PARA SDLXLIFF (RWS TRADOS STANDARD)
# =========================================================================

def convert_to_sdlxliff(
    source_path: str,
    src_lang: str = "en-US",
    tgt_lang: str = "pt-BR",
    output_dir: Optional[str] = None
) -> Tuple[str, int]:
    """
    Converte qualquer documento, planilha, apresentação, PDF ou imagem
    num arquivo .sdlxliff traduzível no padrão oficial do SDL Trados Studio.
    
    Retorna: (caminho_do_sdlxliff, total_de_segmentos)
    """
    segments_raw = extract_segments(source_path)
    
    # Se não houver texto extraído
    if not segments_raw:
        segments_raw = ["(Documento sem texto detectável ou protegido)"]

    base_name = os.path.basename(source_path)
    out_dir = output_dir or os.path.dirname(source_path)
    if not out_dir or not os.path.exists(out_dir):
        out_dir = os.path.join(os.environ.get("USERPROFILE", "."), "Documents", "TradosKiller_Projects")
        os.makedirs(out_dir, exist_ok=True)

    out_sdlxliff = os.path.join(out_dir, f"{base_name}.sdlxliff")

    # Gera a estrutura oficial SDLXLIFF 1.2
    XLIFF_NS = "urn:oasis:names:tc:xliff:document:1.2"
    SDL_NS = "http://sdl.com/FileTypes/SdlXliff/1.0"

    with open(out_sdlxliff, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(f'<xliff xmlns:sdl="{SDL_NS}" xmlns="{XLIFF_NS}" version="1.2" sdl:version="1.0">\n')
        f.write(f'  <file original="{escape(base_name)}" datatype="x-sdlfilterframework2" '
                f'source-language="{escape(src_lang)}" target-language="{escape(tgt_lang)}">\n')
        f.write('    <sdl:filetype-info></sdl:filetype-info>\n')
        f.write('    <body>\n')

        mid = 1
        for seg_text in segments_raw:
            clean = seg_text.strip()
            if not clean:
                continue
            
            guid = str(uuid.uuid4())
            esc_text = escape(clean)
            
            f.write(f'      <trans-unit id="{guid}">\n')
            f.write(f'        <source>{esc_text}</source>\n')
            f.write('        <seg-source>\n')
            f.write(f'          <mrk mtype="seg" mid="{mid}">{esc_text}</mrk>\n')
            f.write('        </seg-source>\n')
            f.write('        <target>\n')
            f.write(f'          <mrk mtype="seg" mid="{mid}"></mrk>\n')
            f.write('        </target>\n')
            f.write('        <sdl:seg-defs>\n')
            f.write(f'          <sdl:seg id="{mid}" conf="Unspecified" origin="none" percent="0">\n')
            f.write('          </sdl:seg>\n')
            f.write('        </sdl:seg-defs>\n')
            f.write('      </trans-unit>\n')
            mid += 1

        f.write('    </body>\n')
        f.write('  </file>\n')
        f.write('</xliff>\n')

    return out_sdlxliff, (mid - 1)
