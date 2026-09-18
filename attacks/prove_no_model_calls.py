"""Prove that rescoring contacts no model, instead of claiming it.

"Zero model calls" is the property that makes a scoring change cheap, so it is
worth more than a sentence in a README. This severs the socket layer outright
and then runs both scorers over the nine journals. If anything tried to reach
Ollama - or anywhere else - it would raise here, loudly, instead of quietly
succeeding because the server happened to be running.
"""
from __future__ import annotations

import pathlib, socket, subprocess, sys


class SeveredSocket:
    def __init__(self, *a, **k):
        raise AssertionError("a rescore attempted a network connection")


socket.socket = SeveredSocket
socket.create_connection = lambda *a, **k: SeveredSocket()

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent))
sys.argv = ["rescore_eval.py"]

import importlib.util

ok = True
for version in ("v1", "v2"):
    spec = importlib.util.spec_from_file_location(f"rescore_{version}", HERE / "rescore_eval.py")
    mod = importlib.util.module_from_spec(spec)
    sys.argv = ["rescore_eval.py", "--scorer", version]
    try:
        spec.loader.exec_module(mod)
    except SystemExit as e:
        if e.code not in (0, None):
            ok = False
            print(f"  {version}: EXIT {e.code}")
            continue
    except AssertionError as e:
        ok = False
        print(f"  {version}: FAILED - {e}")
        continue
    print(f"  {version}: completed with the socket layer severed")

print("\nPROVEN: both scorers ran to completion with no network available."
      if ok else "\nFAILED: a scorer touched the network.")
raise SystemExit(0 if ok else 1)
