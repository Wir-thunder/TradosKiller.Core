"""
ui.segments_model - modelo de tabela VIRTUALIZADO e FILTRÁVEL (QAbstractTableModel).

Anti-crash:
- Quando sem filtro ativo, busca por páginas (fetchMore / lazy loading) mantendo uso de RAM constante.
- Quando filtrado (por busca de texto ou estado no Review Bar), opera sobre a lista de IDs retornada pelo SQLite.
- Suporta destaques de estado visual padrão Trados (Draft, Translated, Approved, Rejected).
"""
from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from core.tm import TranslationMemory
from core.segment import Segment, SegState, display_text

PAGE = 200          # segmentos por pagina buscados ao SQLite
COLUMNS = ("Fonte", "Tradução", "Estado", "Origem", "%")

# Cores de estado padrão Trados Studio
STATE_COLORS = {
    SegState.TRANSLATED.value: QColor(46, 204, 113),    # Verde esmeralda
    SegState.APPROVED.value: QColor(26, 188, 156),      # Verde azulado / Teal
    SegState.DRAFT.value: QColor(243, 156, 18),         # Âmbar / Laranja
    SegState.REJECTED.value: QColor(231, 76, 60),       # Vermelho
    SegState.UNTRANSLATED.value: QColor(149, 165, 166), # Cinza neutro
}

STATE_LABELS = {
    SegState.TRANSLATED.value: "✓ Translated",
    SegState.APPROVED.value: "🔒 Approved",
    SegState.DRAFT.value: "✎ Draft",
    SegState.REJECTED.value: "✗ Rejected",
    SegState.UNTRANSLATED.value: "· Untranslated",
}


class SegmentsModel(QAbstractTableModel):
    def __init__(self, tm: TranslationMemory, parent=None) -> None:
        super().__init__(parent)
        self.tm = tm
        self._total = tm.count()
        self._cache: dict[int, Segment] = {}   # cache para linhas virtualizadas
        self._id_cache: dict[int, Segment] = {} # cache id -> Segment
        self._loaded_rows = 0
        self._ids: list[int] = []              # IDs ativos quando filtrado
        self._is_filtered = False

    # ------------------------------------------------------------------ filtro
    def apply_filter(self, query: str = "", field: str = "both",
                     state: Optional[str] = None, case_sensitive: bool = False) -> int:
        """
        Aplica filtro de busca (Ctrl+F), Display Filter e/ou estado da Review Bar.
        Se query vazia e state for None/"all", desativa o filtro e volta ao modo virtualizado.
        Retorna o número de resultados.
        """
        self.beginResetModel()
        self._cache.clear()
        self._id_cache.clear()

        query_clean = query.strip()
        state_clean = state.lower() if state else "all"

        if not query_clean and state_clean in ("all", "all segments", ""):
            self._is_filtered = False
            self._ids = []
            self._total = self.tm.count()
            self._loaded_rows = 0
            self.endResetModel()
            return self._total
        else:
            self._is_filtered = True
            self._ids = self.tm.filter_ids(query=query_clean, field=field,
                                           state=state_clean, case_sensitive=case_sensitive)
            self._total = len(self._ids)
            self.endResetModel()
            return len(self._ids)

    def refresh(self) -> None:
        """Recarrega os dados da TM preservando o filtro ativo se houver."""
        self.beginResetModel()
        self._cache.clear()
        self._id_cache.clear()
        self._total = self.tm.count()
        self._loaded_rows = 0
        if self._is_filtered:
            self._ids = [i for i in self._ids if self.tm.get_row(i) is not None]
            self._total = len(self._ids)
        self.endResetModel()

    def clear_filter(self) -> None:
        """Limpa o filtro e restaura a visão virtualizada completa."""
        self.apply_filter("", "both", "all")

    def apply_advanced_filter(self, criteria) -> int:
        """Aplica critérios do Advanced Display Filter 2.0."""
        self.beginResetModel()
        self._cache.clear()
        self._id_cache.clear()

        if criteria.is_empty() and not getattr(criteria, "reverse", False):
            self._is_filtered = False
            self._ids = []
            self._total = self.tm.count()
            self._loaded_rows = 0
            self.endResetModel()
            return self._total
        else:
            self._is_filtered = True
            self._ids = self.tm.apply_advanced_filter(criteria)
            self._total = len(self._ids)
            self.endResetModel()
            return len(self._ids)

    def get_current_segments(self) -> list[Segment]:
        """Retorna a lista de segmentos atualmente visíveis (filtrados ou todos)."""
        if self._is_filtered:
            segs = []
            for row_id in self._ids:
                s = self.tm.get_row(row_id)
                if s:
                    segs.append(s)
            return segs
        return list(self.tm.iter_all())

    @property
    def is_filtered(self) -> bool:
        return self._is_filtered

    # ------------------------------------------------ metados obrigatorios Qt
    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._ids) if self._is_filtered else self._total

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS) if not parent.isValid() else 0

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return COLUMNS[section]
            if orientation == Qt.Vertical:
                return str(section + 1)
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        seg = self._ensure(row)
        if seg is None:
            return None

        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0:
                return display_text(seg.source)
            if col == 1:
                return display_text(seg.target)
            if col == 2:
                # Texto limpo com ícone simbólico de estado estilo Trados
                return STATE_LABELS.get(seg.state.value, seg.state.value)
            if col == 3:
                return seg.origin.value
            if col == 4:
                return f"{seg.percent}%" if seg.percent > 0 else ""
            return None

        # Cores para feedback visual imediato
        if role == Qt.ForegroundRole:
            if col == 2:
                return STATE_COLORS.get(seg.state.value, QColor(200, 200, 200))
            if col == 4 and seg.percent >= 100:
                return QColor(46, 204, 113)
            if col == 4 and seg.percent >= 75:
                return QColor(52, 152, 219)

        if role == Qt.TextAlignmentRole:
            if col in (2, 3, 4):
                return int(Qt.AlignCenter)

        if role == Qt.ToolTipRole:
            return f"Segmento #{row + 1} | Estado: {seg.state.value} | Origem: {seg.origin.value}"

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        base_flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == 1:  # Coluna Tradução editável diretamente na tabela
            return base_flags | Qt.ItemIsEditable
        return base_flags

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole or index.column() != 1:
            return False
        row = index.row()
        seg = self._ensure(row)
        if seg is None:
            return False
        new_text = str(value) if value is not None else ""
        if new_text != display_text(seg.target):
            new_state = SegState.TRANSLATED if new_text.strip() else SegState.UNTRANSLATED
            self.tm.update_target(seg.row_id, new_text, new_state)
            seg.target = new_text
            seg.state = new_state
            if self._is_filtered:
                self._id_cache[seg.row_id] = seg
            else:
                self._cache[row] = seg
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1), [Qt.DisplayRole, Qt.ForegroundRole])
            return True
        return False

    # --------------------------------------------- carregamento paginado (lazy)
    def canFetchMore(self, parent=QModelIndex()) -> bool:
        if self._is_filtered:
            return False
        return self._loaded_rows < self._total

    def fetchMore(self, parent=QModelIndex()) -> None:
        if self._is_filtered:
            return
        remainder = self._total - self._loaded_rows
        to_fetch = min(PAGE, remainder)
        if to_fetch <= 0:
            return
        segs = self.tm.page(self._loaded_rows, to_fetch)
        for i, s in enumerate(segs):
            self._cache[self._loaded_rows + i] = s
        self._loaded_rows += to_fetch

    def _ensure(self, row: int) -> Segment | None:
        if self._is_filtered:
            if row < 0 or row >= len(self._ids):
                return None
            seg_id = self._ids[row]
            if seg_id in self._id_cache:
                return self._id_cache[seg_id]
            seg = self.tm.get_row(seg_id)
            if seg:
                self._id_cache[seg_id] = seg
            return seg

        if row in self._cache:
            return self._cache[row]

        # Busca direta de uma janela paginada em torno da linha requisitada (instantâneo mesmo com 1 milhão de segmentos)
        offset = max(0, row - 50)
        segs = self.tm.page(offset, PAGE)
        if len(self._cache) > 5000:
            self._cache.clear()
        for i, s in enumerate(segs):
            self._cache[offset + i] = s
        return self._cache.get(row)

    def segment_at(self, row: int) -> Segment | None:
        return self._ensure(row)

    def row_of_id(self, seg_id: int) -> int:
        """Retorna o índice de linha para um ID específico de segmento."""
        if self._is_filtered:
            try:
                return self._ids.index(seg_id)
            except ValueError:
                return -1
        # No modo não-filtrado, verifica o cache primeiro
        for r, s in self._cache.items():
            if s.row_id == seg_id:
                return r
        # Se não estiver no cache em memória, consulta a posição por ordem no SQLite
        seg = self.tm.get_row(seg_id)
        if seg:
            try:
                cnt = self.tm.conn.execute(
                    "SELECT COUNT(*) FROM segments WHERE segment_order < ? OR (segment_order = ? AND id < ?)",
                    (seg.order, seg.order, seg_id)
                ).fetchone()[0]
                return cnt
            except Exception:
                pass
        return -1

    def refresh(self) -> None:
        self.beginResetModel()
        self._total = self.tm.count()
        self._cache.clear()
        self._id_cache.clear()
        self._loaded_rows = 0
        if self._is_filtered:
            self._ids = [sid for sid in self._ids if self.tm.get_row(sid) is not None]
            self._total = len(self._ids)
        self.endResetModel()
