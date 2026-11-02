"""Render findings as plain-English Markdown and machine-readable JSON."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from . import __version__
from .checks import FAIL, INFO, ORDER, PASS, WARN, Finding, human

ICON = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL", INFO: "INFO"}
CATEGORY_TITLES = {
    "metadata": "Metadata", "license": "License", "readme": "README & documentation",
    "formats": "File formats", "naming": "File naming", "sensitive": "Sensitive data",
    "checksums": "Checksums", "size": "File sizes", "encoding": "Encoding",
}


def overall(findings: List[Finding]) -> str:
    statuses = {f.status for f in findings}
    return FAIL if FAIL in statuses else WARN if WARN in statuses else PASS


def build(dataset: str, targets: List[Dict[str, Any]], results: Dict[str, List[Finding]],
          files, metadata_path) -> Dict[str, Any]:
    return {
        "tool": "data-ready", "version": __version__,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": dataset,
        "metadata_file": str(metadata_path) if metadata_path else None,
        "summary": {"files": len(files), "total_bytes": sum(f.size for f in files)},
        "targets": [
            {
                "id": t["id"], "name": t.get("name", t["id"]),
                "rules_verified": t.get("verified"), "sources": t.get("sources", []),
                "notes": t.get("notes"),
                "status": overall(results[t["id"]]),
                "counts": {s: sum(1 for f in results[t["id"]] if f.status == s) for s in (PASS, WARN, FAIL, INFO)},
                "findings": [f.to_dict() for f in sorted(results[t["id"]], key=lambda f: ORDER[f.status])],
            }
            for t in targets
        ],
        "files": [{"path": f.rel, "bytes": f.size, "sha256": f.sha256, "columns": f.columns} for f in files],
    }


def to_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False)


def _files_line(files: List[str], limit: int = 6) -> str:
    if not files:
        return ""
    shown = ", ".join(f"`{x}`" for x in files[:limit])
    more = f" and {len(files) - limit} more" if len(files) > limit else ""
    return f" Files: {shown}{more}."


def to_markdown(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# Repository readiness report",
        "",
        f"- **Dataset:** `{report['dataset']}` ({s['files']} files, {human(s['total_bytes'])})",
        f"- **Metadata file:** {('`' + report['metadata_file'] + '`') if report['metadata_file'] else 'none found'}",
        f"- **Generated:** {report['generated']} by data-ready {report['version']}",
        "",
        "| Target | Result | Fail | Warn | Pass |",
        "|---|---|---|---|---|",
    ]
    for t in report["targets"]:
        c = t["counts"]
        lines.append(f"| {t['name']} | **{ICON[t['status']]}** | {c[FAIL]} | {c[WARN]} | {c[PASS]} |")
    lines.append("")
    lines.append("FAIL = the repository will reject it or the policy requires it. "
                 "WARN = likely to be queried by a curator or hurts reuse. Checks are automated heuristics; "
                 "a human should still review the deposit.")

    for t in report["targets"]:
        lines += ["", f"## {t['name']} — {ICON[t['status']]}", ""]
        if t.get("notes"):
            lines += [f"> {t['notes'].strip()}", ""]
        todo = [f for f in t["findings"] if f["status"] in (FAIL, WARN)]
        if todo:
            lines += ["### Fix-it list", ""]
            for i, f in enumerate(todo, 1):
                src = f" ([source]({f['source']}))" if f["source"] else ""
                lines.append(f"{i}. **[{ICON[f['status']]}] {f['title']}.** {f['fix']}{src}")
                extra = (f["detail"] + _files_line(f["files"])).strip()
                if extra:
                    lines.append(f"   - {extra}")
            lines.append("")
        else:
            lines += ["Nothing to fix. 🎉", ""]
        lines += ["### All checks", "", "| Status | Area | Check |", "|---|---|---|"]
        for f in t["findings"]:
            title = f["title"].replace("|", "\\|")
            lines.append(f"| {ICON[f['status']]} | {CATEGORY_TITLES.get(f['check'], f['check'])} | {title} |")
        if t["sources"]:
            lines += ["", f"Rules last verified {t['rules_verified']} against: " +
                      ", ".join(f"<{u}>" for u in t["sources"])]
    return "\n".join(lines) + "\n"
