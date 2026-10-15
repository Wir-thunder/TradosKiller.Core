"""
ui.tm_model - modelo de tabela para o Editor de Memoria.

Diferenca face ao SegmentsModel: suporta FILTRO (busca). Mantem uma lista de
ids visiveis (resultado da busca) e so busca os dados das linhas mostradas.
Assim, filtrar 100k segmentos nao carrega tudo - so os ids (inteiros) + paginas.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from core.tm import TranslationMemory
from core.segment import Segment, display_text

PAGE = 300
COLUMNS = ("#", "Fonte", "Tradução", "Estado", "%")


class TmEditorModel(QAbstractTableModel):
    def __init__(self, tm: TranslationMemory, parent=None) -> None:
        super().__init__(parent)
        self.tm = tm
        self._ids: list[int] = []          # ids visiveis (filtro aplicado)
        self._cache: dict[int, Segment] = {}  # id -> segmento (so vistos)
        self.apply_filter("", "both")

    # ------------------------------------------------------------------ filtro
    def apply_filter(self, query: str, field: str = "both") -> None:
        self.beginResetModel()
        self._ids = self.tm.search_ids(query, field)
        self._cache.clear()
        self.endResetModel()

    def visible_ids(self) -> list[int]:
        return self._ids

    # ------------------------------------------------ metados obrigatorios Qt
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._ids) if not parent.isValid() else 0

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS) if not parent.isValid() else 0

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def flags(self, index):
        base = super().flags(index)
        if index.isValid() and index.column() in (1, 2):  # fonte e traducao editaveis
            return base | Qt.ItemIsEditable
        return base

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        row = index.row()
        rid = self._ids[row]
        seg = self._ensure(rid)
        if seg is None:
            return None
        col = index.column()
        if col == 0:
            return rid
        if col == 1:
            return display_text(seg.source)
        if col == 2:
            return display_text(seg.target)
        if col == 3:
            return seg.state.value
        if col == 4:
            return seg.percent
        return None

    def setData(self, index: QModelIndex, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        row = index.row()
        rid = self._ids[row]
        col = index.column()
        if col == 1:
            self.tm.update_source(rid, str(value))
        elif col == 2:
            from core.segment import SegState
            self.tm.update_target(rid, str(value), state=SegState.TRANSLATED)
        else:
            return False
        self._cache.pop(rid, None)
        seg = self._ensure(rid)
        if seg:
            self.dataChanged.emit(self.index(row, 1), self.index(row, 2),
                                  [Qt.DisplayRole, Qt.EditRole])
        return True

    # ---------------------------------------------------- busca paginada por id
    def _ensure(self, rid: int) -> Segment | None:
        if rid in self._cache:
            return self._cache[rid]
        seg = self.tm.get_row(rid)
        if seg is not None:
            self._cache[rid] = seg
        return seg

    def id_at(self, row: int) -> int:
        return self._ids[row] if 0 <= row < len(self._ids) else -1

    def row_of_id(self, rid: int) -> int:
        try:
            return self._ids.index(rid)
        except ValueError:
            return -1

    def refresh(self) -> None:
        self.beginResetModel()
        self._cache.clear()
        self.endResetModel()
