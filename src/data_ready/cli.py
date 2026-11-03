"""Command-line entry point: `data-ready check <path> --target zenodo`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, draft, report
from .checks import FAIL, Context, run_all
from .metadata import (MetadataError, detect_license_text, find_metadata_file,
                       infer_from_readme, load_metadata)
from .rules_loader import available_targets, load_target
from .scan import manifest_text, scan


def _infer(root: Path) -> dict:
    inferred = {}
    for name in ("README.md", "README.txt", "README", "readme.md", "README.rst"):
        p = root / name
        if p.is_file():
            try:
                inferred.update(infer_from_readme(p.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
            break
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"):
        p = root / name
        if p.is_file():
            try:
                lic = detect_license_text(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                lic = None
            if lic:
                inferred["license"] = lic
            break
    return inferred


def cmd_check(args: argparse.Namespace) -> int:
    try:
        return _check(args)
    except OSError as e:  # unwritable --out, manifest or draft location
        print(f"error: {e.strerror or e}: {e.filename or ''}", file=sys.stderr)
        return 2


def _check(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: {root} is not a folder", file=sys.stderr)
        return 2
    rules_dir = Path(args.rules_dir).resolve() if args.rules_dir else None
    try:
        targets = [load_target(t, rules_dir) for t in args.target]
    except KeyError as e:
        print(f"error: {e.args[0]}", file=sys.stderr)
        return 2

    md_path = Path(args.metadata).resolve() if args.metadata else find_metadata_file(root)
    metadata, md_error = {}, None
    if md_path:
        try:
            metadata, _ = load_metadata(md_path)
        except MetadataError as e:
            md_error = str(e)
            print(f"warning: {md_error}", file=sys.stderr)
    inferred = _infer(root)

    if args.write_manifest:
        files = scan(root, hash_limit=float("inf"))
        out = root / "manifest-sha256.txt"
        out.write_text(manifest_text([f for f in files if f.rel != "manifest-sha256.txt"]), encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)

    files = scan(root, hash_files=not args.no_hash)
    results = {}
    for t in targets:
        ctx = Context(root=root, files=files, rules=t, metadata=metadata, inferred=inferred,
                      metadata_path=md_path, metadata_error=md_error)
        results[t["id"]] = run_all(ctx)

    rep = report.build(str(root), targets, results, files, md_path)
    out_dir = Path(args.out).resolve() if args.out else None
    md_text, json_text = report.to_markdown(rep), report.to_json(rep)
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "readiness-report.md").write_text(md_text, encoding="utf-8")
        (out_dir / "readiness-report.json").write_text(json_text, encoding="utf-8")
        print(f"wrote {out_dir / 'readiness-report.md'} and readiness-report.json", file=sys.stderr)
    if args.format == "json":
        print(json_text)
    elif args.format == "markdown":
        print(md_text)
    else:
        for t in rep["targets"]:
            c = t["counts"]
            print(f"{t['name']}: {t['status'].upper()}  (fail {c['fail']}, warn {c['warn']}, pass {c['pass']})")
            for f in t["findings"]:
                if f["status"] in ("fail", "warn"):
                    print(f"  [{f['status'].upper()}] {f['title']}")
        if not out_dir:
            print("\nFull report: add --out <dir> (Markdown + JSON) or --format markdown.")

    if args.draft_metadata:
        d_dir = out_dir or root
        for kind in args.draft_metadata:
            obj = draft.zenodo_json(metadata, inferred) if kind == "zenodo" else draft.datacite_json(metadata, inferred)
            name = ".zenodo.draft.json" if kind == "zenodo" else "datacite.draft.json"
            (d_dir / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"wrote {d_dir / name} ({draft.count_todos(obj)} TODO field(s) to fill in)", file=sys.stderr)

    return 1 if any(t["status"] == FAIL for t in rep["targets"]) and args.strict else 0


def cmd_targets(args: argparse.Namespace) -> int:
    rules_dir = Path(args.rules_dir).resolve() if args.rules_dir else None
    for name in available_targets(rules_dir):
        t = load_target(name, rules_dir)
        print(f"{name:12} {t.get('name', name)}  (verified {t.get('verified', '?')})")
        for s in t.get("sources", []):
            print(f"{'':12}   {s}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="data-ready", description=__doc__)
    p.add_argument("--version", action="version", version=f"data-ready {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="check a dataset folder against one or more targets")
    c.add_argument("path", help="dataset folder")
    c.add_argument("--target", "-t", action="append", required=True,
                   help="target id (zenodo, dryad, figshare, nih-dms) or path to a rules YAML; repeatable")
    c.add_argument("--metadata", "-m", help="metadata file (.zenodo.json, datacite.json, CITATION.cff, metadata.yaml)")
    c.add_argument("--out", "-o", help="write readiness-report.md and readiness-report.json here")
    c.add_argument("--format", choices=["summary", "markdown", "json"], default="summary")
    c.add_argument("--draft-metadata", action="append", choices=["zenodo", "datacite"],
                   help="write a draft metadata file with TODOs for unknown fields")
    c.add_argument("--write-manifest", action="store_true", help="write manifest-sha256.txt into the dataset folder")
    c.add_argument("--no-hash", action="store_true", help="skip SHA-256 hashing (faster on big data)")
    c.add_argument("--strict", action="store_true", help="exit 1 if any target fails (for CI)")
    c.add_argument("--rules-dir", help="extra folder of target YAML files")
    c.set_defaults(func=cmd_check)

    t = sub.add_parser("targets", help="list available targets and their sources")
    t.add_argument("--rules-dir")
    t.set_defaults(func=cmd_targets)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
