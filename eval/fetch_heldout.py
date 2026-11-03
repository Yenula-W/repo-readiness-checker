"""Download the held-out evaluation datasets listed in heldout.json.

Usage: python -I eval/fetch_heldout.py eval/heldout.json OUT_DIR [--max-file-mb 300]

Each dataset lands in OUT_DIR/<source>_<id>/data/, with the repository's own
record saved next to it as record.json (never inside data/). Stdlib only.
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "data-ready-evaluation/0.1 (research software testing)"}


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def download(url, dest: Path, max_bytes: int, log):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        size = int(r.headers.get("Content-Length") or 0)
        if size > max_bytes:
            log.append(f"SKIPPED (too big, {size} B): {dest.name}")
            return
        with dest.open("wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)


def safe(name):
    # Keep the real file name (that is what we are testing) but block path traversal.
    name = name.replace("\\", "/").split("/")[-1]
    return name if name not in ("", ".", "..") else "_"


def zenodo(rid, out, max_b, log):
    rec = get_json(f"https://zenodo.org/api/records/{rid}")
    for f in rec.get("files", []):
        download(f["links"]["self"], out / "data" / safe(f["key"]), max_b, log)
    return rec


def figshare(aid, out, max_b, log):
    rec = get_json(f"https://api.figshare.com/v2/articles/{aid}")
    for f in rec.get("files", []):
        download(f["download_url"], out / "data" / safe(f["name"]), max_b, log)
    return rec


def dataverse(pid, out, max_b, log):
    base = "https://dataverse.harvard.edu/api"
    rec = get_json(f"{base}/datasets/:persistentId/?persistentId={urllib.parse.quote(pid)}")
    for f in rec["data"]["latestVersion"].get("files", []):
        df = f["dataFile"]
        if f.get("restricted"):
            log.append(f"SKIPPED (restricted): {df['filename']}")
            continue
        name = df.get("originalFileName") or df["filename"]
        folder = f.get("directoryLabel", "")
        dest = out / "data" / folder / safe(name) if folder else out / "data" / safe(name)
        download(f"{base}/access/datafile/{df['id']}?format=original", dest, max_b, log)
    return rec


def osf(nid, out, max_b, log):
    rec = get_json(f"https://api.osf.io/v2/nodes/{nid}/")

    def walk(url, rel):
        while url:
            page = get_json(url)
            for item in page["data"]:
                a = item["attributes"]
                if a["kind"] == "folder":
                    walk(item["relationships"]["files"]["links"]["related"]["href"], rel / safe(a["name"]))
                else:
                    download(item["links"]["download"], out / "data" / rel / safe(a["name"]), max_b, log)
            url = page["links"].get("next")

    walk(f"https://api.osf.io/v2/nodes/{nid}/files/osfstorage/", Path())
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("listing")
    ap.add_argument("out")
    ap.add_argument("--max-file-mb", type=float, default=300)
    args = ap.parse_args()
    items = json.loads(Path(args.listing).read_text())
    for it in items:
        key = f"{it['source']}_{re.sub(r'[^A-Za-z0-9]+', '_', it['id'])}"
        out = Path(args.out) / key
        if (out / "record.json").exists():
            print(f"have {key}")
            continue
        log = []
        try:
            rec = globals()[it["source"]](it["id"], out, int(args.max_file_mb * 1e6), log)
            (out / "record.json").write_text(json.dumps(rec, indent=1))
            (out / "fetch.log").write_text("\n".join(log))
            print(f"ok   {key} {len(list((out / 'data').rglob('*')))} entries {'; '.join(log)}")
        except Exception as e:
            print(f"FAIL {key}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
