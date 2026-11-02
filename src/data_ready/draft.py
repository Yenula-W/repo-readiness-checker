"""Emit draft metadata files from what is known. Unknown values become TODO markers.

Never invent: every value comes from the user's metadata file, the README's H1 /
first paragraph, or the LICENSE text. Everything else is a "TODO: ..." string.
"""
from __future__ import annotations

from typing import Any, Dict, List

TODO = "TODO"


def _get(md: Dict, inf: Dict, key: str, hint: str):
    if md.get(key) not in (None, "", []):
        return md[key]
    if inf.get(key) not in (None, "", []):
        return inf[key]
    return f"{TODO}: {hint}"


def _creators(md: Dict) -> List[Dict[str, str]]:
    creators = md.get("creators") or []
    if not creators:
        return [{"name": f"{TODO}: Family, Given", "affiliation": f"{TODO}: institution",
                 "orcid": f"{TODO}: 0000-0000-0000-0000 (optional)"}]
    out = []
    for c in creators:
        out.append({"name": c.get("name", f"{TODO}: Family, Given"),
                    "affiliation": c.get("affiliation", f"{TODO}: institution"),
                    **({"orcid": c["orcid"]} if c.get("orcid") else {})})
    return out


def zenodo_json(md: Dict[str, Any], inf: Dict[str, Any]) -> Dict[str, Any]:
    """Draft .zenodo.json (legacy deposit schema used by the GitHub integration)."""
    kw = md.get("keywords") or [f"{TODO}: keyword 1", f"{TODO}: keyword 2"]
    lic = _get(md, inf, "license", "SPDX id e.g. cc-by-4.0 or cc0-1.0")
    out = {
        "upload_type": md.get("resource_type") or "dataset",
        "title": _get(md, inf, "title", "dataset title"),
        "creators": _creators(md),
        "description": _get(md, inf, "description", "what the data are, how they were made, how to reuse them"),
        "keywords": kw,
        "license": lic.lower() if not str(lic).startswith(TODO) else lic,
        "publication_date": md.get("publication_date") or f"{TODO}: YYYY-MM-DD",
        "access_right": "open",
    }
    if md.get("version"):
        out["version"] = md["version"]
    if md.get("funding"):
        out["grants"] = [{"id": g} for g in md["funding"]]
    if md.get("related_identifiers"):
        out["related_identifiers"] = [{"identifier": r, "relation": f"{TODO}: e.g. isSupplementTo"}
                                      for r in md["related_identifiers"]]
    return out


def datacite_json(md: Dict[str, Any], inf: Dict[str, Any]) -> Dict[str, Any]:
    """Draft DataCite Metadata Schema 4.x JSON (attributes block, as used by the DataCite REST API)."""
    pub = str(md.get("publication_date") or "")
    creators = []
    for c in _creators(md):
        entry: Dict[str, Any] = {"name": c["name"], "nameType": "Personal",
                                 "affiliation": [{"name": c["affiliation"]}]}
        if c.get("orcid") and not c["orcid"].startswith(TODO):
            entry["nameIdentifiers"] = [{"nameIdentifier": c["orcid"], "nameIdentifierScheme": "ORCID",
                                         "schemeUri": "https://orcid.org"}]
        creators.append(entry)
    lic = _get(md, inf, "license", "SPDX id")
    attrs = {
        "doi": f"{TODO}: assigned by the repository",
        "titles": [{"title": _get(md, inf, "title", "dataset title")}],
        "creators": creators,
        "publisher": f"{TODO}: repository name (e.g. Zenodo)",
        "publicationYear": pub[:4] if pub[:4].isdigit() else f"{TODO}: YYYY",
        "types": {"resourceTypeGeneral": "Dataset"},
        "subjects": [{"subject": k} for k in (md.get("keywords") or [f"{TODO}: keyword"])],
        "descriptions": [{"description": _get(md, inf, "description", "abstract"), "descriptionType": "Abstract"}],
        "rightsList": [{"rightsIdentifier": lic, "rightsIdentifierScheme": "SPDX"}],
        "schemaVersion": "http://datacite.org/schema/kernel-4",
    }
    if md.get("methods"):
        attrs["descriptions"].append({"description": md["methods"], "descriptionType": "Methods"})
    if md.get("funding"):
        attrs["fundingReferences"] = [{"funderName": f"{TODO}: funder name", "awardNumber": g}
                                      for g in md["funding"]]
    return {"data": {"type": "dois", "attributes": attrs}}


def count_todos(obj: Any) -> int:
    if isinstance(obj, str):
        return int(obj.startswith(TODO))
    if isinstance(obj, dict):
        return sum(count_todos(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(count_todos(v) for v in obj)
    return 0
