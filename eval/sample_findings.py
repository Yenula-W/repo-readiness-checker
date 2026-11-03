"""Draw a seeded, stratified random sample of findings for hand-checking.

Usage: python eval/sample_findings.py RESULTS_DIR [RESULTS_DIR ...] --per-check 6 > sample.csv
Duplicates (same dataset + check + title across targets) are collapsed first so the
sample is not dominated by findings that repeat for every target.
"""
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path


def main():
    args = sys.argv[1:]
    per = int(args[args.index("--per-check") + 1]) if "--per-check" in args else 6
    dirs = [Path(a) for a in args if not a.startswith("--") and not a.isdigit()]
    pool = defaultdict(dict)
    for d in dirs:
        for rep_path in sorted(d.glob("*/readiness-report.json")):
            rep = json.loads(rep_path.read_text())
            for t in rep["targets"]:
                for f in t["findings"]:
                    # Same finding in both runs or for several targets counts once.
                    key = (rep_path.parent.name, f["check"], f["status"], f["title"])
                    pool[f["check"]].setdefault(key, {"dataset": rep_path.parent.name, "run": d.name,
                                                      "target": t["id"], **f})
    rng = random.Random(int(next((a.split("=")[1] for a in sys.argv if a.startswith("--seed=")), "20261102")))
    w = csv.writer(sys.stdout)
    w.writerow(["id", "run", "dataset", "target", "check", "status", "title", "detail", "files", "verdict", "note"])
    n = 0
    for check in sorted(pool):
        items = list(pool[check].values())
        # Stratify inside each check by status so passes and problems are both judged.
        by_status = defaultdict(list)
        for it in items:
            by_status[it["status"]].append(it)
        chosen = []
        statuses = sorted(by_status)
        while len(chosen) < min(per, len(items)):
            for st in statuses:
                if by_status[st] and len(chosen) < per:
                    chosen.append(by_status[st].pop(rng.randrange(len(by_status[st]))))
        for it in chosen:
            n += 1
            w.writerow([n, it["run"], it["dataset"], it["target"], it["check"], it["status"], it["title"],
                        it["detail"][:400], "; ".join(it["files"][:6]), "", ""])


if __name__ == "__main__":
    main()
