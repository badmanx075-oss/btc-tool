"""Crash-safe JSON files. A run can be killed at any moment (timeout, cancel, runner loss). Writing straight into state.json then leaves a HALF-WRITTEN file,
which the Save-state step used to commit and which made every later scan crash. Here: write to a temp file, then atomically replace; and load() falls back to the
last valid copy in git history if the file on disk is ever broken."""
import os, json, subprocess


def dump(obj, path, **kw):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f, **kw); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def load(path, default=None, history=6):
    """Valid JSON from disk; if broken, the newest valid committed copy (git show HEAD, HEAD~1 ...); else default."""
    try: return json.load(open(path))
    except FileNotFoundError: return default
    except Exception as e: print("CORRUPT", path, type(e).__name__, "-> trying git history")
    for k in range(history):
        try:
            r = subprocess.run(["git", "show", "HEAD" + (f"~{k}" if k else "") + ":" + path], capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                d = json.loads(r.stdout); print("RECOVERED", path, "from git history, steps back:", k); return d
        except Exception: continue
    return default
