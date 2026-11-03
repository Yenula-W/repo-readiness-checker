"""Run data-ready on every held-out dataset and record crashes, runtime and output size.

Usage: python eval/run_heldout.py HELDOUT_DIR RESULTS_DIR
Writes RESULTS_DIR/<dataset>/readiness-report.{md,json} and RESULTS_DIR/summary.json.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

TARGETS = ["zenodo", "dryad", "figshare", "nih-dms"]


def main():
    heldout, results = Path(sys.argv[1]), Path(sys.argv[2])
    results.mkdir(parents=True, exist_ok=True)
    rows = []
    for ds in sorted(p for p in heldout.iterdir() if (p / "data").is_dir()):
        out = results / ds.name
        cmd = [sys.executable, "-m", "data_ready", "check", str(ds / "data"), "--out", str(out),
               "--format", "summary"]
        for t in TARGETS:
            cmd += ["-t", t]
        t0 = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        secs = time.perf_counter() - t0
        crashed = proc.returncode not in (0, 1) or "Traceback" in proc.stderr
        row = {"dataset": ds.name, "seconds": round(secs, 2), "exit": proc.returncode, "crashed": crashed,
               "files": sum(1 for p in (ds / "data").rglob("*") if p.is_file()),
               "bytes": sum(p.stat().st_size for p in (ds / "data").rglob("*") if p.is_file())}
        if crashed:
            row["stderr"] = proc.stderr[-2000:]
        else:
            rep = json.loads((out / "readiness-report.json").read_text())
            row["report_bytes"] = (out / "readiness-report.md").stat().st_size + (out / "readiness-report.json").stat().st_size
            row["targets"] = {t["id"]: {"status": t["status"], **t["counts"]} for t in rep["targets"]}
        rows.append(row)
        print(f"{'CRASH' if crashed else 'ok   '} {ds.name:40} {secs:6.2f}s "
              + " ".join(f"{k}={v['status']}" for k, v in row.get("targets", {}).items()))
    (results / "summary.json").write_text(json.dumps(rows, indent=1))
    print(f"\n{len(rows)} datasets, {sum(r['crashed'] for r in rows)} crashes")


if __name__ == "__main__":
    main()
