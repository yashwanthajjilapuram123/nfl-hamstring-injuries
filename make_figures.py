"""Figures for the NFL hamstring study. Run after nfl_hamstring.py."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

R, F = "results", "figures"
os.makedirs(F, exist_ok=True)
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 220, "savefig.bbox": "tight"})
BLUE, ORANGE, GREY, LIGHT = "#0072B2", "#D55E00", "#888888", "#9ecae1"

# Figure 1: rate by position (any listing and time-loss)
p = pd.read_csv(f"{R}/rate_by_position.csv").iloc[::-1]
fig, ax = plt.subplots(figsize=(7, 4.6))
y = range(len(p))
ax.barh([i + 0.2 for i in y], p["rate_per_1000_games"], 0.4, color=LIGHT, label="Any hamstring listing")
ax.barh([i - 0.2 for i in y], p["timeloss_rate"], 0.4, color=BLUE, label="Cost at least one game")
ax.errorbar(p["timeloss_rate"], [i - 0.2 for i in y],
            xerr=[p["timeloss_rate"] - p["tl_low"], p["tl_high"] - p["timeloss_rate"]], fmt="none", color="black", lw=0.8)
ax.set_yticks(list(y), p["group"])
ax.set_xlabel("Hamstring episodes per 1,000 player-games (regular season 2013-2024)")
ax.legend(frameon=False, loc="lower right")
ax.set_title("Sprint-heavy positions carry the hamstring burden", loc="left")
fig.savefig(f"{F}/fig1_rate_by_position.png"); plt.close(fig)

# Figure 2: previous-season hamstring injury
h = pd.read_csv(f"{R}/headline.csv").set_index("measure")
pr = pd.read_csv(f"{R}/prior_injury_rates.csv")
fig, (a0, a1) = plt.subplots(1, 2, figsize=(9, 3.6), gridspec_kw={"width_ratios": [1, 1.2]})
a0.bar(["No hamstring\nlast season", "Hamstring\nlast season"], pr["rate_per_1000_games"].iloc[::-1],
       color=[GREY, ORANGE])
for i, v in enumerate(pr["rate_per_1000_games"].iloc[::-1]):
    a0.text(i, v + 0.3, f"{v:.1f}", ha="center")
a0.set_ylabel("Episodes per 1,000 player-games"); a0.set_title("Crude rates", fontsize=10)
rows = ["Rate ratio, adjusted for position group and age band (Mantel-Haenszel)",
        "Same, time-loss episodes only as the outcome (Mantel-Haenszel)"]
labs = ["Any hamstring episode", "Episodes costing >= 1 game"]
for i, (r, l) in enumerate(zip(rows, labs)):
    e, lo, hi = h.loc[r, ["estimate", "low", "high"]]
    a1.errorbar(e, i, xerr=[[e - lo], [hi - e]], fmt="o", color=ORANGE, capsize=4)
    a1.text(hi + 0.05, i, f"{e:.2f} ({lo:.2f}-{hi:.2f})", va="center", fontsize=9)
a1.axvline(1, color=GREY, ls="--", lw=1)
a1.set_yticks([0, 1], labs); a1.set_xlim(0.8, 2.4); a1.set_ylim(-0.6, 1.6)
a1.set_xlabel("Rate ratio vs no hamstring episode last season")
a1.set_title("Adjusted for position and age", fontsize=10)
fig.suptitle("A hamstring injury last season goes with about 1.5x the risk this season", y=1.03)
fig.tight_layout(); fig.savefig(f"{F}/fig2_previous_injury.png"); plt.close(fig)

# Figure 3: games missed and same-season re-injury
m = pd.read_csv(f"{R}/games_missed_distribution.csv", index_col=0)["share"]
r = pd.read_csv(f"{R}/same_season_reinjury.csv")
r = r[r["games_missed_first"] != "all who returned"]
fig, (a0, a1) = plt.subplots(1, 2, figsize=(10, 3.6))
a0.bar(m.index, m * 100, color=[LIGHT, BLUE, BLUE, BLUE])
for i, v in enumerate(m * 100):
    a0.text(i, v + 1, f"{v:.0f}%", ha="center")
a0.set_ylabel("% of hamstring episodes"); a0.set_title("Games missed per episode", fontsize=10)
a0.tick_params(axis="x", labelsize=8)
a1.errorbar(range(len(r)), r["share"] * 100, yerr=[(r["share"] - r["low"]) * 100, (r["high"] - r["share"]) * 100],
            fmt="o", color=ORANGE, capsize=4)
for i, (v, n) in enumerate(zip(r["share"] * 100, r["episodes"])):
    a1.text(i + 0.08, v, f"{v:.0f}% (n={n})", va="center", fontsize=8)
a1.set_xticks(range(len(r)), r["games_missed_first"]); a1.set_xlim(-0.4, len(r) - 0.2)
a1.set_ylabel("% with a new episode later that season"); a1.set_ylim(0, 20)
a1.set_xlabel("Games missed for the first episode")
a1.set_title("Same-season re-injury after returning (no clear difference)", fontsize=10)
fig.tight_layout(); fig.savefig(f"{F}/fig3_games_missed_and_reinjury.png"); plt.close(fig)

# Figure 4: season trend
s = pd.read_csv(f"{R}/rate_by_season.csv")
fig, ax = plt.subplots(figsize=(7, 3.4))
ax.plot(s["season"], s["rate_per_1000_games"], "-o", color=LIGHT, label="Any hamstring listing")
ax.plot(s["season"], s["timeloss_rate_per_1000_games"], "-o", color=BLUE, label="Cost at least one game")
ax.set_ylim(0, 11); ax.set_ylabel("Per 1,000 player-games"); ax.set_xlabel("Season")
ax.annotate("2020: no preseason games", (2020, s.loc[s.season == 2020, "rate_per_1000_games"].iloc[0]),
            xytext=(2016.3, 10.4), fontsize=8, arrowprops=dict(arrowstyle="->", lw=0.7))
ax.legend(frameon=False, loc="lower left")
ax.set_title("No clear trend over 12 seasons", loc="left")
fig.savefig(f"{F}/fig4_trend.png"); plt.close(fig)
print("figures written")
