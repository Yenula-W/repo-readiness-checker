"""Walk a dataset folder and collect facts about each file (no judgments here)."""
from __future__ import annotations

import csv
import hashlib
import io
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
    read_error: Optional[str] = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_delimited(fi: FileInfo) -> None:
    with fi.path.open("rb") as fb:
        head = fb.read(64 * 1024)
    try:
        text = head.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = head.decode("latin-1")
        fi.read_error = "not valid UTF-8 (read as Latin-1)"
    if fi.ext == ".txt":
        first = text.splitlines()[0] if text.strip() else ""
        if not any(d in first for d in ",\t;|"):
            return  # prose, not a table
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if fi.ext in (".tsv", ".tab") else csv.excel
    enc = "latin-1" if fi.read_error else "utf-8-sig"
    with fi.path.open("r", encoding=enc, newline="", errors="replace") as f:
        reader = csv.DictReader(f, dialect=dialect)
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


def scan(root: Path, hash_files: bool = True, hash_limit: int = HASH_LIMIT) -> List[FileInfo]:
    files: List[FileInfo] = []
    for p in sorted(root.rglob("*")):
        rel_parts = p.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts) or not p.is_file():
            continue
        fi = FileInfo(rel="/".join(rel_parts), path=p, size=p.stat().st_size, ext=p.suffix.lower())
        if hash_files and fi.size <= hash_limit:
            fi.sha256 = _sha256(p)
        try:
            if fi.ext in TABULAR and fi.size > 0:
                _read_delimited(fi)
            elif fi.ext in EXCEL and fi.size > 0:
                _read_excel(fi)
        except Exception as e:  # never crash the whole report on one bad file
            fi.read_error = f"could not read: {e}"
        files.append(fi)
    return files


def manifest_text(files: List[FileInfo]) -> str:
    """BagIt-style manifest: '<sha256>  <relative path>' per line."""
    buf = io.StringIO()
    for f in files:
        if f.sha256:
            buf.write(f"{f.sha256}  {f.rel}\n")
    return buf.getvalue()
