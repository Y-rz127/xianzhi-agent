"""共振四项 term 的无标签结构诊断（共振权重体检的第一道）。

不需要任何事件标注：快照 `years` 里存的就是**加权后贡献值**、`resonance`
是总分 ⇒ 可直接算各 term 对总分的贡献 stdev 与相关性。

判据是**相关性**，不是均值 —— 这四项都是双向修正项，均值本就该近零；
均值近零只说明"它是修正项"，不说明它没用。

用法：cd backend && ../.venv/Scripts/python.exe scripts/kline_term_diag.py
"""
import glob
import json
import os
import statistics as st

UNITS = {"trend": 8.0, "align": 10.0, "sync": 3.0, "palace": 5.0}
TERMS = ("trend", "align", "sync", "palace")
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root = os.path.join(BACKEND, "tests", "fixtures", "kline_resonance")
files = sorted(glob.glob(os.path.join(root, "*.json")))

per_pair = {}
tot_sd = {t: [] for t in TERMS}
corr = {t: [] for t in TERMS}

for f in files:
    d = json.load(open(f, encoding="utf-8"))
    ys = d["years"]
    ids = [c["id"] for c in d["cases"]]
    name = os.path.basename(f).replace(".json", "")
    tot = [float(x) for x in ys["resonance"].split(",") if x]
    if not tot:
        continue
    s_ = st.pstdev(tot)
    row = {}
    for t in TERMS:
        v = [float(x) for x in ys[t].split(",") if x]
        n = min(len(v), len(tot))
        v2, t2 = v[:n], tot[:n]
        sd = st.pstdev(v2)
        tot_sd[t].append(sd)
        if s_ > 1e-9 and sd > 1e-9:
            mv, mt = st.mean(v2), st.mean(t2)
            cov = sum((a - mv) * (b - mt) for a, b in zip(v2, t2)) / len(v2)
            c = cov / (sd * s_)
        else:
            c = float("nan")
        corr[t].append(c)
        row[t] = (sd, c, len(set(v2)))
    per_pair[name] = (row, ids[0] == ids[1])

print(f"对数 {len(files)}\n")
print(f"{'term':8} {'unit':>5} {'stdev均值':>9} {'corr均值':>9} {'主导度范围':>18}")
for t in TERMS:
    cs = [c for c in corr[t] if c == c]
    lo, hi = min(cs), max(cs)
    flag = ""
    if len(cs) and hi - lo > 0.5:
        flag = "  <- 主导度跨盘差异大"
    print(f"{t:8} {UNITS[t]:5.1f} {st.mean(tot_sd[t]):9.2f} {st.mean(cs):9.3f} "
          f"{lo:8.2f}~{hi:<8.2f}{flag}")

print(f"\n{'pair':46} " + " ".join(f"{t:>14}" for t in TERMS))
for name, (row, is_self) in per_pair.items():
    cells = " ".join(f"{row[t][1]:+6.2f}/{row[t][2]:>2}u" for t in TERMS)
    print(f"{name:46} {cells}{'  SELF' if is_self else ''}")

print("\n(stdev/不同取值个数)")
