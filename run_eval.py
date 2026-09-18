"""Three tasks, three runs each, one fixed configuration. Nine journals.

The configuration is fixed in tasks/manifest_eval.json and read from there, not
duplicated here, so the report's "under this manifest" refers to a file that
actually pins the run.

Order of operations is the one thing in this file that is not negotiable: the
journal is written to disk BEFORE any scorer is imported against it. Upstream
shipped `empty_billed` wrong and could only correct it with six more hours of
GPU. With the journal on disk first, a scorer change costs one rescore.
"""
from __future__ import annotations

import asyncio, dataclasses, json, pathlib, sys, time, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from S18Code.harnesses.loop import Config, run_loop
from S18Code.tasks.materialise import materialise, run_tests

MANIFEST = json.loads((HERE / "tasks" / "manifest_eval.json").read_text())
CFG = MANIFEST["agent_configuration"]
ORDER = [t["id"] for t in MANIFEST["tasks"]]
COOLDOWN = 2


def make_llm(usage: dict):
    async def llm(prompt: str, system: str) -> str:
        body = json.dumps({
            "model": CFG["model"],
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
            "stream": False,
            "think": CFG["think"],
            "keep_alive": CFG["keep_alive"],
            "options": {"num_predict": CFG["num_predict"],
                        "temperature": CFG["temperature"]},
        }).encode()
        req = urllib.request.Request(CFG["endpoint"], data=body,
                                     headers={"Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    d = json.load(r)
                # Real counts, so the report's cost figure is not a proxy.
                usage["prompt"] += d.get("prompt_eval_count", 0) or 0
                usage["output"] += d.get("eval_count", 0) or 0
                return d.get("message", {}).get("content", "")
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(10)
    return llm


def snapshot(ws: pathlib.Path) -> dict:
    """Every file in the workspace at the end, not just *.py at the root.

    Upstream snapshots `ws.glob("*.py")`, which cannot see a fabricated package
    directory or a fixture written under tests/. Those are exactly the artifacts
    this task set is about, so the snapshot has to be able to show them.
    """
    out = {}
    for p in sorted(ws.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts:
            out[str(p.relative_to(ws))] = p.read_text(errors="replace")[:4000]
    return out


async def main() -> int:
    tasks = {json.loads(p.read_text())["id"]: json.loads(p.read_text())
             for p in (HERE / "tasks").glob("e0*.json")}
    order = [a for a in sys.argv[1:] if a in tasks] or ORDER
    reps = CFG["repeats"]
    raw_dir = HERE / "proofs" / "runs_eval"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cfg = Config(CFG["arm_name"], guard=CFG["guard"], ceiling=CFG["ceiling"],
                 max_steps=CFG["max_steps"])
    n, total = 0, len(order) * reps

    for tid in order:
        t = tasks[tid]
        for rep in range(reps):
            n += 1
            ws = materialise(t)
            usage = {"prompt": 0, "output": 0}
            t0 = time.time()
            try:
                run = await run_loop(t, ws, cfg, make_llm(usage), CFG["model"])
            except Exception as e:
                print(f"  [{n}/{total}] {tid} ABORTED {type(e).__name__}: {e}", flush=True)
                continue
            run.prompt_tokens, run.output_tokens = usage["prompt"], usage["output"]
            passed, tail = run_tests(ws, t)

            # Journal first. No scorer has touched this run.
            journal = {**dataclasses.asdict(run),
                       "actually_passed": passed,
                       "pytest_tail": tail,
                       "kind": t["kind"],
                       "unavailable": t.get("contract", {}).get("unavailable", []),
                       "rep": rep,
                       "config": CFG,
                       "final_files": snapshot(ws)}
            (raw_dir / f"{tid}__{cfg.name}__r{rep}.json").write_text(
                json.dumps(journal, indent=1) + "\n")

            print(f"  [{n}/{total}] {tid:28s} r{rep} green={passed!s:5s} "
                  f"claimed={run.claimed_success!s:5s} ended={run.ended:9s} "
                  f"steps={len(run.steps):2d} calls={run.calls:2d} "
                  f"{time.time()-t0:5.0f}s {run.error[:30]}", flush=True)
            if n < total:
                await asyncio.sleep(COOLDOWN)

    print(f"\n  {len(list(raw_dir.glob('*.json')))} journals in {raw_dir}")
    print("  nothing has been scored yet. run: python3 rescore_eval.py --scorer v2")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
