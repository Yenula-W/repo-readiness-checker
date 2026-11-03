"""Walk a dataset folder and collect facts about each file (no judgments here)."""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

TABULAR = {".csv", ".tsv", ".tab", ".txt"}
EXCEL = {".xlsx", ".xlsm"}
SAMPLE_ROWS = 2000
HASH_LIMIT = 2 * 1024**3  # skip hashing files over 2 GiB unless asked
# Folders we never descend into (tool/VCS state, not data).
SKIP_DIRS = {".git", ".venv", "__pycache__", ".data-ready"}


@dataclass
class FileInfo:
    rel: str
    path: Path
    size: int
    ext: str
    sha256: Optional[str] = None
    columns: List[str] = field(default_factory=list)
    sample: List[Dict[str, str]] = field(default_factory=list)
    sheets: List[str] = field(default_factory=list)
    is_symlink: bool = False
    archive_members: Optional[List[str]] = None  # .zip only: names inside the archive
    read_error: Optional[str] = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


READ_LIMIT = 4 * 1024 * 1024  # parse at most the first 4 MB of a text table


def _decode_head(raw: bytes, truncated: bool):
    """Decode a byte prefix. Returns (text, error or None). A multi-byte character cut
    off at the end of the prefix is not an encoding error."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace"), "not valid UTF-8 (UTF-16 encoded)"
    dec = codecs.getincrementaldecoder("utf-8-sig")()
    try:
        return dec.decode(raw, final=not truncated), None
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "not valid UTF-8 (read as Windows-1252/Latin-1)"


def _read_delimited(fi: FileInfo) -> None:
    with fi.path.open("rb") as fb:
        raw = fb.read(READ_LIMIT + 1)
    truncated = len(raw) > READ_LIMIT
    text, err = _decode_head(raw[:READ_LIMIT], truncated)
    if err:
        fi.read_error = err
    if truncated and "\n" in text:
        text = text[: text.rfind("\n") + 1]  # drop the partial last line
    if "\x00" in text[:65536]:
        fi.read_error = "contains NUL bytes; looks like a binary file, not text"
        return
    if fi.ext == ".txt":
        first = text.splitlines()[0] if text.strip() else ""
        if not any(d in first for d in ",\t;|"):
            return  # prose, not a table
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if fi.ext in (".tsv", ".tab") else csv.excel
    reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
    fi.columns = [c.strip() for c in (reader.fieldnames or []) if c is not None]
    for i, row in enumerate(reader):
        if i >= SAMPLE_ROWS:
            break
        fi.sample.append({k: v for k, v in row.items() if k is not None and isinstance(v, str)})


def _read_excel(fi: FileInfo) -> None:
    try:
        import openpyxl  # optional dependency
    except ImportError:
        fi.read_error = "install openpyxl to inspect Excel columns"
        return
    wb = openpyxl.load_workbook(fi.path, read_only=True, data_only=True)
    fi.sheets = list(wb.sheetnames)
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            continue
        cols = [str(c).strip() for c in header if c is not None]
        fi.columns.extend(c for c in cols if c not in fi.columns)
        for i, r in enumerate(rows):
            if i >= SAMPLE_ROWS:
                break
            fi.sample.append({str(h): "" if v is None else str(v) for h, v in zip(header, r) if h is not None})
    wb.close()


def _read_zip(fi: FileInfo) -> None:
    try:
        with zipfile.ZipFile(fi.path) as zf:
            fi.archive_members = [i.filename for i in zf.infolist() if not i.is_dir()]
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError) as e:
        fi.read_error = f"archive could not be opened ({e})"


def scan(root: Path, hash_files: bool = True, hash_limit: float = HASH_LIMIT) -> List[FileInfo]:
    """List every file under root. Never follows symlinks (no loops) and never raises on one bad file."""
    files: List[FileInfo] = []
    walk_errors: List[OSError] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=walk_errors.append):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        base = Path(dirpath)
        # Symlinked folders are listed (as links) but never entered.
        entries = filenames + [d for d in dirnames if (base / d).is_symlink()]
        for name in sorted(entries):
            p = base / name
            rel = p.relative_to(root).as_posix()
            fi = FileInfo(rel=rel, path=p, size=0, ext=p.suffix.lower())
            try:
                if p.is_symlink():
                    fi.is_symlink = True
                    fi.read_error = "symbolic link (not followed)"
                    files.append(fi)
                    continue
                fi.size = p.stat().st_size
                if hash_files and fi.size <= hash_limit:
                    fi.sha256 = _sha256(p)
                if fi.ext in TABULAR and fi.size > 0:
                    _read_delimited(fi)
                elif fi.ext in EXCEL and fi.size > 0:
                    _read_excel(fi)
                elif fi.ext == ".zip":
                    _read_zip(fi)
            except PermissionError:
                fi.read_error = "permission denied"
            except Exception as e:  # never crash the whole report on one bad file
                fi.read_error = f"could not read: {type(e).__name__}: {e}"[:300]
            files.append(fi)
    for err in walk_errors:
        rel = Path(err.filename).relative_to(root).as_posix() if err.filename else "?"
        files.append(FileInfo(rel=rel + "/", path=Path(err.filename or root), size=0, ext="",
                              read_error=f"folder could not be read ({err.strerror})"))
    return files


def manifest_text(files: List[FileInfo]) -> str:
    """BagIt-style manifest: '<sha256>  <relative path>' per line."""
    buf = io.StringIO()
    for f in files:
        if f.sha256:
            buf.write(f"{f.sha256}  {f.rel}\n")
    return buf.getvalue()
