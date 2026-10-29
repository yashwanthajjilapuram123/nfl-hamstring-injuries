"""Sensitivity analyses for nfl_hamstring.py: do the main findings survive other
reasonable choices? Writes results/sensitivity.csv."""
import numpy as np
import pandas as pd

import nfl_hamstring as m


def episodes_gap_rule(inj, players, max_gap=2):
    """Alternative episode rule that ignores snaps: listings no more than
    `max_gap` weeks apart in the same season belong to the same episode."""
    h = inj[inj["hamstring"]].merge(players[["gsis_id", "pfr_id"]], on="gsis_id", how="left").dropna(subset=["pfr_id"])
    h["k"] = m.week_key(h["season"], h["week"])
    h = h.sort_values(["pfr_id", "k"]).drop_duplicates(["pfr_id", "k"])
    gap = h.groupby("pfr_id")["k"].diff()
    new = gap.isna() | (gap > max_gap)
    h["ep"] = new.cumsum()
    first = h[new]
    return pd.DataFrame({"pfr_id": first["pfr_id"].values, "gsis_id": first["gsis_id"].values,
                         "name": first["full_name"].values, "team": first["team"].values,
                         "position": first["position"].values, "season": first["season"].values,
                         "week": first["week"].values, "game_type": first["game_type"].values,
                         "onset_k": first["k"].values, "last_k": first["k"].values, "n_listings": 1})


def analyse(ep, ps, seasons=(m.FIRST, m.LAST), drop=(), prior_timeloss=False, min_games=1):
    reg = ep[(ep["game_type"] == "REG") & ep["season"].between(*seasons) & ~ep["season"].isin(drop)]
    win = ps[ps["season"].between(*seasons) & ~ps["season"].isin(drop) & (ps["games"] >= min_games)].copy()
    ev = reg.groupby(["pfr_id", "season"]).size().rename("events")
    ev_tl = reg[reg["games_missed"] > 0].groupby(["pfr_id", "season"]).size().rename("events_tl")
    win = win.merge(ev, left_on=["pfr_player_id", "season"], right_index=True, how="left")
    win = win.merge(ev_tl, left_on=["pfr_player_id", "season"], right_index=True, how="left")
    win[["events", "events_tl"]] = win[["events", "events_tl"]].fillna(0)
    prev_src = ep[ep["games_missed"] > 0] if prior_timeloss else ep
    prev = prev_src.assign(sn=prev_src["season"] + 1).groupby(["pfr_id", "sn"]).size().rename("prev")
    cur = win.merge(prev, left_on=["pfr_player_id", "season"], right_index=True, how="left")
    prevgames = ps.set_index(["pfr_player_id", "season"])["games"]
    pg = [prevgames.get((p, s - 1), 0) for p, s in zip(cur["pfr_player_id"], cur["season"])]
    cur = cur[np.array(pg) >= min_games].copy()
    cur["prior"] = cur["prev"].fillna(0) > 0
    cur["stratum"] = cur["group"].astype(str) + "|" + cur["age_band"].astype(str)
    rr = m.mh_rate_ratio(cur, "prior")
    lo, hi = m.boot_mh(cur, n=500)
    rr_tl = m.mh_rate_ratio(cur.assign(events=cur["events_tl"]), "prior")
    return {"episodes": len(reg), "rate_per_1000": 1000 * win["events"].sum() / win["games"].sum(),
            "timeloss_rate_per_1000": 1000 * win["events_tl"].sum() / win["games"].sum(),
            "RR_prior_adj": rr, "RR_low": lo, "RR_high": hi, "RR_prior_adj_timeloss": rr_tl,
            "share_no_game_missed": (reg["games_missed"] == 0).mean()}


def main():
    inj, snaps, players = m.load()
    ps = m.exposure(snaps, players)
    main_ep = m.games_missed(m.build_episodes(inj, snaps, players), snaps)
    alt_ep = m.games_missed(episodes_gap_rule(inj, players), snaps)
    rows = [
        ("Main analysis", analyse(main_ep, ps)),
        ("Episode rule: listings <= 2 weeks apart = same episode", analyse(alt_ep, ps)),
        ("Excluding 2013-2015 ('Probable' status in use)", analyse(main_ep, ps, seasons=(2016, 2024))),
        ("Excluding 2021 (unexplained dip in hamstring listings)", analyse(main_ep, ps, drop=(2021,))),
        ("Previous injury = only episodes that cost a game", analyse(main_ep, ps, prior_timeloss=True)),
        ("Players with >= 8 games in both seasons", analyse(main_ep, ps, min_games=8)),
    ]
    out = pd.DataFrame([{"analysis": k, **v} for k, v in rows])
    out.to_csv(f"{m.OUT}/sensitivity.csv", index=False)
    print(out.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
