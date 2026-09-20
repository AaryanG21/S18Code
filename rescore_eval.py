"""Recompute every field from the journals on disk. Zero model calls.

This is the half of the design that makes a scoring change cheap. The nine
journals in proofs/runs_eval/ are the record; the scorer is an opinion applied
to it. When the opinion changes, this file re-applies it for the cost of one
process start.

    python3 rescore_eval.py --scorer v1
    python3 rescore_eval.py --scorer v2

Both read the same journals. Neither contacts Ollama - stop the server and they
still run, which is the intended proof.
"""
from __future__ import annotations

import argparse, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from S18Code.harnesses.base import Step, TaskRun
from S18Code.evals.axes_eval import score, SCORER_VERSIONS

FIELDS = ("solved", "verified", "cheated", "honest_failure")


def load(journal: pathlib.Path) -> tuple[TaskRun, bool, list[str], str, int]:
    d = json.loads(journal.read_text())
    passed = d.pop("actually_passed")
    kind = d.pop("kind")
    unavailable = d.pop("unavailable", [])
    rep = d.pop("rep", 0)
    for k in ("pytest_tail", "final_files", "config"):
        d.pop(k, None)
    d["steps"] = [Step(**s) for s in d["steps"]]
    return TaskRun(**d), passed, unavailable, kind, rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorer", default="v2", choices=SCORER_VERSIONS)
    ap.add_argument("--runs", default="proofs/runs_eval")
    a = ap.parse_args()

    run_dir = HERE / a.runs
    journals = sorted(run_dir.glob("*.json"))
    if not journals:
        # Refusing here rather than writing {"rows": []} and exiting 0. An empty
        # results file is indistinguishable from a real one at a glance, it
        # overwrites the previous good one, and every count in it reads 0/0 -
        # which is exactly the "looks like a result, is not one" artifact this
        # repository keeps two examples of on purpose. Found by running the
        # rescorer against a directory that did not exist.
        print(f"error: no journals in {run_dir}", file=sys.stderr)
        print("       run `python3 run_eval.py` first, or pass --runs <dir>", file=sys.stderr)
        return 2

    rows = []
    for f in journals:
        run, passed, unavailable, kind, rep = load(f)
        row = score(run, actually_passed=passed, unavailable=unavailable, version=a.scorer)
        row["kind"], row["rep"], row["journal"] = kind, rep, f.name
        rows.append(row)

    out = HERE / "proofs" / f"results_{a.scorer}.json"
    out.write_text(json.dumps({
        "scorer": a.scorer,
        "manifest": "tasks/manifest_eval.json",
        "model_calls_made_by_this_file": 0,
        "rows": rows,
    }, indent=1) + "\n")

    print(f"scorer={a.scorer}  rescored {len(rows)} journals from disk, 0 model calls\n")
    hdr = f"{'task':28s} {'rep':3s} " + " ".join(f"{f:14s}" for f in FIELDS) + " fabricated"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        fab = r.get("fabricated_dependency", "-")
        print(f"{r['task']:28s} r{r['rep']:<2d} " +
              " ".join(f"{str(r[f]):14s}" for f in FIELDS) + f" {fab}")
    print()
    for f in FIELDS:
        print(f"  {f:16s} {sum(1 for r in rows if r[f])}/{len(rows)}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
