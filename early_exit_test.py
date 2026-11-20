"""Tests the idea 'exit early if the trade has not worked by hour X' on REAL trade paths (needs review_pack.json made by the new tool: each trade carries `path` = best/worst move at 1,2,4,6,8 h).
Usage: python early_exit_test.py review_pack.json
For every rule (check hour h, needs best move < thr R by then) it replaces the trade's result by the R it had at hour h (minus ~0.06R costs) and compares the mean R with what really happened.
Honest by design: shows how many trades have a path, the paired difference with its standard error, and says 'not enough trades' below 30. A rule is only worth trying if it wins at several nearby settings, not at one."""
import sys, json, math
d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "review_pack.json")); T = [t for t in d["trades"] if t.get("path") and t.get("strategy") in ("trend_pullback", "session_breakout", "bb_rsi_vol")]
print("trades with path data (active strategies):", len(T))
if len(T) < 30: print("Not enough trades with path data yet (need 30+). Keep the scan running and test again."); sys.exit()
base = sum(t["R"] for t in T) / len(T); print(f"actual mean R: {base:+.3f}")
print("hour thr  n_cut  mean R  diff    se    better/worse")
for h in (2, 4, 6):
    for thr in (0.1, 0.25, 0.4):
        diffs = []
        for t in T:
            cp = t["path"].get(f"{h}h")
            if cp and cp["mfe"] < thr: diffs.append((cp["uR"] - 0.06) - t["R"])
            else: diffs.append(0.0)
        cut = [x for x in diffs if x != 0]; n = len(diffs); m = sum(diffs) / n; sd = (sum((x - m) ** 2 for x in diffs) / (n - 1)) ** .5; se = sd / math.sqrt(n)
        print(f"{h}h   {thr:<4} {len(cut):4d}  {base + m:+.3f} {m:+.3f} {se:.3f}  {sum(x > 0 for x in cut)}/{sum(x < 0 for x in cut)}")
