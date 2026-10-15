"""
core.spellcheck - revisor ortografico NATIVO do Windows (ISpellChecker).

Usa a Spell Checking API do proprio Windows (COM: SpellCheckerFactory) -
os dicionarios instalados no sistema. NAO usa Hunspell nem dicionarios
empacotados. Requer Windows 8+ e a lib 'comtypes'.

IIDs/vtable extraidos do header oficial da Microsoft (spellcheck.h / .i.c).
Se a API nao estiver disponivel, available=False e a app segue sem realce.
"""
from __future__ import annotations

import ctypes
from typing import List, Optional, Tuple

try:
    import comtypes
    import comtypes.client
    from comtypes import GUID, COMMETHOD, HRESULT, POINTER, IUnknown
    _HAS_COMTYPES = True
    
    CLSID_SpellCheckerFactory = GUID("{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}")
    IID_ISpellCheckerFactory = GUID("{8E018A9D-2415-4677-BF08-794EA61F94BB}")
    IID_ISpellChecker = GUID("{B6FD0B71-E2BC-4653-8D05-F197E412770B}")
    IID_ISpellingError = GUID("{B7C82D61-FBE8-4B47-9B27-6C0D2E0DE0A3}")
    IID_IEnumSpellingError = GUID("{803E3BD4-2828-4410-8290-418D1D73C762}")
    IID_IEnumString = GUID("{00000101-0000-0000-C000-000000000046}")
    
    class ISpellingError(IUnknown):
        _iid_ = IID_ISpellingError
        _methods_ = (
            COMMETHOD([], HRESULT, "get_StartIndex",
                      (["out", "retval"], POINTER(ctypes.c_ulong), "value")),
            COMMETHOD([], HRESULT, "get_Length",
                      (["out", "retval"], POINTER(ctypes.c_ulong), "value")),
            COMMETHOD([], HRESULT, "get_CorrectiveAction",
                      (["out", "retval"], POINTER(ctypes.c_int), "value")),
            COMMETHOD([], HRESULT, "get_Replacement",
                      (["out", "retval"], POINTER(ctypes.c_wchar_p), "value")),
        )

    class IEnumSpellingError(IUnknown):
        _iid_ = IID_IEnumSpellingError
        _methods_ = (
            COMMETHOD([], HRESULT, "Next",
                      (["in"], ctypes.c_ulong, "celt"),
                      (["out"], POINTER(POINTER(ISpellingError)), "rgelt"),
                      (["out"], POINTER(ctypes.c_ulong), "pceltFetched")),
            COMMETHOD([], HRESULT, "Skip", (["in"], ctypes.c_ulong, "celt")),
            COMMETHOD([], HRESULT, "Reset"),
            COMMETHOD([], HRESULT, "Clone",
                      (["out"], POINTER(POINTER(IUnknown)), "ppenum")),
        )

    class IEnumString(IUnknown):
        _iid_ = IID_IEnumString
        _methods_ = (
            COMMETHOD([], HRESULT, "Next",
                      (["in"], ctypes.c_ulong, "celt"),
                      (["out"], POINTER(ctypes.c_wchar_p), "rgelt"),
                      (["out"], POINTER(ctypes.c_ulong), "pceltFetched")),
            COMMETHOD([], HRESULT, "Skip", (["in"], ctypes.c_ulong, "celt")),
            COMMETHOD([], HRESULT, "Reset"),
            COMMETHOD([], HRESULT, "Clone",
                      (["out"], POINTER(POINTER(IUnknown)), "ppenum")),
        )

    class ISpellChecker(IUnknown):
        _iid_ = IID_ISpellChecker
        _methods_ = (
            COMMETHOD([], HRESULT, "get_LanguageTag",
                      (["out"], POINTER(ctypes.c_wchar_p), "value")),
            COMMETHOD([], HRESULT, "Check",
                      (["in"], ctypes.c_wchar_p, "text"),
                      (["out"], POINTER(POINTER(IEnumSpellingError)), "value")),
            COMMETHOD([], HRESULT, "Suggest",
                      (["in"], ctypes.c_wchar_p, "word"),
                      (["out"], POINTER(POINTER(IEnumString)), "value")),
            COMMETHOD([], HRESULT, "Add", (["in"], ctypes.c_wchar_p, "word")),
            COMMETHOD([], HRESULT, "Ignore", (["in"], ctypes.c_wchar_p, "word")),
            COMMETHOD([], HRESULT, "AutoCorrect",
                      (["in"], ctypes.c_wchar_p, "from_"),
                      (["in"], ctypes.c_wchar_p, "to")),
        )

    class ISpellCheckerFactory(IUnknown):
        _iid_ = IID_ISpellCheckerFactory
        _methods_ = (
            COMMETHOD([], HRESULT, "get_SupportedLanguages",
                      (["out"], POINTER(POINTER(IEnumString)), "value")),
            COMMETHOD([], HRESULT, "IsSupported",
                      (["in"], ctypes.c_wchar_p, "languageTag"),
                      (["out"], POINTER(ctypes.c_int), "value")),
            COMMETHOD([], HRESULT, "CreateSpellChecker",
                      (["in"], ctypes.c_wchar_p, "languageTag"),
                      (["out"], POINTER(POINTER(ISpellChecker)), "value")),
        )
except Exception:  # pragma: no cover
    _HAS_COMTYPES = False
    IUnknown = object  # type: ignore


def _drain_spelling_errors(enum_err, text: str) -> List[Tuple[int, int, str]]:
    """Itera IEnumSpellingError 1-a-1 (comtypes devolve (item, fetched))."""
    out: List[Tuple[int, int, str]] = []
    while True:
        ret = enum_err.Next(1)
        # comtypes com ['out'] simples devolve tuplo (rgelt, pceltFetched)
        rgelt, fetched = _unpack_next(ret)
        if not rgelt or fetched == 0:
            break
        err = rgelt[0] if isinstance(rgelt, (list, tuple)) else rgelt
        if not err:
            break
        start = err.get_StartIndex()
        length = err.get_Length()
        out.append((start, length, text[start:start + length]))
    return out


def _drain_enum_string(enum_str, limit: int = 8) -> List[str]:
    """Itera IEnumString 1-a-1."""
    out: List[str] = []
    while len(out) < limit:
        ret = enum_str.Next(1)
        rgelt, fetched = _unpack_next(ret)
        if not rgelt or fetched == 0:
            break
        val = rgelt[0] if isinstance(rgelt, (list, tuple)) else rgelt
        if val:
            out.append(val)
        else:
            break
    return out


def _unpack_next(ret):
    """Normaliza o retorno do Next conforme o estilo do comtypes."""
    if isinstance(ret, tuple):
        if len(ret) == 2:
            return ret
        if len(ret) == 1:
            return ret[0], 1
    # retorno directo (retval): nao ha fetched; assume 1 item
    return ret, 1


class WindowsSpellChecker:
    """
    Wrapper do revisor nativo do Windows.
        sc = WindowsSpellChecker("pt-PT")
        if sc.available:
            sc.check("texto com errro")   -> [(start, length, palavra), ...]
            sc.suggest("errro")           -> ["erro", ...]
    """

    def __init__(self, language_tag: str = "pt-PT") -> None:
        self.language_tag = language_tag
        self.available = False
        self._factory = None
        self._checker = None
        if not _HAS_COMTYPES:
            return
        try:
            comtypes.CoInitialize()
            factory = comtypes.client.CreateObject(CLSID_SpellCheckerFactory)
            self._factory = factory.QueryInterface(ISpellCheckerFactory)
            checker = self._create_checker(self._factory, language_tag)
            if checker is not None:
                self._checker = checker
                self.available = True
        except Exception:
            self.available = False

    def _create_checker(self, factory, tag):
        try:
            supported = factory.IsSupported(tag)  # retorna int directo
            use = tag if supported else "en-US"
            self.language_tag = use
            return factory.CreateSpellChecker(use)  # retorna POINTER(ISpellChecker)
        except Exception:
            return None

    def check(self, text: str) -> List[Tuple[int, int, str]]:
        """Devolve [(start, length, palavra), ...] dos erros ortograficos."""
        if not self.available or not text:
            return []
        result: List[Tuple[int, int, str]] = []
        try:
            enum_err = self._checker.Check(text)
            if not enum_err:
                return []
            result = _drain_spelling_errors(enum_err, text)
        except Exception:
            return result
        return result

    def suggest(self, word: str, limit: int = 8) -> List[str]:
        """Sugestoes para uma palavra errada."""
        if not self.available or not word:
            return []
        try:
            enum_str = self._checker.Suggest(word)
            if not enum_str:
                return []
            return _drain_enum_string(enum_str, limit)
        except Exception:
            return []

    def ignore(self, word: str) -> None:
        if self.available and word:
            try:
                self._checker.Ignore(word)
            except Exception:
                pass

    def add(self, word: str) -> None:
        if self.available and word:
            try:
                self._checker.Add(word)
            except Exception:
                pass

    def supported_languages(self) -> List[str]:
        if not self._factory:
            return []
        try:
            enum = self._factory.get_SupportedLanguages()
            if not enum:
                return []
            return _drain_enum_string(enum, limit=10_000)
        except Exception:
            return []

if __name__ == "__main__":
    checker = WindowsSpellChecker("pt-PT")
    if checker.available:
        print(f"Idiomas suportados no teu PC: {checker.supported_languages()}")
        erros = checker.check("Isto é um errro de texte")
        print(f"Erros encontrados: {erros}")
        if erros:
            sugestoes = checker.suggest(erros[0][2])
            print(f"Sugestões para '{erros[0][2]}': {sugestoes}")
    else:
        print("Revisor não disponível. O comtypes está instalado?")