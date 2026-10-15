"""
io_layer - I/O layer for parsing and writing translation file formats.
Supports RWS Trados ecosystem (.sdlxliff, .sdltm, .sdlproj, .sdlppx, .sdlrpx) and open standards (TMX 1.4b).
"""
from .sdlproj import parse_sdlproj, is_sdlproj_file, detect_sdlproj_info  # noqa: F401
from .sdlxliff import iter_sdlxliff, detect_sdlxliff_langs  # noqa: F401
from .sdlxliff_writer import write_sdlxliff  # noqa: F401
from .sdltm import iter_sdltm, detect_sdltm_langs, write_sdltm, parse_sdltm_segment_xml  # noqa: F401
from .sdlpackage import is_sdlpackage, extract_package, create_return_package  # noqa: F401
from .tmx import iter_tmx, detect_tmx_langs  # noqa: F401
from .tmx_writer import write_tmx  # noqa: F401
