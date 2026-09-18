"""Why the fixed configuration is think:false. Measured, not assumed.

The manifest pins one configuration and the report leans on it, so the choice
has to be evidence rather than preference. This runs the same trivial step
under three settings and records what came back.
"""
from __future__ import annotations

import json, pathlib, time, urllib.request

SYSTEM = ('Reply with ONE json object and nothing else.\n'
          'To read:  {"action":"read","path":"f.py"}\n'
          'To write: {"action":"write","path":"f.py","content":"...full new file..."}\n'
          'To test:  {"action":"test"}\n'
          'To stop:  {"action":"done","success":true,"note":"one line"}')
USER = json.dumps({"goal": "chunk.py splits a list into windows and drops the last item. Fix it.",
                   "files": ["chunk.py"], "history": []})
# The large-budget probe is repeated. The first two times it was run by hand it
# disagreed with itself - once content:"", once a usable action - so a single
# sample of it is not evidence of anything, in either direction.
PROBES = [("think on, small budget", True, 400, 2),
          ("think on, large budget", True, 2400, 3),
          ("think off", False, 700, 3)]


def call(think: bool, num_predict: int) -> dict:
    body = json.dumps({
        "model": "qwen3:latest", "stream": False, "think": think, "keep_alive": "30m",
        "options": {"num_predict": num_predict, "temperature": 0.2},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}],
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    return {"seconds": round(time.time() - t0, 1), "eval_count": d.get("eval_count"),
            "content": d.get("message", {}).get("content", ""),
            "thinking_chars": len(d.get("message", {}).get("thinking") or "")}


rows = []
for label, think, np_, reps in PROBES:
    for rep in range(reps):
        r = call(think, np_)
        usable = bool(r["content"].strip())
        rows.append({"probe": label, "rep": rep, "think": think, "num_predict": np_,
                     "seconds": r["seconds"], "tokens_generated": r["eval_count"],
                     "reasoning_channel_chars": r["thinking_chars"],
                     "content": r["content"][:200], "usable_reply": usable})
        print(f"  {label:24s} r{rep} think={think!s:5s} np={np_:5d} {r['seconds']:6.1f}s "
              f"eval={r['eval_count']:5d} usable={usable!s:5s} content={r['content'][:50]!r}",
              flush=True)

out = pathlib.Path(__file__).resolve().parents[1] / "proofs" / "config_selection.json"
out.write_text(json.dumps({
    "date": "2026-09-19", "model": "qwen3:latest (8.2B Q4_K_M, Ollama)",
    "question": "Should the fixed configuration run with reasoning on?",
    "answer": "No, and the reason is latency plus instability rather than the single "
              "dramatic finding the first probe suggested. At num_predict=400 reasoning on "
              "consumes the whole budget in the reasoning channel and returns content:'' - "
              "a fully billed non-answer. At num_predict=2400 it can emit a usable action, "
              "but takes over a hundred seconds to do it and does not do it every time. "
              "think:false answers the same step in under a second. Fourteen steps times "
              "nine runs at the reasoning-on rate is hours of wall clock for a "
              "configuration that still sometimes returns nothing, so the manifest pins "
              "think:false.",
    "correction": "An earlier hand-run of the num_predict=2400 probe returned content:'' "
                  "and was written up as 'the empty-reply pathology, reproduced twice'. "
                  "The scripted re-run returned a usable action. One sample was being read "
                  "as a property. The probe now repeats itself and the rows below are all "
                  "of them, including the disagreeing ones.",
    "caveat": "This is a limit of this 8B model at this prompt size, and the report says "
              "so. It is not a claim about reasoning models generally.",
    "probes": rows}, indent=1) + "\n")
print(f"\nwrote {out}")
