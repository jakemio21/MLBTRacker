#!/usr/bin/env python3
"""
MLB Matchup Model — Daily Analysis

Usage:
    python mlb_matchup_model.py                  # today
    python mlb_matchup_model.py 2026-04-25       # specific date

Requires:
    pip install requests
"""

import sys
import json
import hashlib
import webbrowser
from datetime import datetime
from pathlib import Path

import requests

# ── Config ─────────────────────────────────────────────────────────────────────

BASE      = "https://statsapi.mlb.com/api/v1"
TODAY     = datetime.now().strftime("%Y-%m-%d")
YEAR      = datetime.now().year
CACHE_DIR = Path.home() / ".mlb_model_cache"
CACHE_DIR.mkdir(exist_ok=True)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "mlb-matchup-model/1.0"


# ── Cache ──────────────────────────────────────────────────────────────────────

def _cpath(url, params, date):
    key = json.dumps({"u": url, "p": params or {}}, sort_keys=True)
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{date}_{h}.json"

def api(url, params=None, date=TODAY):
    path = _cpath(url, params, date)
    if path.exists():
        return json.loads(path.read_text())
    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        path.write_text(json.dumps(data))
        return data
    except Exception as e:
        print(f"  [API error] {url} — {e}")
        return None


# ── Scoring Tables ─────────────────────────────────────────────────────────────

def ops_score(ops):
    if ops < .550: return 1
    if ops < .600: return 2
    if ops < .650: return 3
    if ops < .700: return 4
    if ops < .750: return 5
    if ops < .800: return 6
    if ops < .850: return 7
    if ops < .900: return 8
    if ops < .950: return 9
    return 10

def sp_era_score(era):
    if era > 5.50: return 1
    if era > 5.00: return 2
    if era > 4.60: return 3
    if era > 4.20: return 4
    if era > 3.80: return 5
    if era > 3.40: return 6
    if era > 3.10: return 7
    if era > 2.80: return 8
    if era > 2.50: return 9
    return 10

# WHIP typical range is 0.80–1.80, so a separate scale is used
def sp_whip_score(whip):
    if whip > 1.70: return 1
    if whip > 1.60: return 2
    if whip > 1.50: return 3
    if whip > 1.40: return 4
    if whip > 1.30: return 5
    if whip > 1.20: return 6
    if whip > 1.10: return 7
    if whip > 1.00: return 8
    if whip > 0.90: return 9
    return 10

def rp_era_score(era):
    if era > 5.20: return 1
    if era > 4.85: return 2
    if era > 4.50: return 3
    if era > 4.15: return 4
    if era > 3.80: return 5
    if era > 3.50: return 6
    if era > 3.20: return 7
    if era > 2.90: return 8
    if era > 2.60: return 9
    return 10

def rp_whip_score(whip):
    if whip > 1.80: return 1
    if whip > 1.65: return 2
    if whip > 1.55: return 3
    if whip > 1.45: return 4
    if whip > 1.35: return 5
    if whip > 1.25: return 6
    if whip > 1.15: return 7
    if whip > 1.05: return 8
    if whip > 0.95: return 9
    return 10

def record_score(pct):
    if pct < .425: return 1
    if pct < .451: return 2
    if pct < .476: return 3
    if pct < .500: return 4
    if pct < .525: return 5
    if pct < .550: return 6
    if pct < .575: return 7
    if pct < .600: return 8
    if pct < .625: return 9
    return 10


# ── Stat Helpers ───────────────────────────────────────────────────────────────

def ip_float(ip):
    """'6.2' → 6.667  (baseball partial-inning notation uses thirds)"""
    s = str(ip or "0")
    parts = s.split(".")
    whole = int(parts[0]) if parts[0] else 0
    frac  = int(parts[1]) / 3 if len(parts) > 1 and parts[1] else 0
    return whole + frac

def _calc_ops(splits):
    ab = h = bb = hbp = sf = d = t = hr = 0
    for s in splits:
        st   = s.get("stat", {})
        ab  += int(st.get("atBats",      0) or 0)
        h   += int(st.get("hits",        0) or 0)
        bb  += int(st.get("baseOnBalls", 0) or 0)
        hbp += int(st.get("hitByPitch",  0) or 0)
        sf  += int(st.get("sacFlies",    0) or 0)
        d   += int(st.get("doubles",     0) or 0)
        t   += int(st.get("triples",     0) or 0)
        hr  += int(st.get("homeRuns",    0) or 0)
    if ab == 0:
        return None
    obp = (h + bb + hbp) / (ab + bb + hbp + sf) if (ab + bb + hbp + sf) else 0
    slg = (h + d + 2*t + 3*hr) / ab
    return obp + slg

def _calc_pitching(splits):
    """Return (era, whip) aggregated across splits."""
    tip = ter = th = tbb = 0
    for s in splits:
        st   = s.get("stat", {})
        tip += ip_float(st.get("inningsPitched", 0))
        ter += int(st.get("earnedRuns",  0) or 0)
        th  += int(st.get("hits",        0) or 0)
        tbb += int(st.get("baseOnBalls", 0) or 0)
    if tip == 0:
        return None, None
    return (ter / tip) * 9, (th + tbb) / tip


# ── Data Fetchers ──────────────────────────────────────────────────────────────

def fetch_schedule(date):
    data = api(f"{BASE}/schedule", {
        "sportId": 1, "date": date,
        "hydrate": "probablePitcher,team,venue"
    }, date)
    if not data:
        return []
    return [
        g for d in data.get("dates", [])
        for g in d.get("games", [])
        if g.get("status", {}).get("abstractGameState") != "Final"
    ]

def fetch_standings(date):
    data = api(f"{BASE}/standings", {
        "leagueId": "103,104", "season": YEAR, "gameType": "R"
    }, date)
    out = {}
    if data:
        for div in data.get("records", []):
            for tr in div.get("teamRecords", []):
                tid = tr["team"]["id"]
                w, l = tr.get("wins", 0), tr.get("losses", 0)
                out[tid] = w / (w + l) if (w + l) else 0.5
    return out

def team_hitting_season(team_id, date):
    data = api(f"{BASE}/teams/{team_id}/stats", {
        "stats": "season", "group": "hitting", "season": YEAR, "gameType": "R"
    }, date)
    if data:
        for sg in data.get("stats", []):
            for sp in sg.get("splits", []):
                v = sp.get("stat", {}).get("ops")
                if v:
                    return float(v)
    return None

def team_hitting_last5(team_id, date):
    data = api(f"{BASE}/teams/{team_id}/stats", {
        "stats": "gameLog", "group": "hitting", "season": YEAR, "gameType": "R"
    }, date)
    if data:
        for sg in data.get("stats", []):
            splits = sg.get("splits", [])
            last5  = splits[-5:] if len(splits) >= 5 else splits
            if last5:
                return _calc_ops(last5)
    return None

def pitcher_season(pid, date):
    data = api(f"{BASE}/people/{pid}/stats", {
        "stats": "season", "group": "pitching", "season": YEAR, "gameType": "R"
    }, date)
    if data:
        for sg in data.get("stats", []):
            for sp in sg.get("splits", []):
                st = sp.get("stat", {})
                if st.get("era") is not None:
                    return float(st["era"]), float(st.get("whip", 1.35))
    return None, None

def pitcher_last5(pid, date):
    data = api(f"{BASE}/people/{pid}/stats", {
        "stats": "gameLog", "group": "pitching", "season": YEAR, "gameType": "R"
    }, date)
    if data:
        for sg in data.get("stats", []):
            splits = sg.get("splits", [])
            starts = [s for s in splits
                      if ip_float(s.get("stat", {}).get("inningsPitched", 0)) >= 3.0]
            src   = starts or splits
            last5 = src[-5:] if len(src) >= 5 else src
            return _calc_pitching(last5)
    return None, None

def pitcher_home_away(pid, is_home, date):
    data = api(f"{BASE}/people/{pid}/stats", {
        "stats": "statSplits", "group": "pitching", "season": YEAR, "gameType": "R"
    }, date)
    label = "Home" if is_home else "Away"
    if data:
        for sg in data.get("stats", []):
            for sp in sg.get("splits", []):
                if sp.get("split", {}).get("description") == label:
                    st = sp.get("stat", {})
                    if st.get("era") is not None:
                        return float(st["era"]), float(st.get("whip", 1.35))
    return None, None

def team_bullpen(team_id, date):
    """Team aggregate pitching ERA/WHIP as bullpen proxy — 1 API call instead of 10+."""
    data = api(f"{BASE}/teams/{team_id}/stats", {
        "stats": "season", "group": "pitching", "season": YEAR, "gameType": "R"
    }, date)
    if data:
        for sg in data.get("stats", []):
            for sp in sg.get("splits", []):
                st = sp.get("stat", {})
                era  = st.get("era")
                whip = st.get("whip")
                if era is not None:
                    return float(era), float(whip or 1.35)
    return None, None


# ── Score Calculators ──────────────────────────────────────────────────────────

def calc_hitting(team_id, date):
    s_ops  = team_hitting_season(team_id, date) or 0.710
    l5_ops = team_hitting_last5(team_id, date)  or s_ops
    wops   = l5_ops * 0.65 + s_ops * 0.35
    return ops_score(wops), wops

def calc_sp(pid, is_home, date):
    if not pid:
        return 5.0

    s_era,  s_whip  = pitcher_season(pid, date)
    l5_era, l5_whip = pitcher_last5(pid, date)
    ha_era, ha_whip = pitcher_home_away(pid, is_home, date)

    s_era   = s_era   or 4.50;  s_whip  = s_whip  or 1.35
    l5_era  = l5_era  or s_era; l5_whip = l5_whip or s_whip
    ha_era  = ha_era  or s_era; ha_whip = ha_whip or s_whip

    w_era   = s_era  * 0.60 + l5_era  * 0.40
    w_whip  = s_whip * 0.60 + l5_whip * 0.40

    era_sc  = sp_era_score(w_era)
    whip_sc = sp_whip_score(w_whip)
    ha_sc   = (sp_era_score(ha_era) + sp_whip_score(ha_whip)) / 2

    return era_sc * 0.40 + whip_sc * 0.40 + ha_sc * 0.20

def calc_rp(team_id, date):
    # Last-5-games bullpen data would require per-game reliever logs (hundreds of
    # extra API calls), so season stats serve as the proxy for both components.
    s_era, s_whip = team_bullpen(team_id, date)
    s_era  = s_era  or 4.20
    s_whip = s_whip or 1.35
    return rp_era_score(s_era) * 0.50 + rp_whip_score(s_whip) * 0.50

def calc_record(team_id, standings):
    pct = standings.get(team_id)
    return record_score(pct) if pct is not None else 5.0

def score_team(team_id, name, pid, is_home, standings, date):
    h_sc, wops = calc_hitting(team_id, date)
    sp_sc      = calc_sp(pid, is_home, date)
    rp_sc      = calc_rp(team_id, date)
    rec_sc     = calc_record(team_id, standings)
    final      = h_sc * 0.40 + sp_sc * 0.32 + rp_sc * 0.18 + rec_sc * 0.10
    return {
        "name":    name,
        "id":      team_id,
        "is_home": is_home,
        "final":   round(final,  2),
        "hitting": round(h_sc,   2),
        "sp":      round(sp_sc,  2),
        "rp":      round(rp_sc,  2),
        "record":  round(rec_sc, 2),
        "wops":    round(wops,   3),
    }


# ── Terminal Report ────────────────────────────────────────────────────────────

W = 66
DIV = "─" * W

def edge_label(edge):
    if edge < 1.0: return "Toss-up"
    if edge < 2.0: return "Slight edge"
    if edge < 3.0: return "Strong edge"
    return "TOP PLAY — Very strong edge"

def print_game(r):
    fav, dog = r["fav"], r["dog"]
    fl = "Home" if fav["is_home"] else "Away"
    dl = "Home" if dog["is_home"] else "Away"
    print(f"\n  {fav['name']} ({fl})  vs  {dog['name']} ({dl})")
    print(f"  Score    {fav['name']} {fav['final']}  |  {dog['name']} {dog['final']}")
    print(f"  Edge     {fav['name']} +{r['edge']:.1f}  [{r['label']}]")
    print(f"  SPs      {r['away_sp']} (Away) vs {r['home_sp']} (Home)")

def print_report(results, date):
    print(f"\n{'=' * W}")
    print(f"  MLB MATCHUP MODEL   {date}")
    print(f"{'=' * W}")
    buckets = [
        ("TOP ALGORITHM FAVOURITES  (Edge 3.0+)",   [r for r in results if r["edge"] >= 3.0]),
        ("STRONG EDGES  (2.0 – 2.9)",               [r for r in results if 2.0 <= r["edge"] < 3.0]),
        ("SLIGHT EDGES  (1.0 – 1.9)",               [r for r in results if 1.0 <= r["edge"] < 2.0]),
        ("CLOSE GAMES / TOSS-UPS  (< 1.0)",         [r for r in results if r["edge"] < 1.0]),
    ]
    for title, group in buckets:
        if group:
            print(f"\n{DIV}\n  {title}\n{DIV}")
            for r in group:
                print_game(r)
    print(f"\n{'=' * W}\n")


# ── History & Results ─────────────────────────────────────────────────────────

HISTORY_FILE = CACHE_DIR / "picks_history.json"

TIER_META = {
    "top":    ("&#128293; Top Picks",    "top"),
    "strong": ("&#9889; Strong Edges",   "strong"),
    "slight": ("&#128202; Slight Edges", "slight"),
    "tossup": ("&#10134; Toss-Ups",      "tossup"),
}

def load_history():
    try:
        return json.loads(HISTORY_FILE.read_text()) if HISTORY_FILE.exists() else {}
    except Exception:
        return {}

def save_history(h):
    HISTORY_FILE.write_text(json.dumps(h, indent=2))

def record_picks(results, date, h):
    if date in h:
        return
    h[date] = {"picks": [
        {
            "tier": _tier(r["edge"]), "edge": r["edge"],
            "fav_name": r["fav"]["name"], "fav_id": r["fav"]["id"],
            "dog_name":  r["dog"]["name"],
            "home_sp": r["home_sp"], "away_sp": r["away_sp"],
            "outcome": None, "fav_score": None, "dog_score": None,
        }
        for r in results
    ]}
    save_history(h)

def resolve_outcomes(h):
    today = datetime.now().strftime("%Y-%m-%d")
    changed = False
    for date in sorted(h):
        if date >= today:
            continue
        picks = h[date].get("picks", [])
        if all(p.get("outcome") for p in picks):
            continue
        data = api(f"{BASE}/schedule", {
            "sportId": 1, "date": date, "hydrate": "team,linescore"
        }, date)
        if not data:
            continue
        scores = {}
        for d in data.get("dates", []):
            for g in d.get("games", []):
                if g.get("status", {}).get("abstractGameState") != "Final":
                    continue
                ls   = g.get("linescore", {}).get("teams", {})
                h_id = g["teams"]["home"]["team"]["id"]
                a_id = g["teams"]["away"]["team"]["id"]
                hr   = ls.get("home", {}).get("runs") or 0
                ar   = ls.get("away", {}).get("runs") or 0
                scores[h_id] = (hr, ar)
                scores[a_id] = (ar, hr)
        for p in picks:
            if p.get("outcome") or p["fav_id"] not in scores:
                continue
            fr, dr = scores[p["fav_id"]]
            p["outcome"]   = "win" if fr > dr else "loss"
            p["fav_score"] = fr
            p["dog_score"] = dr
            changed = True
    if changed:
        save_history(h)
    return h

def _results_html(h, current_date):
    stats = {t: [0, 0] for t in TIER_META}
    rows  = []
    for date in sorted(h, reverse=True):
        if date == current_date:
            continue
        dlbl = datetime.strptime(date, "%Y-%m-%d").strftime("%b %d")
        for p in h[date].get("picks", []):
            t = p.get("tier", "tossup")
            if p.get("outcome") == "win":
                stats[t][0] += 1
            elif p.get("outcome") == "loss":
                stats[t][1] += 1
            if p.get("outcome"):
                win = p["outcome"] == "win"
                fs, ds = p.get("fav_score", "?"), p.get("dog_score", "?")
                rows.append(
                    f'<tr class="pr {"win" if win else "loss"}">'
                    f'<td class="pr-date">{dlbl}</td>'
                    f'<td><span class="td-dot {t}"></span></td>'
                    f'<td class="pr-mu"><b>{p["fav_name"]}</b>'
                    f' <span class="pr-edge">+{p["edge"]:.1f}</span>'
                    f' vs {p["dog_name"]}</td>'
                    f'<td class="pr-sc">{fs}&#8211;{ds}</td>'
                    f'<td class="pr-res {"win" if win else "loss"}">'
                    f'{"&#10003;" if win else "&#10007;"}</td>'
                    f'</tr>'
                )
    cards = ""
    for t, (lbl, cls) in TIER_META.items():
        w, l = stats[t]
        tot  = w + l
        pct  = round(w / tot * 100) if tot else 0
        cards += (
            f'<div class="rc {cls}">'
            f'<div class="rc-lbl">{lbl}</div>'
            f'<div class="rc-pct">{pct}<span>%</span></div>'
            f'<div class="rc-rec">{w}W &ndash; {l}L</div>'
            f'<div class="rc-bar-bg"><div class="rc-bar {cls}" style="width:{pct}%"></div></div>'
            f'</div>'
        )
    table = (
        '<div class="pt-wrap"><table class="pt"><thead><tr>'
        '<th>Date</th><th></th><th>Pick</th><th>Score</th><th></th>'
        '</tr></thead><tbody>' + "\n".join(rows) + '</tbody></table></div>'
        if rows else
        '<div class="no-hist">No resolved picks yet &#8212; run the model tomorrow to see results.</div>'
    )
    return (
        '<div class="rpage-hd">'
          '<div class="rpage-title">Algorithm Performance</div>'
          '<div class="rpage-sub">Win rate tracked across all confidence tiers</div>'
        '</div>'
        f'<div class="rc-grid">{cards}</div>'
        '<div class="rpage-shd">&#128197; Pick History</div>'
        + table
    )


# ── Web Report ─────────────────────────────────────────────────────────────────

def _logo_url(team_id):
    return f"https://www.mlbstatic.com/team-logos/{team_id}.svg"

def _tier(edge):
    if edge >= 3.0: return "top"
    if edge >= 2.0: return "strong"
    if edge >= 1.0: return "slight"
    return "tossup"

BADGE = {
    "top":    "&#128293; TOP PLAY",
    "strong": "&#9889; Strong Edge",
    "slight": "&#128202; Slight Edge",
    "tossup": "&#10134; Toss-Up",
}

def _card(r, large=False):
    fav, dog = r["fav"], r["dog"]
    t   = _tier(r["edge"])
    lgs = " lg" if large else ""
    mu  = "mu" if large else "mu sm"
    pct = round((fav["final"] / 10) * 100)
    fav_loc = "&#127968; Home" if fav["is_home"] else "&#9992;&#65039; Away"
    dog_loc = "&#127968; Home" if dog["is_home"] else "&#9992;&#65039; Away"
    return (
        f'<div class="card {t}">'
        f'<span class="badge {t}">{BADGE[t]}</span>'
        f'<div class="{mu}">'
          f'<div class="team ta">'
            f'<div class="t-id">'
              f'<div class="logo-wrap{lgs}">'
                f'<img class="logo" src="{_logo_url(fav["id"])}" alt="" onerror="this.remove()">'
              f'</div>'
              f'<div>'
                f'<div class="t-name{lgs}">{fav["name"]}</div>'
                f'<div class="t-meta">{fav_loc}</div>'
              f'</div>'
            f'</div>'
            f'<div class="score{lgs}">{fav["final"]}</div>'
          f'</div>'
          f'<div class="vs-col">'
            f'<div class="vs-tag">EDGE</div>'
            f'<div class="edge-n {t}">+{r["edge"]:.1f}</div>'
            f'<div class="vs-tag">VS</div>'
          f'</div>'
          f'<div class="team tb">'
            f'<div class="t-id">'
              f'<div class="logo-wrap{lgs}">'
                f'<img class="logo" src="{_logo_url(dog["id"])}" alt="" onerror="this.remove()">'
              f'</div>'
              f'<div>'
                f'<div class="t-name{lgs}">{dog["name"]}</div>'
                f'<div class="t-meta">{dog_loc}</div>'
              f'</div>'
            f'</div>'
            f'<div class="score{lgs} dim">{dog["final"]}</div>'
          f'</div>'
        f'</div>'
        f'<div class="bar">'
          f'<div class="bar-f" style="width:{pct}%"></div>'
          f'<div class="bar-d"></div>'
        f'</div>'
        f'<div class="sp">'
          f'<span class="sp-n">{r["away_sp"]}</span>'
          f'<span class="sp-b">&#9918;</span>'
          f'<span class="sp-n">{r["home_sp"]}</span>'
        f'</div>'
        f'</div>'
    )

def _section(icon, title, cls, grid_cls, items, large=False):
    if not items:
        return ""
    s = "s" if len(items) != 1 else ""
    cards = "\n".join(_card(r, large) for r in items)
    return (
        f'<div class="sec-hd">'
          f'<span class="sec-ico">{icon}</span>'
          f'<span class="sec-lbl {cls}">{title}</span>'
          f'<div class="sec-rule {cls}"></div>'
          f'<span class="sec-ct">{len(items)} game{s}</span>'
        f'</div>'
        f'<div class="grid {grid_cls}">{cards}</div>'
    )

HTML_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MLB Matchup Model</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700;800;900&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#060912;--card:#0c1525;--card2:#101d35;
  --border:rgba(255,255,255,0.055);--border2:rgba(255,255,255,0.10);
  --gold:#f5a523;--gold-lt:#ffd060;--gold-dim:rgba(245,165,35,0.13);
  --green:#00d47e;--green-dim:rgba(0,212,126,0.11);
  --blue:#4d8af5;--blue-dim:rgba(77,138,245,0.11);
  --gray:#55667a;--gray-dim:rgba(85,102,122,0.09);
  --text:#dce8f8;--dim:#6a7f98;--muted:#3a4d62;
}
html{scroll-behavior:smooth}
body{
  background:var(--bg);color:var(--text);
  font-family:'Inter',system-ui,sans-serif;
  min-height:100vh;overflow-x:hidden;
}
body::before{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:
    radial-gradient(ellipse 55% 40% at 10% 10%,rgba(77,138,245,0.07) 0%,transparent 65%),
    radial-gradient(ellipse 45% 35% at 90% 85%,rgba(245,165,35,0.05) 0%,transparent 65%),
    radial-gradient(ellipse 35% 25% at 55% 50%,rgba(0,212,126,0.03) 0%,transparent 65%);
}
body::after{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(255,255,255,0.016) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(255,255,255,0.016) 1px,transparent 1px);
  background-size:64px 64px;
}

/* HEADER */
.hdr{
  position:sticky;top:0;z-index:100;
  background:rgba(6,9,18,0.88);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid rgba(245,165,35,0.14);
  padding:16px 48px;
  display:flex;align-items:center;justify-content:space-between;
}
.hdr-brand{display:flex;align-items:center;gap:14px}
.hdr-icon{
  font-size:30px;line-height:1;
  filter:drop-shadow(0 0 14px rgba(245,165,35,0.75));
  display:inline-block;animation:spin 25s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}
.hdr-title{
  font-family:'Barlow Condensed',sans-serif;
  font-size:24px;font-weight:900;letter-spacing:4px;text-transform:uppercase;
  background:linear-gradient(135deg,#fff 0%,#aac5f8 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.hdr-right{display:flex;align-items:center;gap:14px}
.live{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--dim);letter-spacing:1.5px}
.dot{
  width:7px;height:7px;border-radius:50%;
  background:var(--green);box-shadow:0 0 7px var(--green);
  animation:blink 2s ease infinite;
}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.45}}
.date-pill{
  font-family:'Barlow Condensed',sans-serif;
  font-size:14px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  color:var(--gold);background:var(--gold-dim);
  border:1px solid rgba(245,165,35,0.22);
  padding:6px 18px;border-radius:999px;
}

/* LAYOUT */
.wrap{position:relative;z-index:1;max-width:1280px;margin:0 auto;padding:36px 40px 100px}

/* SECTION HEADERS */
.sec-hd{display:flex;align-items:center;gap:12px;margin:52px 0 20px}
.sec-hd:first-child{margin-top:0}
.sec-ico{font-size:20px}
.sec-lbl{
  font-family:'Barlow Condensed',sans-serif;
  font-size:16px;font-weight:800;letter-spacing:3.5px;text-transform:uppercase;white-space:nowrap;
}
.sec-lbl.top{color:var(--gold)} .sec-lbl.strong{color:var(--green)}
.sec-lbl.slight{color:var(--blue)} .sec-lbl.tossup{color:var(--gray)}
.sec-rule{flex:1;height:1px;opacity:.18}
.sec-rule.top{background:var(--gold)} .sec-rule.strong{background:var(--green)}
.sec-rule.slight{background:var(--blue)} .sec-rule.tossup{background:var(--gray)}
.sec-ct{font-family:'Barlow Condensed',sans-serif;font-size:12px;font-weight:700;color:var(--muted);letter-spacing:1px}

/* GRIDS */
.grid{display:grid;gap:16px}
.g1{grid-template-columns:1fr}
.g2{grid-template-columns:repeat(auto-fill,minmax(500px,1fr))}
.g3{grid-template-columns:repeat(auto-fill,minmax(360px,1fr))}

/* CARDS */
.card{
  position:relative;background:var(--card);border-radius:20px;border:1px solid var(--border);
  padding:26px 30px 22px;overflow:hidden;
  transition:transform .22s cubic-bezier(.22,.68,0,1.18),box-shadow .22s ease;
}
.card:hover{transform:translateY(-5px)}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}

.card.top{
  border-color:rgba(245,165,35,0.35);
  background:linear-gradient(145deg,#0e192e 0%,#0c1525 60%,#0e1a2a 100%);
  box-shadow:0 0 60px rgba(245,165,35,0.15),0 0 120px rgba(245,165,35,0.07),
             inset 0 1px 0 rgba(245,165,35,0.12),inset -120px -120px 120px rgba(245,165,35,0.03);
}
.card.top:hover{box-shadow:0 8px 80px rgba(245,165,35,0.22),0 0 130px rgba(245,165,35,0.10)}
.card.top::before{background:linear-gradient(90deg,transparent,var(--gold) 30%,var(--gold-lt) 50%,var(--gold) 70%,transparent);height:3px}
.card.strong{border-color:rgba(0,212,126,0.14)}
.card.strong::before{background:linear-gradient(90deg,transparent,var(--green),transparent)}
.card.slight{border-color:rgba(77,138,245,0.11)}
.card.slight::before{background:linear-gradient(90deg,transparent,var(--blue),transparent)}
.card.tossup::before{background:linear-gradient(90deg,transparent,var(--gray),transparent);opacity:.35}

/* BADGE */
.badge{
  display:inline-flex;align-items:center;gap:5px;
  font-family:'Barlow Condensed',sans-serif;
  font-size:11px;font-weight:800;letter-spacing:2.5px;text-transform:uppercase;
  padding:4px 13px 3px;border-radius:999px;margin-bottom:20px;
}
.badge.top{
  background:linear-gradient(135deg,#f5a523,#e88a0a);color:#080300;
  box-shadow:0 0 18px rgba(245,165,35,0.38);
  animation:glow 2.5s ease-in-out infinite;
}
@keyframes glow{0%,100%{box-shadow:0 0 18px rgba(245,165,35,0.38)}50%{box-shadow:0 0 32px rgba(245,165,35,0.65)}}
.badge.strong{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,212,126,0.28)}
.badge.slight{background:var(--blue-dim);color:var(--blue);border:1px solid rgba(77,138,245,0.28)}
.badge.tossup{background:var(--gray-dim);color:var(--gray);border:1px solid rgba(85,102,122,0.2)}

/* MATCHUP */
.mu{display:grid;grid-template-columns:1fr 96px 1fr;align-items:center;gap:14px;margin-bottom:16px}
.mu.sm{grid-template-columns:1fr 80px 1fr}
.team{display:flex;flex-direction:column;gap:10px}
.ta{align-items:flex-start} .tb{align-items:flex-end}
.t-id{display:flex;align-items:center;gap:11px}
.tb .t-id{flex-direction:row-reverse}

.logo-wrap{width:52px;height:52px;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.logo-wrap.lg{width:70px;height:70px}
.logo{width:100%;height:100%;object-fit:contain;filter:drop-shadow(0 2px 10px rgba(0,0,0,0.6));transition:transform .2s}
.card:hover .logo{transform:scale(1.06)}
.logo-fb{
  width:100%;height:100%;border-radius:50%;
  background:var(--card2);border:1px solid var(--border2);
  display:flex;align-items:center;justify-content:center;
  font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:16px;color:var(--dim);
}

.t-name{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:19px;line-height:1.1}
.t-name.lg{font-size:26px}
.t-meta{font-size:10px;color:var(--dim);letter-spacing:1.2px;text-transform:uppercase;margin-top:2px}

.score{font-family:'Barlow Condensed',sans-serif;font-weight:900;font-size:54px;line-height:1;color:#fff}
.score.lg{font-size:72px}
.score.dim{color:var(--dim)}
.tb .score{text-align:right}

/* VS CENTER */
.vs-col{display:flex;flex-direction:column;align-items:center;gap:4px;text-align:center}
.vs-tag{font-size:10px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;font-weight:600}
.edge-n{font-family:'Barlow Condensed',sans-serif;font-weight:900;font-size:32px;line-height:1}
.edge-n.top{color:var(--gold);text-shadow:0 0 22px rgba(245,165,35,0.55)}
.edge-n.strong{color:var(--green)}
.edge-n.slight{color:var(--blue)}
.edge-n.tossup{color:var(--gray)}

/* SCORE BAR */
.bar{height:4px;background:var(--border);border-radius:4px;overflow:hidden;display:flex;gap:2px;margin-bottom:16px}
.bar-f{border-radius:4px 0 0 4px;background:linear-gradient(90deg,rgba(255,255,255,0.07),rgba(255,255,255,0.22))}
.bar-d{flex:1;border-radius:0 4px 4px 0;background:rgba(255,255,255,0.035)}

/* SP STRIP */
.sp{
  border-top:1px solid var(--border);padding-top:12px;
  display:flex;align-items:center;justify-content:center;
  gap:9px;flex-wrap:wrap;font-size:12px;color:var(--dim);
}
.sp-n{color:var(--text);font-weight:500}
.sp-b{opacity:.3;font-size:13px}

/* EMPTY */
.empty{text-align:center;padding:100px 20px;color:var(--dim)}
.empty-ico{font-size:64px;margin-bottom:20px}
.empty-txt{font-size:20px;font-weight:500}

/* FOOTER */
footer{
  position:relative;z-index:1;text-align:center;padding:22px;
  color:var(--muted);font-size:11px;letter-spacing:1px;
  border-top:1px solid var(--border);
}

/* ── NAV TABS ── */
.nav-bar{
  position:sticky;top:62px;z-index:99;
  display:flex;align-items:center;gap:8px;padding:10px 48px;
  background:rgba(6,9,18,0.9);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  border-bottom:1px solid rgba(255,255,255,0.05);
}
.nav-btn{
  font-family:'Barlow Condensed',sans-serif;
  font-size:13px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
  padding:8px 26px;border-radius:999px;
  border:1px solid rgba(255,255,255,0.1);
  background:transparent;color:var(--dim);
  cursor:pointer;transition:all .18s;
}
.nav-btn:hover:not(.active){background:rgba(255,255,255,0.06);color:var(--text)}
.nav-btn.active{background:var(--gold);color:#060912;border-color:var(--gold);
  box-shadow:0 0 18px rgba(245,165,35,0.35);}
.page{display:none}
.page.active{display:block}

/* ── RESULTS PAGE ── */
.rpage-hd{text-align:center;padding:44px 0 30px}
.rpage-title{
  font-family:'Barlow Condensed',sans-serif;
  font-size:36px;font-weight:900;letter-spacing:2px;
  background:linear-gradient(135deg,#fff 0%,#aac5f8 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.rpage-sub{color:var(--dim);font-size:13px;margin-top:8px;letter-spacing:.3px}
.rpage-shd{
  font-family:'Barlow Condensed',sans-serif;
  font-size:13px;font-weight:800;letter-spacing:3px;text-transform:uppercase;
  color:var(--muted);margin:40px 0 16px;
}
.rc-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:8px}
@media(max-width:900px){.rc-grid{grid-template-columns:repeat(2,1fr)}}
.rc{
  background:var(--card);border-radius:20px;padding:26px 20px 22px;
  border:1px solid var(--border);text-align:center;
  transition:transform .2s,box-shadow .2s;
}
.rc:hover{transform:translateY(-3px)}
.rc.top{border-color:rgba(245,165,35,0.25);
  box-shadow:0 0 30px rgba(245,165,35,0.06)}
.rc.strong{border-color:rgba(0,212,126,0.15)}
.rc.slight{border-color:rgba(77,138,245,0.12)}
.rc-lbl{
  font-family:'Barlow Condensed',sans-serif;font-size:11px;font-weight:700;
  letter-spacing:2px;text-transform:uppercase;color:var(--dim);margin-bottom:14px;
}
.rc-pct{
  font-family:'Barlow Condensed',sans-serif;font-size:62px;
  font-weight:900;line-height:1;color:#fff;
}
.rc-pct span{font-size:30px}
.rc-rec{font-size:12px;color:var(--dim);margin:8px 0 18px}
.rc-bar-bg{height:4px;background:var(--border);border-radius:4px;overflow:hidden}
.rc-bar{height:100%;border-radius:4px;transition:width .5s ease}
.rc-bar.top{background:var(--gold)}
.rc-bar.strong{background:var(--green)}
.rc-bar.slight{background:var(--blue)}
.rc-bar.tossup{background:var(--gray)}
.pt-wrap{
  overflow:hidden;border-radius:16px;
  border:1px solid var(--border);margin-bottom:60px;
}
.pt{width:100%;border-collapse:collapse;font-size:13px}
.pt th{
  font-family:'Barlow Condensed',sans-serif;font-size:11px;font-weight:700;
  letter-spacing:2px;text-transform:uppercase;color:var(--muted);
  padding:13px 18px;text-align:left;background:rgba(255,255,255,0.02);
  border-bottom:1px solid var(--border);
}
.pt td{padding:14px 18px;border-top:1px solid rgba(255,255,255,0.03);vertical-align:middle}
.pr:hover td{background:rgba(255,255,255,0.015)}
.pr-date{color:var(--dim);font-size:12px;white-space:nowrap;width:60px}
.td-dot{
  display:inline-block;width:8px;height:8px;border-radius:50%;
  vertical-align:middle;
}
.td-dot.top{background:var(--gold);box-shadow:0 0 6px rgba(245,165,35,0.5)}
.td-dot.strong{background:var(--green)}
.td-dot.slight{background:var(--blue)}
.td-dot.tossup{background:var(--gray)}
.pr-mu{color:var(--text);min-width:280px}
.pr-mu b{font-weight:600}
.pr-edge{
  font-family:'Barlow Condensed',sans-serif;font-weight:700;
  font-size:12px;color:var(--gold);
}
.pr-sc{
  font-family:'Barlow Condensed',sans-serif;font-size:15px;
  font-weight:700;color:var(--dim);white-space:nowrap;
}
.pr-res{font-size:17px;font-weight:700;text-align:center;width:40px}
.pr-res.win{color:var(--green)}
.pr-res.loss{color:#ff4757}
.no-hist{
  text-align:center;padding:64px 20px;
  color:var(--muted);font-size:15px;
  border:1px solid var(--border);border-radius:16px;
}
</style>
</head>
<body>
<header class="hdr">
  <div class="hdr-brand">
    <span class="hdr-icon">&#9918;</span>
    <span class="hdr-title">MLB Matchup Model</span>
  </div>
  <div class="hdr-right">
    <span class="live"><span class="dot"></span>LIVE</span>
    <div class="date-pill">__DATE__</div>
  </div>
</header>

<div class="nav-bar">
  <button class="nav-btn active" onclick="nav('home',this)">&#9918;&nbsp; Today's Picks</button>
  <button class="nav-btn" onclick="nav('results',this)">&#128202;&nbsp; Results Tracker</button>
</div>

<div id="page-home" class="page active">
  <div class="wrap">__HOME__</div>
</div>
<div id="page-results" class="page">
  <div class="wrap">__RESULTS__</div>
</div>

<footer>Generated __GEN__&nbsp;&nbsp;&#183;&nbsp;&nbsp;Data via MLB Stats API&nbsp;&nbsp;&#183;&nbsp;&nbsp;For entertainment purposes only</footer>
<script>
function nav(name,btn){
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active');});
  document.querySelectorAll('.nav-btn').forEach(function(b){b.classList.remove('active');});
  document.getElementById('page-'+name).classList.add('active');
  btn.classList.add('active');
}
</script>
</body>
</html>"""


def open_in_browser(results, date):
    # Load history, resolve yesterday's outcomes, record today's picks
    h = load_history()
    h = resolve_outcomes(h)
    record_picks(results, date, h)

    top    = [r for r in results if r["edge"] >= 3.0]
    strong = [r for r in results if 2.0 <= r["edge"] < 3.0]
    slight = [r for r in results if 1.0 <= r["edge"] < 2.0]
    toss   = [r for r in results if r["edge"] < 1.0]

    home = (
        _section("&#128293;", "Top Algorithm Favourites", "top",    "g1", top,    large=True)
      + _section("&#9889;",   "Strong Edges",             "strong", "g2", strong)
      + _section("&#128202;", "Slight Edges",             "slight", "g3", slight)
      + _section("&#10134;",  "Close Games / Toss-Ups",   "tossup", "g3", toss)
    ) or '<div class="empty"><div class="empty-ico">&#9918;</div><div class="empty-txt">No games scheduled today.</div></div>'

    html = (HTML_SHELL
            .replace("__HOME__",    home)
            .replace("__RESULTS__", _results_html(h, date))
            .replace("__DATE__",    datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y"))
            .replace("__GEN__",     datetime.now().strftime("%B %d, %Y at %I:%M %p")))

    out = Path.home() / "Downloads" / f"mlb_{date}.html"
    out.write_text(html, encoding="utf-8")
    print(f"  Opening browser → {out}")
    webbrowser.open(out.as_uri())


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else TODAY
    print(f"\nMLB Matchup Model  |  {date}")
    print("Fetching schedule and standings…")

    games     = fetch_schedule(date)
    standings = fetch_standings(date)

    if not games:
        print("No games scheduled.")
        return

    print(f"Found {len(games)} game(s). Calculating scores…\n")

    results = []
    for game in games:
        try:
            t         = game.get("teams", {})
            home      = t.get("home", {})
            away      = t.get("away", {})
            home_id   = home["team"]["id"]
            away_id   = away["team"]["id"]
            home_name = home["team"]["name"]
            away_name = away["team"]["name"]

            hp       = home.get("probablePitcher") or {}
            ap       = away.get("probablePitcher") or {}
            home_pid = hp.get("id")
            away_pid = ap.get("id")
            home_sp  = hp.get("fullName", "TBD")
            away_sp  = ap.get("fullName", "TBD")

            print(f"  {away_name} @ {home_name}  |  {away_sp} vs {home_sp}")

            home_t = score_team(home_id, home_name, home_pid, True,  standings, date)
            away_t = score_team(away_id, away_name, away_pid, False, standings, date)

            edge     = abs(home_t["final"] - away_t["final"])
            fav, dog = (home_t, away_t) if home_t["final"] >= away_t["final"] else (away_t, home_t)

            results.append({
                "fav":      fav,
                "dog":      dog,
                "edge":     round(edge, 2),
                "label":    edge_label(edge),
                "home_sp":  home_sp,
                "away_sp":  away_sp,
            })
        except Exception as e:
            away_n = game.get("teams", {}).get("away", {}).get("team", {}).get("name", "?")
            home_n = game.get("teams", {}).get("home", {}).get("team", {}).get("name", "?")
            print(f"  [Error] {away_n} @ {home_n}: {e}")

    results.sort(key=lambda x: x["edge"], reverse=True)
    print_report(results, date)
    open_in_browser(results, date)


if __name__ == "__main__":
    main()
