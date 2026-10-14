import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


IN_CSV    = r"D:\new_k8s_analysis\pe_per_month.csv"
OUT_PNG   = r"D:\new_k8s_analysis\obj_per_month.png"
OUT_PDF   = r"D:\new_k8s_analysis\obj_per_month.pdf"
PCT_COLUMN  = "PEPerMonth_pct"
N_COLS      = 5
YMAX        = 50
LOWESS_FRAC = 0.5
TICK_COLOR  = "black"
LABEL_EVERY = 6

ORDER = ["Autoscaler","ConfigMap","CustomResourceDefinition","DaemonSet",
         "Deployment","Ingress","LimitRange","Namespace","NetworkPolicy",
         "PersistentVolume","PersistentVolumeClaim","Pod","ReplicaSet",
         "Secret","Service","StatefulSet",
         "Node affinity","Pod anti-affinity","Taints"]
CSV_NAME = {"Node affinity":"Node Affinity",
            "Pod anti-affinity":"Pod Anti-Affinity",
            "Taints":"Taints"}

PALETTE = ["#1f77b4","#17becf","#ff7f0e","#2ca02c","#9467bd","#bcbd22",
           "#3b3b6d","#7f7f4f","#8c6d31","#1f9e89","#2c8c5a","#6a51a3",
           "#7f7f7f","#d4a017","#2ca25f","#756bb1","#2b8cbe","#b58900",
           "#4f9d9d","#444444"]



def lowess(x, y, frac=0.5):
    x = np.asarray(x, float); y = np.asarray(y, float)
    n = len(x)
    if n < 3:
        return x, y
    r = max(int(np.ceil(frac*n)), 3)
    out = np.empty(n)
    for i in range(n):
        d = np.abs(x - x[i])
        h = np.sort(d)[min(r, n-1)]; h = h if h > 0 else 1.0
        w = np.clip(d/h, 0, 1); w = (1-w**3)**3
        A = np.array([[np.sum(w), np.sum(w*x)],
                      [np.sum(w*x), np.sum(w*x*x)]])
        beta = np.array([np.sum(w*y), np.sum(w*x*y)])
        try:
            sol = np.linalg.solve(A, beta); out[i] = sol[0] + sol[1]*x[i]
        except np.linalg.LinAlgError:
            out[i] = np.sum(w*y)/np.sum(w)
    return x, out
df = pd.read_csv(IN_CSV)
months = sorted(df["Month"].unique())
midx = {m: i for i, m in enumerate(months)}
M = len(months)
om = df.groupby("Month")["ObjectTotal_t"].first()
tot_all = om.sum()


def series_for(name):
    csv_name = CSV_NAME.get(name, name)
    s = df[df["PE"] == csv_name].dropna(subset=[PCT_COLUMN])
    xs = np.array([midx[m] for m in s["Month"]]); ys = s[PCT_COLUMN].to_numpy()
    o = np.argsort(xs); return xs[o], ys[o]


tot_x = np.array([midx[m] for m in om.index])
tot_y = (om / tot_all * 100).to_numpy()
o = np.argsort(tot_x); tot_x, tot_y = tot_x[o], tot_y[o]

panels = list(ORDER) + ["Total"]

n = len(panels)
n_rows = int(np.ceil(n/N_COLS))
fig, axes = plt.subplots(n_rows, N_COLS, figsize=(3.0*N_COLS, 2.5*n_rows))
axes = np.atleast_2d(axes).ravel()

maj_idx = [i for i in range(M) if i % LABEL_EVERY == 0]
maj_lab = [months[i][2:] for i in maj_idx]

for k, name in enumerate(panels):
    ax = axes[k]; color = PALETTE[k % len(PALETTE)]; is_total = (name == "Total")
    x, y = (tot_x, tot_y) if is_total else series_for(name)

    ax.set_facecolor("#eaeaea")
    ax.grid(True, color="white", linewidth=0.8, zorder=0); ax.set_axisbelow(True)
    for s in ax.spines.values(): s.set_visible(False)

    if len(x):
        ax.scatter(x, y, s=14, color=color, alpha=0.5, zorder=2, edgecolors="none")
        if len(x) >= 3:
            lx, lf = lowess(x, y, LOWESS_FRAC)
            _, band = lowess(x, np.abs(y-lf), LOWESS_FRAC); band = np.clip(band,0,None)
            ax.fill_between(lx, np.clip(lf-band,0,None), lf+band, color=color, alpha=0.20, zorder=1)
            ax.plot(lx, lf, color=color, linewidth=2.8, zorder=3,
                    solid_capstyle="round")

    ax.add_patch(Rectangle((0,1.0),1,0.11, transform=ax.transAxes, clip_on=False,
                 facecolor="#d6d6d6", edgecolor="#b3b3b3", linewidth=0.6, zorder=4))
    ax.text(0.5, 1.055, name, transform=ax.transAxes, ha="center", va="center",
            fontsize=8.5, zorder=5)

    ax.set_xlim(-1, M)
    if not is_total:
        ax.set_ylim(0, YMAX if YMAX else None)
    else:
        ax.set_ylim(0, float(np.nanmax(tot_y))*1.12 if len(tot_y) else 1)

    ax.set_xticks(range(M), minor=True)
    ax.set_xticks(maj_idx)
    ax.set_xticklabels(maj_lab, rotation=45, ha="right", fontsize=6.5, color=TICK_COLOR)
    ax.tick_params(axis="x", which="major", length=4, color=TICK_COLOR)
    ax.tick_params(axis="x", which="minor", length=2, color=TICK_COLOR)
    ax.tick_params(axis="y", labelsize=7, color=TICK_COLOR)
    if k % N_COLS == 0:
        ax.set_ylabel("PE per month", fontsize=9)

for j in range(n, len(axes)): axes[j].axis("off")

fig.tight_layout(h_pad=2.2, w_pad=1.0)
fig.savefig(OUT_PNG, dpi=170, bbox_inches="tight")
fig.savefig(OUT_PDF, bbox_inches="tight")
print("panels:", panels)
print("months:", M, months[0], "->", months[-1])
print("saved", OUT_PNG)
