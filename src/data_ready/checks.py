"""Turn scanned facts + metadata + target rules into pass/warn/fail findings."""
from __future__ import annotations

import fnmatch
import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .metadata import detect_license_text
from .scan import FileInfo

PASS, WARN, FAIL, INFO = "pass", "warn", "fail", "info"
ORDER = {FAIL: 0, WARN: 1, INFO: 2, PASS: 3}


@dataclass
class Finding:
    check: str
    status: str
    title: str
    detail: str = ""
    fix: str = ""
    source: str = ""
    files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Context:
    root: Path
    files: List[FileInfo]
    rules: Dict[str, Any]
    metadata: Dict[str, Any]          # from the user's metadata file
    inferred: Dict[str, Any]          # from README / LICENSE (never invented)
    metadata_path: Optional[Path]
    readme: Optional[FileInfo] = None
    readme_text: str = ""
    docs_text: str = ""               # README + data dictionaries, lower-cased
    doc_files: List[str] = field(default_factory=list)


README_RE = re.compile(r"^readme([._-].*)?(\.(md|markdown|txt|rst|pdf|html))?$", re.I)
DICT_RE = re.compile(r"(dictionary|codebook|data[_-]?dict|variables|schema|field[_-]?descriptions)", re.I)
TEXT_DOC_EXT = {".md", ".markdown", ".txt", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml", ".html"}
LICENSE_RE = re.compile(r"^(license|licence|copying)(\.(md|txt))?$", re.I)


def _read_text(path: Path, limit: int = 2_000_000) -> str:
    try:
        return path.read_bytes()[:limit].decode("utf-8", errors="replace")
    except OSError:
        return ""


def prepare(ctx: Context) -> None:
    """Locate README, data dictionaries and other docs used by several checks."""
    top = [f for f in ctx.files if "/" not in f.rel]
    readmes = [f for f in top if README_RE.match(Path(f.rel).name)]
    if not readmes:  # accept a README one folder down, e.g. data/README.md
        readmes = [f for f in ctx.files if README_RE.match(Path(f.rel).name)]
    readmes.sort(key=lambda f: (f.ext != ".md", f.rel.count("/"), f.rel))
    ctx.readme = readmes[0] if readmes else None
    corpus = []
    for f in ctx.files:
        name = Path(f.rel).name
        is_doc = README_RE.match(name) or (DICT_RE.search(name) and f.ext in TEXT_DOC_EXT | {".xlsx"})
        if is_doc:
            ctx.doc_files.append(f.rel)
            if f.ext == ".xlsx":
                corpus.append(" ".join(f.columns + [v for r in f.sample for v in r.values()]))
            elif f.ext != ".pdf":
                corpus.append(_read_text(f.path))
    if ctx.readme and ctx.readme.ext != ".pdf":
        ctx.readme_text = _read_text(ctx.readme.path)
    ctx.docs_text = "\n".join(corpus).lower()


# --- metadata --------------------------------------------------------------

def _field_value(ctx: Context, name: str):
    """Return (value, origin) where origin is 'metadata', 'inferred' or None."""
    md, inf = ctx.metadata, ctx.inferred
    if name.startswith("creator_"):
        sub = name.split("_", 1)[1]
        creators = md.get("creators") or []
        if creators and all(c.get(sub) for c in creators):
            return [c[sub] for c in creators], "metadata"
        if creators and any(c.get(sub) for c in creators):
            return None, "partial"
        return None, None
    if md.get(name) not in (None, "", []):
        return md[name], "metadata"
    if inf.get(name) not in (None, "", []):
        return inf[name], "inferred"
    return None, None


def _check_field(ctx: Context, spec: Dict, required: bool) -> Finding:
    name, label = spec["field"], spec.get("label", spec["field"])
    value, origin = _field_value(ctx, name)
    bad = FAIL if required else WARN
    kind = "Required" if required else "Recommended"
    src = spec.get("source", "")
    why = spec.get("why", "")
    if origin == "partial":
        return Finding("metadata", bad, f"{kind}: {label} missing for some creators", why,
                       f"Add {label.lower()} for every creator in your metadata file.", src)
    if value is None:
        return Finding("metadata", bad, f"{kind}: {label} not provided", why,
                       f"Add '{name}' to your metadata file (or fill it in on the deposit form).", src)
    count = len(value) if isinstance(value, list) else 1
    if spec.get("min_count") and count < spec["min_count"]:
        return Finding("metadata", bad, f"{kind}: {label} has {count}, needs {spec['min_count']}+",
                       why, f"Add at least {spec['min_count']} {label.lower()}.", src)
    if spec.get("min_length") and isinstance(value, str) and len(value.strip()) < spec["min_length"]:
        return Finding("metadata", bad, f"{kind}: {label} is too short", why,
                       f"Expand the {label.lower()} to at least {spec['min_length']} characters.", src)
    if origin == "inferred":
        return Finding("metadata", WARN, f"{kind}: {label} only found in README/LICENSE",
                       f"Inferred value: {str(value)[:120]!r}. Repositories need it entered as metadata.",
                       f"Copy the {label.lower()} into your metadata file / deposit form and check it.", src)
    return Finding("metadata", PASS, f"{label} present", source=src)


def check_metadata(ctx: Context) -> List[Finding]:
    out = []
    if ctx.metadata_path is None:
        out.append(Finding("metadata", INFO, "No metadata file found",
                           "Checked README/LICENSE instead. Supported: .zenodo.json, datacite.json, CITATION.cff, metadata.yaml.",
                           "Run with --draft-metadata to generate a starter file with TODOs."))
    for spec in ctx.rules.get("required_metadata", []):
        out.append(_check_field(ctx, spec, True))
    for spec in ctx.rules.get("recommended_metadata", []):
        out.append(_check_field(ctx, spec, False))
    return out


# --- license ---------------------------------------------------------------

def check_license(ctx: Context) -> List[Finding]:
    rules = ctx.rules.get("license") or {}
    src = rules.get("source", "")
    lic_file = next((f for f in ctx.files if "/" not in f.rel and LICENSE_RE.match(f.rel)), None)
    file_lic = detect_license_text(_read_text(lic_file.path)) if lic_file else None
    md_lic = ctx.metadata.get("license")
    found = md_lic or file_lic
    only = rules.get("only")
    out = []
    if only:
        lic = str(found or "")
        if found and not any(o.lower().replace("-1.0", "") in lic.lower() for o in only):
            out.append(Finding("license", FAIL, f"License '{found}' is not accepted",
                               rules.get("message", ""), f"Use {', '.join(only)} or deposit elsewhere.", src))
        else:
            out.append(Finding("license", PASS, f"License compatible with {', '.join(only)}",
                               rules.get("message", ""), source=src))
        return out
    if found:
        where = "metadata" if md_lic else f"{lic_file.rel}"
        out.append(Finding("license", PASS, f"License: {found} (from {where})", source=src))
    elif lic_file:
        out.append(Finding("license", WARN, f"{lic_file.rel} present but license not recognised",
                           "Could not match a standard license text.",
                           "Name the license with its SPDX id (e.g. CC-BY-4.0, CC0-1.0) in your metadata.", src,
                           [lic_file.rel]))
    else:
        in_metadata_rules = any(s.get("field") == "license" for s in ctx.rules.get("required_metadata", []))
        sev = INFO if in_metadata_rules else FAIL if rules.get("required") else WARN
        out.append(Finding("license", sev, "No LICENSE file or license metadata found",
                           "Without a license, others cannot legally reuse the data.",
                           "Choose a license (CC-BY-4.0 or CC0-1.0 are common for data) and add it to metadata plus a LICENSE file.",
                           src))
    return out


# --- README / documentation -------------------------------------------------

def _mentioned(needle: str, haystack: str) -> bool:
    n = needle.lower().strip()
    if not n:
        return True
    return re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", haystack) is not None


def _file_described(rel: str, docs: str) -> bool:
    p = Path(rel)
    if _mentioned(p.name, docs) or _mentioned(rel, docs) or _mentioned(p.stem, docs) and len(p.stem) > 3:
        return True
    # A folder of many similar files can be described as a group (e.g. "images/" or "*.tif").
    for parent in p.parents:
        if str(parent) not in (".", "") and _mentioned(str(parent) + "/", docs):
            return True
    return f"*{p.suffix.lower()}" in docs if p.suffix else False


SKIP_DESCRIBE = re.compile(r"^(license|licence|copying|citation\.cff|\.zenodo\.json|datacite\.json|"
                           r"metadata\.(json|ya?ml)|manifest-.*|checksums.*|md5sum.*|sha256sum.*|\.gitignore)$", re.I)


def check_readme(ctx: Context) -> List[Finding]:
    rules = ctx.rules.get("readme") or {}
    src = rules.get("source", "")
    out: List[Finding] = []
    if ctx.readme is None:
        sev = FAIL if rules.get("required") else WARN
        return [Finding("readme", sev, "No README found",
                        "A README is how reusers learn what each file and column means.",
                        "Add README.md at the top level describing the files, columns, units and missing-value codes.",
                        src)]
    out.append(Finding("readme", PASS, f"README found: {ctx.readme.rel}", source=src))
    fmts = rules.get("required_format")
    if fmts and ctx.readme.ext not in fmts:
        out.append(Finding("readme", FAIL, f"README must be {'/'.join(fmts)}",
                           f"Found {ctx.readme.rel}.", f"Convert the README to {fmts[0]} (Markdown).", src,
                           [ctx.readme.rel]))
    if not ctx.readme_text.strip():
        out.append(Finding("readme", WARN, "README could not be read as text (PDF or empty)",
                           "Topic and coverage checks were skipped.", "Provide README.md (plain text).", src))
        return out
    text = ctx.readme_text.lower()
    missing_topics = [t["label"] for t in rules.get("topics", [])
                      if not any(k.lower() in text for k in t["keywords"])]
    if missing_topics:
        out.append(Finding("readme", WARN, f"README seems to be missing {len(missing_topics)} topic(s)",
                           "Not found: " + "; ".join(missing_topics),
                           "Add a short section for each missing topic.", src))
    else:
        out.append(Finding("readme", PASS, "README covers the expected topics", source=src))

    docs = ctx.docs_text
    if rules.get("describe_every_file"):
        undescribed = [f.rel for f in ctx.files
                       if f.rel not in ctx.doc_files and not SKIP_DESCRIBE.match(Path(f.rel).name)
                       and not _file_described(f.rel, docs)]
        if undescribed:
            out.append(Finding("readme", WARN, f"{len(undescribed)} file(s) not mentioned in README/data dictionary",
                               "Every file (or folder of similar files) should be described.",
                               "List each file/folder in the README with a one-line description.", src,
                               undescribed))
        else:
            out.append(Finding("readme", PASS, "Every file is mentioned in the documentation", source=src))
    if rules.get("describe_every_column"):
        gaps = {}
        for f in ctx.files:
            if f.columns and f.rel not in ctx.doc_files:
                miss = [c for c in f.columns if c and not _mentioned(c, docs)]
                if miss:
                    gaps[f.rel] = miss
        if gaps:
            n = sum(len(v) for v in gaps.values())
            detail = "; ".join(f"{k}: {', '.join(v[:8])}{' …' if len(v) > 8 else ''}" for k, v in gaps.items())
            out.append(Finding("readme", WARN, f"{n} column(s) not defined in README/data dictionary",
                               detail,
                               "Add a data dictionary (e.g. data_dictionary.csv: column, description, units, allowed values, missing code).",
                               src, list(gaps)))
        elif any(f.columns for f in ctx.files):
            out.append(Finding("readme", PASS, "Every column is defined in the documentation", source=src))
    return out


# --- formats ---------------------------------------------------------------

def check_formats(ctx: Context) -> List[Finding]:
    fm = ctx.rules.get("formats") or {}
    out = []
    by_ext = defaultdict(list)
    for f in ctx.files:
        by_ext[f.ext].append(f.rel)
    for ext, rels in sorted(by_ext.items()):
        if ext in (fm.get("rejected") or {}):
            r = fm["rejected"][ext]
            out.append(Finding("formats", FAIL, f"{ext} files are not accepted by this repository",
                               "", r["suggest"], r.get("source", ""), rels))
        elif ext in (fm.get("discouraged") or {}):
            r = fm["discouraged"][ext]
            # An open-format twin (same stem, .csv) next to the file satisfies the advice.
            twins = [x for x in rels if any(g.rel == str(Path(x).with_suffix(e))
                                             for g in ctx.files for e in (".csv", ".tsv", ".h5", ".nc", ".pdf", ".parquet"))]
            rest = [x for x in rels if x not in twins]
            if rest:
                out.append(Finding("formats", WARN, f"{len(rest)} {ext} file(s) in a proprietary/closed format",
                                   "", r["suggest"], r.get("source", ""), rest))
    if not any(o.status != PASS for o in out):
        out.append(Finding("formats", PASS, "All file formats are open or accepted"))
    return out


# --- file naming -----------------------------------------------------------

BAD_CHARS = re.compile(r"[^A-Za-z0-9._\-/]")


def check_naming(ctx: Context) -> List[Finding]:
    fn = ctx.rules.get("file_naming") or {}
    src = fn.get("source", "")
    max_len = fn.get("max_name_length", 64)
    junk, spaces, special, long_, nonascii = [], [], [], [], []
    lower_seen = defaultdict(list)
    for f in ctx.files:
        parts = f.rel.split("/")
        if any(fnmatch.fnmatch(part, pat) for part in parts for pat in fn.get("junk_patterns", [])):
            junk.append(f.rel)
            continue
        name = parts[-1]
        if " " in f.rel:
            spaces.append(f.rel)
        if any(ord(ch) > 127 for ch in f.rel):
            nonascii.append(f.rel)
        elif BAD_CHARS.search(f.rel.replace(" ", "")):
            special.append(f.rel)
        if len(name) > max_len:
            long_.append(f.rel)
        lower_seen[unicodedata.normalize("NFC", f.rel).lower()].append(f.rel)
    out = []
    if junk:
        out.append(Finding("naming", WARN, f"{len(junk)} system/temporary file(s) should be removed",
                           "", "Delete OS/editor junk (.DS_Store, ~$ lock files, __MACOSX…) before deposit.", src, junk))
    if spaces:
        out.append(Finding("naming", WARN, f"{len(spaces)} path(s) contain spaces",
                           "Spaces break command-line tools and URLs.", "Replace spaces with _ or -.", src, spaces))
    if special:
        out.append(Finding("naming", WARN, f"{len(special)} path(s) contain special characters",
                           "Use only letters, digits, _ - and .", "Rename using A-Z a-z 0-9 _ - .", src, special))
    if nonascii:
        out.append(Finding("naming", WARN, f"{len(nonascii)} path(s) contain non-ASCII characters",
                           "These can be mangled when zipped or downloaded on other systems.",
                           "Transliterate to ASCII.", src, nonascii))
    if long_:
        out.append(Finding("naming", WARN, f"{len(long_)} file name(s) longer than {max_len} characters",
                           "", "Shorten names; move detail into the README.", src, long_))
    clashes = [r for v in lower_seen.values() if len(v) > 1 for r in v]
    if clashes:
        out.append(Finding("naming", FAIL, "File names differ only by upper/lower case",
                           "They will overwrite each other on macOS/Windows.", "Rename so names are unique ignoring case.",
                           src, clashes))
    if not out:
        out.append(Finding("naming", PASS, "File names are clean", source=src))
    return out


# --- sensitive data ----------------------------------------------------------

PII_HEADERS = {
    "personal name": r"^(first|last|full|given|family|middle|patient|participant|subject|respondent|maiden)?_?names?$|^(sur|fore)name$|^firstname$|^lastname$|^fullname$",
    "email address": r"e_?mail",
    "date of birth": r"^(dob|d_o_b|birth_?date|date_?of_?birth|birthday)$",
    "medical record number": r"^(mrn|medical_?record.*|med_?rec.*|nhs_?(no|number)|health_?plan.*)$",
    "government ID": r"^(ssn|social_?security.*|sin|national_?insurance.*|passport.*|driver_?licen[cs]e.*)$",
    "phone number": r"^(phone|tel|telephone|mobile|cell|cell_?phone|fax|phone_?(no|number))$",
    "street address": r"^(address|street|street_?address|home_?address|address_?line.*|postcode|post_?code|zip|zip_?code|postal_?code)$",
    "IP address": r"^ip(_?address)?$",
}
PII_VALUES = {
    "email address": (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), 1),
    "US SSN": (re.compile(r"^\d{3}-\d{2}-\d{4}$"), 1),
    "phone number": (re.compile(r"^(\+?\d{1,2}[ .-])?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}$"), 3),
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")


def check_sensitive(ctx: Context) -> List[Finding]:
    sd = ctx.rules.get("sensitive_data") or {}
    sev = sd.get("severity", WARN)
    hits: Dict[str, List[str]] = defaultdict(list)
    for f in ctx.files:
        if not f.columns or f.rel in ctx.doc_files:
            continue
        for col in f.columns:
            h = _norm_header(col)
            for kind, pat in PII_HEADERS.items():
                if re.search(pat, h):
                    hits[f.rel].append(f"column '{col}' looks like {kind}")
                    break
            values = [str(r.get(col, "")).strip() for r in f.sample]
            for kind, (rx, min_hits) in PII_VALUES.items():
                n = sum(1 for v in values if v and rx.search(v))
                if n >= min_hits:
                    hits[f.rel].append(f"column '{col}' has {n} value(s) that look like {kind}")
                    break
    if not hits:
        return [Finding("sensitive", PASS, "No obvious personal identifiers in tabular files",
                        "Heuristic only: checks column names and the first rows. It does not replace a disclosure review.",
                        source=sd.get("source", ""))]
    detail = "; ".join(f"{k}: {', '.join(dict.fromkeys(v))}" for k, v in hits.items())
    return [Finding("sensitive", sev, "Possible personal identifiers (PII) found",
                    f"{sd.get('message', '')} Matches — {detail}",
                    "Remove or pseudonymise these columns, or use a controlled-access repository. Confirm with your IRB/privacy office.",
                    sd.get("source", ""), list(hits))]


# --- checksums ---------------------------------------------------------------

def _parse_manifest(text: str) -> Dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(MD5|SHA256)\s*\((.+)\)\s*=\s*([0-9a-fA-F]+)$", line)  # BSD style
        if m:
            out[m.group(2)] = m.group(3).lower()
            continue
        m = re.match(r"^([0-9a-fA-F]{32}|[0-9a-fA-F]{64})\s+\*?(.+)$", line)  # GNU / BagIt style
        if m:
            rel = m.group(2).strip()
            out[rel[2:] if rel.startswith("./") else rel] = m.group(1).lower()
    return out


def check_checksums(ctx: Context) -> List[Finding]:
    cs = ctx.rules.get("checksums") or {}
    src = cs.get("source", "")
    names = {n.lower() for n in cs.get("manifest_names", [])}
    manifests = [f for f in ctx.files if Path(f.rel).name.lower() in names]
    if not manifests:
        return [Finding("checksums", WARN, "No checksum manifest",
                        "A manifest lets you and the repository prove files were not corrupted in transfer.",
                        "Run `data-ready check <path> --write-manifest` to create manifest-sha256.txt.", src)]
    out = []
    by_rel = {f.rel: f for f in ctx.files}
    for m in manifests:
        entries = _parse_manifest(_read_text(m.path))
        base = str(Path(m.rel).parent)
        bad, missing = [], []
        for rel, digest in entries.items():
            full = rel if base in (".", "") else f"{base}/{rel}"
            f = by_rel.get(full) or by_rel.get(rel)
            if f is None:
                missing.append(rel)
                continue
            if len(digest) == 64:
                actual = f.sha256 or hashlib.sha256(f.path.read_bytes()).hexdigest()
            else:
                actual = hashlib.md5(f.path.read_bytes()).hexdigest()
            if actual != digest:
                bad.append(full)
        listed = {(rel if base in (".", "") else f"{base}/{rel}") for rel in entries}
        unlisted = [f.rel for f in ctx.files if f.rel not in listed and f is not m and f not in manifests]
        if bad:
            out.append(Finding("checksums", FAIL, f"{len(bad)} file(s) do not match {m.rel}",
                               "File changed or was corrupted since the manifest was made.",
                               "Re-check the file; regenerate the manifest only if the change was intended.", src, bad))
        if missing:
            out.append(Finding("checksums", WARN, f"{len(missing)} file(s) listed in {m.rel} are missing", "",
                               "Restore the files or regenerate the manifest.", src, missing))
        if unlisted:
            out.append(Finding("checksums", WARN, f"{len(unlisted)} file(s) not covered by {m.rel}", "",
                               "Regenerate the manifest with --write-manifest.", src, unlisted))
        if not (bad or missing or unlisted):
            out.append(Finding("checksums", PASS, f"All {len(entries)} checksums in {m.rel} verified", source=src))
    return out


# --- sizes ------------------------------------------------------------------

def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return str(n)


def check_sizes(ctx: Context) -> List[Finding]:
    sl = ctx.rules.get("size_limits") or {}
    src = sl.get("source", "")
    out = []
    empty = [f.rel for f in ctx.files if f.size == 0]
    if empty:
        out.append(Finding("size", WARN, f"{len(empty)} empty (0-byte) file(s)",
                           "", "Remove empty files or explain them in the README.", files=empty))
    total = sum(f.size for f in ctx.files)
    if sl.get("max_files") and len(ctx.files) > sl["max_files"]:
        out.append(Finding("size", FAIL, f"{len(ctx.files)} files exceeds the limit of {sl['max_files']}",
                           sl.get("note", ""), "Bundle related files into .zip/.tar.gz archives.", src))
    if sl.get("max_total_bytes") and total > sl["max_total_bytes"]:
        out.append(Finding("size", FAIL, f"Total size {human(total)} exceeds {human(sl['max_total_bytes'])}",
                           sl.get("note", ""), "Split the deposit or ask the repository about a quota increase.", src))
    if sl.get("max_file_bytes"):
        big = [f.rel for f in ctx.files if f.size > sl["max_file_bytes"]]
        if big:
            out.append(Finding("size", FAIL, f"{len(big)} file(s) larger than {human(sl['max_file_bytes'])}",
                               "", "Split large files or compress them.", src, big))
    if sl.get("recommended_max_file_bytes"):
        big = [f.rel for f in ctx.files if f.size > sl["recommended_max_file_bytes"]]
        if big:
            out.append(Finding("size", WARN, f"{len(big)} file(s) larger than recommended {human(sl['recommended_max_file_bytes'])}",
                               "Large files are hard for reusers to download.", "Consider splitting them.", src, big))
    if len(out) == (1 if empty else 0):  # nothing over a limit
        out.append(Finding("size", PASS, f"{len(ctx.files)} files, {human(total)} total — within limits", source=src))
    return out


def unreadable(ctx: Context) -> List[Finding]:
    bad = [f for f in ctx.files if f.read_error]
    if not bad:
        return []
    return [Finding("encoding", WARN, f"{len(bad)} file(s) had read problems",
                    "; ".join(f"{f.rel}: {f.read_error}" for f in bad[:10]),
                    "Save text/CSV files as UTF-8.", files=[f.rel for f in bad])]


ALL_CHECKS = [check_metadata, check_license, check_readme, check_formats, check_naming,
              check_sensitive, check_checksums, check_sizes, unreadable]


def run_all(ctx: Context) -> List[Finding]:
    prepare(ctx)
    findings: List[Finding] = []
    for fn in ALL_CHECKS:
        findings.extend(fn(ctx))
    return findings
