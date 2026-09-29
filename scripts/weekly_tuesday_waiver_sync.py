#!/usr/bin/env python3
"""Weekly Tuesday Morning Waiver Wire Sync & Digest for Gridiron Edge AI.

Refreshes live Sleeper NFL injury/depth-chart telemetry (`/v1/players/nfl`),
24h trending waiver adds (`/v1/players/nfl/trending/add`), and live roster/FAAB
states across Carl's Sleeper leagues (`1389351355675586560`, `1389692936198819840`,
`1387700465294135296`, `1389346051961389056`), triggers `/api/refresh` on the
local War Room server (`http://127.0.0.1:8765/api/refresh`), and outputs a structured
Tuesday Morning Waiver Briefing.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logging.getLogger("ffp_agent.telemetry").setLevel(logging.WARNING)

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ffp_agent.data_providers import get_nflverse_client
from ffp_agent.tools import (
    discover_undervalued_waiver_wire_breakouts,
    fetch_live_sleeper_league_and_waiver_market,
)

CARL_LEAGUES = [
    ("1389351355675586560", "The London League (12-Team Half-PPR)"),
    ("1389692936198819840", "CClub League (12-Team PPR)"),
    ("1387700465294135296", "Top Chops (18-Team Guillotine PPR)"),
    ("1389346051961389056", "Judgey Best Ball (12-Team Half-PPR)"),
]


def ping_war_room_refresh() -> dict:
    """Trigger `/api/refresh` on the running War Room server if active."""
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8765/api/refresh",
            headers={"User-Agent": "GridironEdgeAI-WeeklySync/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "server_offline", "detail": str(exc)}
    return {"status": "unknown"}


def run_weekly_sync() -> int:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"======================================================================")
    print(f"🏈 GRIDIRON EDGE AI — TUESDAY MORNING WAIVER WIRE SYNC ({now_iso})")
    print(f"======================================================================")

    sync_stats = get_nflverse_client().refresh_live_data(force=True)
    server_ping = ping_war_room_refresh()
    print(
        f"✅ Live NFL Injury & Depth-Chart Gatekeeper Synced: "
        f"{sync_stats['active_healthy_count']} healthy active candidates | "
        f"{sync_stats['excluded_injured_or_inactive_count']} excluded (IR/PUP/Out/Inactive)"
    )
    print(f"🌐 War Room Server (http://cpcloud.c.googlers.com:8765) Refresh: {server_ping.get('status')}")
    print()

    for league_id, label in CARL_LEAGUES:
        league_res = fetch_live_sleeper_league_and_waiver_market(league_id=league_id)
        breakouts_res = discover_undervalued_waiver_wire_breakouts(
            position="ALL",
            max_rostered_pct=40.0,
            min_route_participation_pct=40.0,
            min_yprr=1.30,
            top_k=6,
            league_id=league_id,
        )
        l_data = league_res.get("data", {})
        b_data = breakouts_res.get("data", {})
        u_ctx = l_data.get("user_roster_context", {})
        rem_faab = u_ctx.get("remaining_faab_budget", 100)
        tot_faab = l_data.get("waiver_budget_total", 100)
        scale = tot_faab / 100.0

        print(f"----------------------------------------------------------------------")
        print(f"🏆 {label} [ID: {league_id}]")
        print(f"   Team: {u_ctx.get('team_name')} | Remaining FAAB: ${rem_faab}/${tot_faab}")
        print(f"   Suggested Drops: {', '.join(u_ctx.get('droppable_bench_players', [])[:3])}")
        print(f"   Top Healthy Available Waiver Breakouts (65% L4 Recency-Weighted):")

        candidates = b_data.get("breakout_candidates", [])
        for idx, c in enumerate(candidates[:5], start=1):
            sharp_pct = float(c.get("sharp_optimal_faab_pct", 5.0))
            bid_dollars = max(1, int(round((sharp_pct / 100.0) * tot_faab)))
            cons_dollars = max(1, int(round(bid_dollars * 0.55)))
            aggr_dollars = max(bid_dollars + 2, int(round(bid_dollars * 1.45)))
            print(
                f"     {idx}. {c['player_name']} ({c['team']} {c['position']} #{c.get('depth_chart_order', 1)}) "
                f"— Sharp Bid: ${bid_dollars} ({sharp_pct:.0f}% | Cons ${cons_dollars} / Aggr ${aggr_dollars}) "
                f"| L4 YPRR: {c.get('l4_yprr')} | L4 Trend: {c.get('l4_weekly_trajectory')}"
            )

        rostered_targets = b_data.get("rostered_in_league_trade_targets", [])
        if rostered_targets:
            owners_str = ", ".join(
                f"{r['player_name']} ({r.get('league_owner_team_name', 'Rostered')})"
                for r in rostered_targets[:4]
            )
            print(f"   🔒 Already Rostered in This League (Excluded from Waivers): {owners_str}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(run_weekly_sync())
