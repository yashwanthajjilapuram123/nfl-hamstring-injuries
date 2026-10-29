"""Hamstring injuries in the NFL, 2013-2024: exposure-based rates, time lost and
the risk that follows a previous hamstring injury.

Data (public, nflverse; downloaded by get_data.sh):
  * weekly official injury reports (teams must file them), 2009-2025
  * snap counts per player per game (Pro Football Reference via nflverse), 2013-2025
  * player register (ID crosswalk, position, birth date)

Analysis window: regular seasons 2013-2024 (complete seasons with snap counts).
Every number in the README is produced by this script.
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

DATA, OUT = "data", "results"
FIRST, LAST = 2013, 2024
SEED, N_BOOT = 2026, 1000
INJ_COLS = ["report_primary_injury", "report_secondary_injury",
            "practice_primary_injury", "practice_secondary_injury"]

POS_GROUP = {"WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB", "QB": "QB",
             "T": "OL", "G": "OL", "C": "OL", "OL": "OL", "OT": "OL", "OG": "OL",
             "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL",
             "LB": "LB", "OLB": "LB", "ILB": "LB", "MLB": "LB",
             "CB": "CB", "DB": "CB", "S": "S", "FS": "S", "SS": "S", "SAF": "S",
             "K": "K/P/LS", "P": "K/P/LS", "LS": "K/P/LS"}
GROUP_ORDER = ["WR", "CB", "S", "RB", "TE", "LB", "DL", "OL", "QB", "K/P/LS"]


def week_key(season, week):
    """Chronological key: season * 100 + week (postseason weeks continue the count)."""
    return season * 100 + week


# --------------------------------------------------------------------------- load
def load():
    inj = pd.concat([pd.read_csv(f, low_memory=False) for f in sorted(glob.glob(f"{DATA}/injuries_*.csv"))],
                    ignore_index=True)
    inj["hamstring"] = inj[INJ_COLS].astype(str).apply(lambda c: c.str.contains("hamstring", case=False)).any(axis=1)
    snaps = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{DATA}/snap_counts_*.csv"))], ignore_index=True)
    snaps = snaps.dropna(subset=["pfr_player_id"])
    snaps["snaps"] = snaps[["offense_snaps", "defense_snaps", "st_snaps"]].fillna(0).sum(axis=1)
    snaps["k"] = week_key(snaps["season"], snaps["week"])
    players = pd.read_csv(f"{DATA}/players.csv", low_memory=False)[["gsis_id", "pfr_id", "birth_date", "display_name"]]
    return inj, snaps, players


# ----------------------------------------------------------------------- episodes
def build_episodes(inj, snaps, players):
    """Group weekly hamstring listings into episodes.

    A listing starts a NEW episode if, since the player's previous hamstring
    listing, he played (snaps > 0) in at least one game in a week in which he was
    not listed with a hamstring injury. Otherwise the listing continues the
    current episode (this keeps players who sat out, or were moved to injured
    reserve and later re-listed, in one episode).
    """
    h = inj[inj["hamstring"]].merge(players[["gsis_id", "pfr_id"]], on="gsis_id", how="left")
    h = h.dropna(subset=["pfr_id"])
    h["k"] = week_key(h["season"], h["week"])
    h = h.sort_values(["pfr_id", "k"]).drop_duplicates(["pfr_id", "k"])
    played = snaps[snaps["snaps"] > 0][["pfr_player_id", "k"]]
    played_by_player = {p: np.sort(g["k"].to_numpy()) for p, g in played.groupby("pfr_player_id")}
    listed_by_player = {p: set(g["k"]) for p, g in h.groupby("pfr_id")}

    rows = []
    for pid, g in h.groupby("pfr_id"):
        pk = played_by_player.get(pid, np.array([], dtype=int))
        listed = listed_by_player[pid]
        cur = None
        for r in g.itertuples():
            if cur is not None:
                between = pk[(pk > cur["last_k"]) & (pk < r.k)]
                played_between = any(k not in listed for k in between)
                if not played_between:
                    cur["last_k"] = r.k
                    cur["n_listings"] += 1
                    continue
                rows.append(cur)
            cur = {"pfr_id": pid, "gsis_id": r.gsis_id, "name": r.full_name, "team": r.team,
                   "position": r.position, "season": r.season, "week": r.week,
                   "game_type": r.game_type, "onset_k": r.k, "last_k": r.k, "n_listings": 1}
        rows.append(cur)
    return pd.DataFrame(rows)


def games_missed(ep, snaps):
    """Team games from the onset week onwards in which the player had no snaps,
    until he next played. Counted within the same season (regular + postseason);
    'season_ended' marks episodes where he did not play again that season."""
    team_games = snaps[["season", "team", "k"]].drop_duplicates()
    tg = {key: np.sort(g["k"].to_numpy()) for key, g in team_games.groupby(["season", "team"])}
    played = snaps[snaps["snaps"] > 0]
    pk = {p: np.sort(g["k"].to_numpy()) for p, g in played.groupby("pfr_player_id")}
    missed, ended = [], []
    for r in ep.itertuples():
        games = tg.get((r.season, r.team), np.array([], dtype=int))
        games = games[games >= r.onset_k]
        pp = pk.get(r.pfr_id, np.array([], dtype=int))
        nxt = pp[(pp >= r.onset_k) & (pp < (r.season + 1) * 100)]
        if len(nxt):
            missed.append(int((games < nxt[0]).sum()))
            ended.append(False)
        else:
            missed.append(int(len(games)))
            ended.append(True)
    ep = ep.copy()
    ep["games_missed"], ep["season_ended"] = missed, ended
    return ep


# ----------------------------------------------------------------------- exposure
def exposure(snaps, players):
    reg = snaps[(snaps["game_type"] == "REG") & (snaps["snaps"] > 0) & snaps["season"].between(FIRST - 1, LAST)]
    pos = (reg.groupby(["pfr_player_id", "season"])["position"]
           .agg(lambda s: s.value_counts().index[0]).rename("position"))
    ps = reg.groupby(["pfr_player_id", "season"]).size().rename("games").to_frame().join(pos).reset_index()
    ps["group"] = ps["position"].map(POS_GROUP).fillna("Other")
    b = players.dropna(subset=["pfr_id"]).drop_duplicates("pfr_id").set_index("pfr_id")["birth_date"]
    ps["birth"] = pd.to_datetime(ps["pfr_player_id"].map(b), errors="coerce")
    ps["age"] = (pd.to_datetime(ps["season"].astype(str) + "-09-01") - ps["birth"]).dt.days / 365.25
    ps["age_band"] = pd.cut(ps["age"], [0, 25, 28, 31, 60], labels=["<25", "25-27", "28-30", "31+"], right=False)
    return ps


# ------------------------------------------------------------------ statistics
def mh_rate_ratio(df, exposed, events="events", time="games", strata="stratum"):
    """Mantel-Haenszel rate ratio across strata."""
    num = den = 0.0
    for _, g in df.groupby(strata, observed=True):
        T = g[time].sum()
        if T == 0:
            continue
        a = g.loc[g[exposed], events].sum(); t1 = g.loc[g[exposed], time].sum()
        b = g.loc[~g[exposed], events].sum(); t0 = g.loc[~g[exposed], time].sum()
        num += a * t0 / T
        den += b * t1 / T
    return num / den if den else np.nan


def boot_weights(df, n=N_BOOT, seed=SEED, cluster="pfr_player_id"):
    """Player-cluster bootstrap: for each replicate, how many times each row's
    player was drawn (rows of the same player share the weight)."""
    codes, uniq = pd.factorize(df[cluster])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(uniq), size=(n, len(uniq)))
    counts = np.stack([np.bincount(d, minlength=len(uniq)) for d in draws])
    return counts[:, codes]                     # shape (n, rows)


def boot_rate(df, n=N_BOOT):
    w = boot_weights(df, n)
    e, g = df["events"].to_numpy(float), df["games"].to_numpy(float)
    vals = 1000 * (w @ e) / (w @ g)
    return np.percentile(vals, [2.5, 97.5])


def boot_mh(df, exposed="prior", strata="stratum", n=N_BOOT):
    w = boot_weights(df, n)
    sc, _ = pd.factorize(df[strata].astype(str).fillna("missing"))
    x = df[exposed].to_numpy(bool)
    e, g = df["events"].to_numpy(float), df["games"].to_numpy(float)
    vals = []
    for wi in w:
        a = np.bincount(sc, wi * e * x); t1 = np.bincount(sc, wi * g * x)
        b = np.bincount(sc, wi * e * ~x); t0 = np.bincount(sc, wi * g * ~x)
        T = t1 + t0
        ok = T > 0
        vals.append((a[ok] * t0[ok] / T[ok]).sum() / (b[ok] * t1[ok] / T[ok]).sum())
    return np.percentile(vals, [2.5, 97.5])


def wilson(k, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


# ------------------------------------------------------------------------ main
def main():
    os.makedirs(OUT, exist_ok=True)
    inj, snaps, players = load()
    ep = games_missed(build_episodes(inj, snaps, players), snaps)
    ps = exposure(snaps, players)

    # episodes in the analysis window: regular-season onsets 2013-2024
    reg_ep = ep[(ep["game_type"] == "REG") & ep["season"].between(FIRST, LAST)].copy()
    reg_ep = reg_ep.merge(ps[["pfr_player_id", "season", "group", "age_band"]],
                          left_on=["pfr_id", "season"], right_on=["pfr_player_id", "season"], how="left")
    reg_ep["group"] = reg_ep["group"].fillna(reg_ep["position"].map(POS_GROUP)).fillna("Other")
    reg_ep.drop(columns=["pfr_player_id"]).to_csv(f"{OUT}/hamstring_episodes.csv", index=False)

    win = ps[ps["season"].between(FIRST, LAST)].copy()
    ev = reg_ep.groupby(["pfr_id", "season"]).size().rename("events")
    win = win.merge(ev, left_on=["pfr_player_id", "season"], right_index=True, how="left")
    win["events"] = win["events"].fillna(0).astype(int)
    ev_tl = reg_ep[reg_ep["games_missed"] > 0].groupby(["pfr_id", "season"]).size().rename("events_tl")
    win = win.merge(ev_tl, left_on=["pfr_player_id", "season"], right_index=True, how="left")
    win["events_tl"] = win["events_tl"].fillna(0).astype(int)

    # data flow
    flow = pd.DataFrame([
        ("weekly injury-report rows 2009-2025", len(inj)),
        ("  rows naming a hamstring injury", int(inj["hamstring"].sum())),
        ("hamstring episodes (all seasons, all game types)", len(ep)),
        ("regular-season hamstring episodes 2013-2024", len(reg_ep)),
        ("  episodes without snap-count exposure that season", int(reg_ep["age_band"].isna().sum())),
        ("player-seasons with >= 1 regular-season game 2013-2024", len(win)),
        ("player-games (regular season, >= 1 snap) 2013-2024", int(win["games"].sum())),
        ("players", win["pfr_player_id"].nunique()),
    ], columns=["step", "n"])
    flow.to_csv(f"{OUT}/data_flow.csv", index=False)

    # 1. incidence per 1,000 player-games, overall / by position / by season
    def rate(e, g):
        return 1000 * e / g

    win_m = win.copy()
    overall = rate(win_m["events"].sum(), win_m["games"].sum())
    ci = boot_rate(win_m)
    overall_tl = rate(win_m["events_tl"].sum(), win_m["games"].sum())
    ci_tl = boot_rate(win_m.assign(events=win_m["events_tl"]))
    pos_rows = []
    for gname in GROUP_ORDER:
        d = win_m[win_m["group"] == gname]
        lo, hi = boot_rate(d)
        lo2, hi2 = boot_rate(d.assign(events=d["events_tl"]))
        pos_rows.append({"group": gname, "player_games": int(d["games"].sum()), "episodes": int(d["events"].sum()),
                         "rate_per_1000_games": rate(d["events"].sum(), d["games"].sum()), "low": lo, "high": hi,
                         "timeloss_episodes": int(d["events_tl"].sum()),
                         "timeloss_rate": rate(d["events_tl"].sum(), d["games"].sum()), "tl_low": lo2, "tl_high": hi2})
    by_pos = pd.DataFrame(pos_rows)
    by_pos.to_csv(f"{OUT}/rate_by_position.csv", index=False)
    by_season = (win_m.groupby("season").agg(episodes=("events", "sum"), timeloss_episodes=("events_tl", "sum"),
                                            player_games=("games", "sum")).reset_index())
    by_season["rate_per_1000_games"] = rate(by_season["episodes"], by_season["player_games"])
    by_season["timeloss_rate_per_1000_games"] = rate(by_season["timeloss_episodes"], by_season["player_games"])
    by_season.to_csv(f"{OUT}/rate_by_season.csv", index=False)

    # 2. time lost
    tl = reg_ep["games_missed"]
    miss_dist = pd.Series({"0 games (played through)": (tl == 0).mean(), "1 game": (tl == 1).mean(),
                           "2-3 games": tl.between(2, 3).mean(), "4+ games": (tl >= 4).mean()})
    miss_dist.to_csv(f"{OUT}/games_missed_distribution.csv", header=["share"])

    # 3. risk after a hamstring injury in the previous season (same players, exposed both seasons)
    prev_any = ep.assign(season_next=ep["season"] + 1).groupby(["pfr_id", "season_next"]).size().rename("prev")
    cur = win.merge(prev_any, left_on=["pfr_player_id", "season"], right_index=True, how="left")
    played_prev = set(zip(ps["pfr_player_id"], ps["season"] + 1))
    cur = cur[[(p, s) in played_prev for p, s in zip(cur["pfr_player_id"], cur["season"])]].copy()
    cur["prior"] = cur["prev"].fillna(0) > 0
    cur["stratum"] = cur["group"].astype(str) + "|" + cur["age_band"].astype(str)
    crude = rate(cur.loc[cur["prior"], "events"].sum(), cur.loc[cur["prior"], "games"].sum()) / \
        rate(cur.loc[~cur["prior"], "events"].sum(), cur.loc[~cur["prior"], "games"].sum())
    mh = mh_rate_ratio(cur, "prior")
    mh_ci = boot_mh(cur)
    # sensitivity: only episodes that cost at least one game (outcome), prior = any episode
    cur_tl = cur.assign(events=cur["events_tl"])
    mh_tl = mh_rate_ratio(cur_tl, "prior")
    mh_tl_ci = boot_mh(cur_tl)
    prior_tab = pd.DataFrame([
        {"group": "hamstring episode in previous season", "player_seasons": int(cur["prior"].sum()),
         "episodes": int(cur.loc[cur["prior"], "events"].sum()), "player_games": int(cur.loc[cur["prior"], "games"].sum())},
        {"group": "no hamstring episode in previous season", "player_seasons": int((~cur["prior"]).sum()),
         "episodes": int(cur.loc[~cur["prior"], "events"].sum()), "player_games": int(cur.loc[~cur["prior"], "games"].sum())}])
    prior_tab["rate_per_1000_games"] = rate(prior_tab["episodes"], prior_tab["player_games"])
    prior_tab.to_csv(f"{OUT}/prior_injury_rates.csv", index=False)

    # 4. same-season re-injury after return, by games missed for the first episode
    ep_s = ep.sort_values(["pfr_id", "onset_k"]).copy()
    ep_s["next_onset"] = ep_s.groupby("pfr_id")["onset_k"].shift(-1)
    ep_s["next_same_season"] = ep_s["next_onset"].notna() & (ep_s["next_onset"] // 100 == ep_s["season"])
    first_in = reg_ep.merge(ep_s[["pfr_id", "onset_k", "next_same_season"]], on=["pfr_id", "onset_k"])
    returned = first_in[~first_in["season_ended"]].copy()
    returned["miss_group"] = pd.cut(returned["games_missed"], [-1, 0, 1, 3, 99],
                                    labels=["0 (played through)", "1", "2-3", "4+"])
    re_rows = []
    for gname, g in returned.groupby("miss_group", observed=True):
        k, n = int(g["next_same_season"].sum()), len(g)
        lo, hi = wilson(k, n)
        re_rows.append({"games_missed_first": str(gname), "episodes": n, "reinjured_same_season": k,
                        "share": k / n, "low": lo, "high": hi})
    k, n = int(returned["next_same_season"].sum()), len(returned)
    lo, hi = wilson(k, n)
    re_rows.append({"games_missed_first": "all who returned", "episodes": n, "reinjured_same_season": k,
                    "share": k / n, "low": lo, "high": hi})
    reinj = pd.DataFrame(re_rows)
    reinj.to_csv(f"{OUT}/same_season_reinjury.csv", index=False)

    # 5. players with repeated episodes over the window
    per_player = reg_ep.groupby("pfr_id").size()
    repeat = pd.DataFrame({"episodes": ["1", "2", "3+"],
                           "players": [int((per_player == 1).sum()), int((per_player == 2).sum()),
                                       int((per_player >= 3).sum())]})
    repeat.to_csv(f"{OUT}/players_by_episodes.csv", index=False)

    headline = pd.DataFrame([
        ("Hamstring episodes per 1,000 player-games", overall, *ci),
        ("Time-loss episodes (>= 1 game missed) per 1,000 player-games", overall_tl, *ci_tl),
        ("Rate ratio after a hamstring episode in the previous season (crude)", crude, np.nan, np.nan),
        ("Rate ratio, adjusted for position group and age band (Mantel-Haenszel)", mh, *mh_ci),
        ("Same, time-loss episodes only as the outcome (Mantel-Haenszel)", mh_tl, *mh_tl_ci),
        ("Median games missed per episode", tl.median(), tl.quantile(.25), tl.quantile(.75)),
        ("Share of episodes with no game missed", (tl == 0).mean(), np.nan, np.nan),
        ("Same-season re-injury after returning", reinj.iloc[-1]["share"], reinj.iloc[-1]["low"], reinj.iloc[-1]["high"]),
        ("Players with 2+ episodes, % of injured players", (per_player >= 2).mean(), np.nan, np.nan),
    ], columns=["measure", "estimate", "low", "high"])
    headline.to_csv(f"{OUT}/headline.csv", index=False)

    with open(f"{OUT}/summary.txt", "w") as fh:
        for t in (flow, headline.round(3), by_pos.round(2), prior_tab.round(2), miss_dist.round(3).to_frame("share"),
                  reinj.round(3), repeat):
            fh.write(t.to_string() + "\n\n")
    print(open(f"{OUT}/summary.txt").read())


if __name__ == "__main__":
    main()
