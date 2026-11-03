"""Read user metadata from common formats into one canonical dict.

Canonical keys: title, creators (list of {name, affiliation, email, orcid}),
description, keywords, license, publication_date, resource_type, subjects,
funding, related_identifiers, methods, version, journal.

Nothing here invents values: a key is only set when the source has it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

AUTO_NAMES = [".zenodo.json", "zenodo.json", "datacite.json", "CITATION.cff",
              "metadata.json", "metadata.yaml", "metadata.yml", "dataset.yaml", "datapackage.json"]


def find_metadata_file(root: Path) -> Optional[Path]:
    for name in AUTO_NAMES:
        p = root / name
        if p.is_file():
            return p
    return None


def _as_list(v: Any) -> List:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [s.strip() for s in re.split(r"[;,]", v) if s.strip()]
    return [v]


def _creator(c: Any) -> Dict[str, str]:
    if isinstance(c, str):
        return {"name": c}
    if not isinstance(c, dict):
        return {}
    name = c.get("name") or c.get("full_name")
    if not name:
        given = c.get("given-names") or c.get("givenName") or c.get("given_name") or ""
        family = c.get("family-names") or c.get("familyName") or c.get("family_name") or ""
        name = f"{family}, {given}".strip(", ") if (given or family) else None
    aff = c.get("affiliation")
    if isinstance(aff, list):  # DataCite: [{"name": ...}] or [str]
        aff = "; ".join(a.get("name", "") if isinstance(a, dict) else str(a) for a in aff)
    orcid = c.get("orcid")
    for ni in c.get("nameIdentifiers", []) or []:
        if isinstance(ni, dict) and "orcid" in str(ni.get("nameIdentifierScheme", "")).lower():
            orcid = ni.get("nameIdentifier")
    out = {"name": name, "affiliation": aff, "email": c.get("email"), "orcid": orcid}
    return {k: v for k, v in out.items() if v}


def _grant(g: Any) -> Optional[str]:
    """'Funder name: award code' from Zenodo/InvenioRDM grant objects or plain strings."""
    if not isinstance(g, dict):
        return str(g) if g else None
    funder = g.get("funder")
    funder = funder.get("name") if isinstance(funder, dict) else funder
    award = g.get("code") or g.get("number") or g.get("id") or g.get("awardNumber")
    if isinstance(award, dict):
        award = award.get("number") or award.get("id")
    parts = [str(x) for x in (funder, award) if x]
    return ": ".join(parts) or None


def _license(v: Any) -> Optional[str]:
    if isinstance(v, dict):
        return (v.get("id") or v.get("identifier") or v.get("rightsIdentifier") or v.get("name")
                or license_from_url(v.get("path") or v.get("url") or v.get("rightsUri")))
    if isinstance(v, list) and v:
        return _license(v[0])
    return v or None


def normalize(raw: Dict[str, Any], fmt: str) -> Dict[str, Any]:
    if fmt == "datacite":
        a = raw.get("data", {}).get("attributes", raw)
        titles = a.get("titles") or []
        descs = a.get("descriptions") or []
        out = {
            "title": titles[0].get("title") if titles else None,
            "creators": [_creator(c) for c in a.get("creators", [])],
            "description": next((d.get("description") for d in descs
                                 if d.get("descriptionType", "Abstract") == "Abstract"), None),
            "methods": next((d.get("description") for d in descs
                             if d.get("descriptionType") == "Methods"), None),
            "keywords": [s.get("subject") for s in a.get("subjects", []) if not s.get("subjectScheme")],
            "subjects": [s.get("subject") for s in a.get("subjects", []) if s.get("subjectScheme")],
            "license": _license(a.get("rightsList")),
            "publication_date": str(a.get("publicationYear") or "") or None,
            "resource_type": (a.get("types") or {}).get("resourceTypeGeneral"),
            "funding": [": ".join(x for x in (f.get("funderName"), f.get("awardNumber")) if x)
                        for f in a.get("fundingReferences", []) if f.get("funderName") or f.get("awardNumber")],
            "related_identifiers": [r.get("relatedIdentifier") for r in a.get("relatedIdentifiers", [])],
            "version": a.get("version"),
        }
    elif fmt == "datapackage":  # Frictionless Data Package
        out = {
            "title": raw.get("title"),
            "creators": [_creator({"name": c.get("title"), "email": c.get("email"),
                                   "affiliation": c.get("organization")})
                         for c in raw.get("contributors", []) if isinstance(c, dict) and c.get("title")],
            "description": raw.get("description"),
            "keywords": _as_list(raw.get("keywords")),
            "license": _license(raw.get("licenses")),
            "publication_date": raw.get("created"),
            "version": raw.get("version"),
            "related_identifiers": [s.get("path") for s in raw.get("sources", []) if isinstance(s, dict)],
        }
    elif fmt == "cff":
        out = {
            "title": raw.get("title"),
            "creators": [_creator(c) for c in raw.get("authors", [])],
            "description": raw.get("abstract"),
            "keywords": _as_list(raw.get("keywords")),
            "license": _license(raw.get("license")),
            "publication_date": str(raw.get("date-released") or "") or None,
            "resource_type": raw.get("type"),
            "version": str(raw.get("version") or "") or None,
            "related_identifiers": [i.get("value") for i in raw.get("identifiers", []) if isinstance(i, dict)],
        }
    else:  # zenodo (.zenodo.json / deposit metadata) or generic canonical
        m = raw.get("metadata", raw)
        rt = m.get("resource_type")
        if isinstance(rt, dict):  # InvenioRDM style {"id": "dataset"}
            rt = rt.get("id") or rt.get("type")
        out = {
            "title": m.get("title"),
            "creators": [_creator(c) for c in _as_list(m.get("creators") or m.get("authors"))],
            "description": m.get("description") or m.get("abstract"),
            "keywords": _as_list(m.get("keywords")),
            "license": _license(m.get("license")),
            "publication_date": m.get("publication_date"),
            "resource_type": m.get("upload_type") or rt or m.get("item_type"),
            "subjects": _as_list(m.get("subjects") or m.get("categories") or m.get("research_domain")),
            "funding": [_grant(g) for g in _as_list(m.get("grants") or m.get("funding"))],
            "related_identifiers": [r.get("identifier") if isinstance(r, dict) else r
                                    for r in _as_list(m.get("related_identifiers") or m.get("related_works"))],
            "methods": m.get("method") or m.get("methods") or m.get("notes"),
            "version": m.get("version"),
            "journal": m.get("journal_title") or m.get("journal"),
        }
        out["subjects"] = [s.get("term") if isinstance(s, dict) else s for s in out["subjects"]]
    out = {k: ([x for x in v if x not in (None, "")] if isinstance(v, list) else v) for k, v in out.items()}
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


class MetadataError(ValueError):
    """The metadata file exists but cannot be parsed."""


def load_metadata(path: Path) -> Tuple[Dict[str, Any], str]:
    try:
        text = path.read_bytes().decode("utf-8-sig")
        raw = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError, OSError) as e:
        first = str(e).splitlines()[0] if str(e) else type(e).__name__
        raise MetadataError(f"{path.name} could not be parsed: {first}") from e
    raw = raw or {}
    if not isinstance(raw, dict):
        raise MetadataError(f"{path.name} must contain a mapping of fields, not a {type(raw).__name__}")
    if path.name.lower() == "citation.cff":
        fmt = "cff"
    elif path.name.lower() == "datapackage.json" or "resources" in raw and "metadata" not in raw:
        fmt = "datapackage"
    elif "titles" in raw or isinstance(raw.get("data"), dict) and "attributes" in raw["data"]:
        fmt = "datacite"
    else:
        fmt = "zenodo"
    try:
        return normalize(raw, fmt), fmt
    except (AttributeError, TypeError, KeyError, IndexError) as e:
        raise MetadataError(f"{path.name} has an unexpected structure ({type(e).__name__}: {e})") from e


# --- inference from the dataset itself (README / LICENSE) -------------------

LICENSE_PATTERNS = [
    ("CC0-1.0", r"CC0|Creative Commons Zero|public domain dedication"),
    ("CC-BY-4.0", r"Attribution 4\.0 International|CC[- ]BY[- ]4\.0"),
    ("CC-BY-SA-4.0", r"Attribution-ShareAlike 4\.0|CC[- ]BY[- ]SA(?![- ]?NC)"),
    ("CC-BY-NC-4.0", r"Attribution-NonCommercial 4\.0|CC[- ]BY[- ]NC(?![- ](SA|ND))"),
    ("CC-BY-NC-SA-4.0", r"Attribution-NonCommercial-ShareAlike 4\.0|CC[- ]BY[- ]NC[- ]SA"),
    ("CC-BY-ND-4.0", r"Attribution-NoDerivatives 4\.0|CC[- ]BY[- ]ND"),
    ("CC-BY-NC-ND-4.0", r"Attribution-NonCommercial-NoDerivatives 4\.0|CC[- ]BY[- ]NC[- ]ND"),
    ("MIT", r"\bMIT License\b|Permission is hereby granted, free of charge"),
    ("Apache-2.0", r"Apache License,? Version 2\.0"),
    ("ODbL-1.0", r"Open Database License"),
]


LICENSE_ALIASES = {
    "cc0-1.0": ["cc0", "cc-zero", "cc0-1.0", "cc-0", "creative commons zero", "public domain dedication",
                "cc0 1.0 universal"],
    "cc-by-4.0": ["cc-by-4.0", "cc-by", "cc by 4.0", "creative commons attribution 4.0"],
}


def canonical_license(value: Any) -> str:
    """Map repository-specific license ids (Zenodo 'cc-zero', 'CC0 1.0') to one SPDX-like id."""
    v = str(value or "").strip().lower()
    for spdx, aliases in LICENSE_ALIASES.items():
        if v in aliases or any(v.startswith(a) for a in aliases if len(a) > 6):
            return spdx
    return v


CC_URL_RE = re.compile(r"creativecommons\.org/(?:licenses/(by(?:-nc)?(?:-sa|-nd)?)|publicdomain/(zero))/(\d\.\d)", re.I)


def license_from_url(url: Any) -> Optional[str]:
    m = CC_URL_RE.search(str(url or ""))
    if not m:
        return None
    return f"CC0-{m.group(3)}" if m.group(2) else f"CC-{m.group(1).upper()}-{m.group(3)}"


def detect_license_text(text: str) -> Optional[str]:
    """The license whose name appears first. Legal codes name themselves in the title; later
    mentions (every CC 4.0 legal code ends with a note about CC0) must not win."""
    hits = []
    for spdx, pat in LICENSE_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            hits.append((m.start(), spdx))
    return min(hits)[1] if hits else None


LICENSE_SECTION_RE = re.compile(r"^(?:#+\s*|\**)(?:licen[cs]e|licensing|terms of use|copyright)\b[^\n]*", re.I | re.M)


def license_from_readme(text: str) -> Optional[str]:
    """License named in a README's 'License'/'Licence' heading or line, never elsewhere
    (READMEs also cite the licenses of software and other people's data)."""
    for m in LICENSE_SECTION_RE.finditer(text):
        lic = detect_license_text(text[m.start():m.start() + 400]) or license_from_url(text[m.start():m.start() + 400])
        if lic:
            return lic
    return None


def infer_from_readme(text: str) -> Dict[str, str]:
    """Title = first Markdown H1; description = first prose paragraph; license = the one named
    in a License/Licence section. Nothing else."""
    out: Dict[str, str] = {}
    lic = license_from_readme(text)
    if lic:
        out["license"] = lic
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        # "# Title: My data" -> "My data"; strip Markdown emphasis.
        title = re.sub(r"^(title|dataset|data set)\s*[:\-–]\s*", "", m.group(1).strip(), flags=re.I)
        out["title"] = title.strip("*_ ").strip()
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        # Not a description: a quoted paper title, a "supporting:" lead-in, a "Contact: ..."
        # label line or a numbered list item.
        quoted = b[:1] in "\"“'" and b.rstrip(".")[-1:] in "\"”'"
        intro = re.match(r"(description|abstract|summary|overview|about)\s*:\s*", b, re.I)
        if intro:
            b = b[intro.end():]
        label = not intro and re.match(r"(\d+[.)]\s|[A-Z][\w ]{0,30}:\s)", b)
        if b and not b.startswith(("#", "-", "*", "|", "```", "<", "!")) and len(b) > 40 and not quoted \
                and not b.endswith(":") and not label:
            out["description"] = " ".join(b.split())
            break
    return out
