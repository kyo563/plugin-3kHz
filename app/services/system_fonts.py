"""Read installed Windows font family names; never open or distribute font files."""
import ctypes
from ctypes import wintypes
import sys
import unicodedata


def valid_family(name: str) -> bool:
    return (isinstance(name, str) and 0 < len(name) <= 128 and bool(name.strip())
            and not any(unicodedata.category(c).startswith('C') for c in name))


def font_id(name: str) -> str:
    return 'system:' + name.encode('utf-8').hex()


def enumerate_windows_fonts():
    if sys.platform != 'win32':
        return []

    class LOGFONTW(ctypes.Structure):
        _fields_ = [(name, wintypes.LONG) for name in
                    ('lfHeight', 'lfWidth', 'lfEscapement', 'lfOrientation', 'lfWeight')] + [
            (name, wintypes.BYTE) for name in ('lfItalic', 'lfUnderline', 'lfStrikeOut',
                'lfCharSet', 'lfOutPrecision', 'lfClipPrecision', 'lfQuality', 'lfPitchAndFamily')
        ] + [('lfFaceName', wintypes.WCHAR * 32)]

    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(LOGFONTW),
                                      ctypes.c_void_p, wintypes.DWORD, ctypes.c_ssize_t)
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    gdi.DeleteDC.restype = wintypes.BOOL
    gdi.EnumFontFamiliesExW.argtypes = [wintypes.HDC, ctypes.POINTER(LOGFONTW),
                                      callback_type, ctypes.c_ssize_t, wintypes.DWORD]
    gdi.EnumFontFamiliesExW.restype = ctypes.c_int
    found = {}

    @callback_type
    def collect(logfont, _metric, _type, _param):
        font = logfont.contents
        name = font.lfFaceName
        if valid_family(name) and not name.startswith('@'):
            # SHIFTJIS_CHARSET indicates Japanese support, not full glyph coverage.
            found[name] = found.get(name, False) or font.lfCharSet == 128
        return 1

    dc = gdi.CreateCompatibleDC(None)
    if not dc:
        raise OSError('Font enumeration unavailable')
    try:
        query = LOGFONTW()
        query.lfCharSet = 1  # DEFAULT_CHARSET: all families and character sets.
        gdi.EnumFontFamiliesExW(dc, ctypes.byref(query), collect, 0, 0)
    finally:
        gdi.DeleteDC(dc)
    return [{'id': font_id(name), 'name': name, 'japanese': japanese}
            for name, japanese in sorted(found.items(), key=lambda item: (not item[1], item[0].casefold()))]
