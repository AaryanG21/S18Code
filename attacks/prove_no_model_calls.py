"""Prove that rescoring contacts no model, instead of claiming it.

"Zero model calls" is the property that makes a scoring change cheap, so it is
worth more than a sentence in a README.

The first version of this raised inside a severed socket and called the run
proven if nothing propagated. A negative control on 2026-09-23 broke it: plant
`try: urlopen(...) except Exception: pass` in the rescorer and the "proof"
still printed PROVEN, because the code under test swallowed the evidence. A
proof the code under test can silence is not a proof.

So now every connection attempt is RECORDED in a list the code under test
never sees, and the verdict reads the list afterwards. Swallowing the exception
no longer hides the attempt. And the negative control is built in: before the
real check, this plants exactly that swallowed call and requires the recorder
to catch it. If it cannot catch a planted call, it refuses to vouch for the
real one.

The second version still passed a rescorer with a planted network call in it,
with a detector shown to work - which meant the call never ran. Neither did
anything else. Both versions loaded rescore_eval.py under a module name that is
not "__main__", so its `if __name__ == "__main__"` guard skipped main() and NO
RESCORING HAPPENED. From the first commit until 2026-09-23 this file proved only
that importing the rescorer opens no sockets. Caught by backdating the results
files and seeing that the "proof" never touched them.

So it now calls main() explicitly and checks its own subject ran: each results
file must be rewritten during the check and must hold one row per journal. A
proof that does not verify the thing it describes actually happened is the
same defect as a test suite that never collects.
"""
from __future__ import annotations

import importlib.util, pathlib, socket, sys

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))

ATTEMPTS: list[str] = []


class RecordingSeveredSocket:
    def __init__(self, *a, **k):
        ATTEMPTS.append(f"socket.socket{a[:2]}")
        raise OSError("network severed by prove_no_model_calls")


def _create_connection(address, *a, **k):
    ATTEMPTS.append(f"create_connection{address}")
    raise OSError("network severed by prove_no_model_calls")


socket.socket = RecordingSeveredSocket
socket.create_connection = _create_connection


def _run_rescore(version: str) -> None:
    spec = importlib.util.spec_from_file_location(f"rescore_{version}", HERE / "rescore_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)            # defines main(); runs nothing
    sys.argv = ["rescore_eval.py", "--scorer", version]
    out = HERE / "proofs" / f"results_{version}.json"
    before = out.stat().st_mtime_ns if out.exists() else -1
    code = mod.main()                       # the call both earlier versions never made
    if code not in (0, None):
        raise RuntimeError(f"rescore --scorer {version} returned {code}")

    # Did the thing we are vouching for actually happen?
    import json
    if not out.exists() or out.stat().st_mtime_ns == before:
        raise RuntimeError(f"{out.name} was not rewritten - the rescorer did not run")
    journals = len(list((HERE / "proofs" / "runs_eval").glob("*.json")))
    rows = len(json.loads(out.read_text())["rows"])
    if rows != journals or journals == 0:
        raise RuntimeError(f"{out.name} holds {rows} rows for {journals} journals")
    print(f"  {version}: rescored {rows}/{journals} journals, {out.name} rewritten")


# ---- negative control: a swallowed call MUST be caught, or nothing is proven
ATTEMPTS.clear()
try:
    import urllib.request
    urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
except Exception:
    pass                       # exactly how a careless "best effort" call hides
if not ATTEMPTS:
    print("CONTROL FAILED: a planted, swallowed network call went unrecorded.")
    print("This check cannot see the thing it claims to rule out. Not vouching.")
    raise SystemExit(2)
print(f"  control: planted swallowed call was recorded ({ATTEMPTS[0]}) - detector works")

# ---- the real check
ATTEMPTS.clear()
for version in ("v1", "v2"):
    _run_rescore(version)

if ATTEMPTS:
    print(f"\nFAILED: rescoring attempted {len(ATTEMPTS)} connection(s): {ATTEMPTS}")
    raise SystemExit(1)
print("\nPROVEN: both scorers ran with 0 connection attempts, by a detector shown to catch one.")
