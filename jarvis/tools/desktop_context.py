from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

CF_UNICODETEXT = 13
SUPPORTED_DOC_EXTENSIONS = {".txt", ".md", ".log", ".py", ".kt", ".json", ".csv", ".pdf"}


def _read_windows_clipboard() -> str:
    """Read CF_UNICODETEXT from the Windows clipboard without spawning any window."""
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise ValueError("El portapapeles nativo de Windows no está disponible en este sistema.")

    user32 = windll.user32
    kernel32 = windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        raise ValueError("El portapapeles está vacío o no contiene texto.")

    if not user32.OpenClipboard(None):
        raise ValueError("No se pudo abrir el portapapeles de Windows.")

    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            raise ValueError("El portapapeles está vacío o no contiene texto.")
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise ValueError("No se pudo leer el contenido del portapapeles.")
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def read_clipboard_text(max_chars: int = 1800) -> str:
    """Return truncated text from the Windows clipboard or raise ValueError if empty/unavailable."""
    if max_chars <= 0:
        raise ValueError("max_chars debe ser mayor que 0.")

    text = _read_windows_clipboard().strip()
    if not text:
        raise ValueError("El portapapeles está vacío o no contiene texto.")
    return text[:max_chars]


def _default_search_roots() -> list[Path]:
    home = Path.home()
    candidates = [
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        Path.cwd(),
    ]
    roots: list[Path] = []
    seen: set[Path] = set()
    for root in candidates:
        resolved = root.resolve()
        if resolved not in seen and resolved.exists() and resolved.is_dir():
            seen.add(resolved)
            roots.append(resolved)
    return roots


def _iter_top_two_levels(root: Path) -> list[Path]:
    """Return supported files within depth 0 (root/*) and depth 1 (root/*/*)."""
    files: list[Path] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return files

    for entry in entries:
        try:
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
                files.append(entry)
            elif entry.is_dir():
                for child in entry.iterdir():
                    if child.is_file() and child.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
                        files.append(child)
        except OSError:
            continue
    return files


def _find_document(query_or_path: str, search_roots: list[Path] | None = None) -> Path:
    raw = query_or_path.strip().strip("\"'")
    if not raw:
        raise ValueError("Debes indicar el nombre o ruta del documento.")

    direct = Path(raw).expanduser()
    if direct.exists() and direct.is_file():
        if direct.suffix.lower() not in SUPPORTED_DOC_EXTENSIONS:
            raise ValueError(f"Formato de archivo no soportado: '{direct.suffix}'.")
        return direct

    roots = search_roots if search_roots is not None else _default_search_roots()
    needle = raw.lower()
    candidates: list[tuple[int, int, Path]] = []

    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for file_path in _iter_top_two_levels(root):
            name_lower = file_path.name.lower()
            stem_lower = file_path.stem.lower()
            if name_lower == needle:
                score = 0
            elif stem_lower == needle:
                score = 1
            elif needle in name_lower:
                score = 2
            else:
                continue
            candidates.append((score, len(str(file_path)), file_path))

    if not candidates:
        raise FileNotFoundError(f"No se encontró el documento '{raw}'.")

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _extract_document_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("Para leer archivos PDF instala 'pypdf'.") from exc
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        return "\n".join(p for p in pages if p)

    return path.read_text(encoding="utf-8", errors="replace")


def read_local_document(
    query_or_path: str,
    search_roots: list[Path] | None = None,
    max_chars: int = 2400,
) -> tuple[Path, str]:
    """Find a local document and return (path, truncated_text)."""
    if max_chars <= 0:
        raise ValueError("max_chars debe ser mayor que 0.")

    path = _find_document(query_or_path, search_roots=search_roots)
    content = _extract_document_text(path).strip()
    if not content:
        raise ValueError(f"El documento '{path.name}' está vacío.")
    return path, content[:max_chars]
