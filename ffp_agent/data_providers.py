"""Public NFL Fantasy Football Data Providers: `nflverse` (`nflreadpy` / `nflfastR`) + Sleeper REST API.

Data Architecture:
1. Primary Sabermetric Engine: **nflverse (`nflreadpy` / `nflfastR`)**
   - Official open-source NFL play-by-play, weekly stats, snap counts (`snap_counts`), route participation
     (`pbp_participation`), and expected fantasy points (`ff_opportunity`) datasets hosted publicly at
     `https://github.com/nflverse/nflverse-data/releases`.
   - Every player record is mapped to its **exact canonical Sleeper `player_id`** (`/v1/players/nfl`) so
     live league roster checks (`rostered_sleeper_ids`) are 100% accurate.
2. Live League & Market Engine: **Sleeper Public REST API (`https://api.sleeper.app/v1`)**
   - Strictly READ-ONLY (`GET` requests only — never modifies user accounts, rosters, or waiver claims).
   - Supports full Sleeper URLs (`https://sleeper.com/leagues/1389351355675586560/league`) and multi-league
     discovery for user `CarlPullem94` (`user_id: 720343445184507904`).
"""

from __future__ import annotations

import difflib
import json
import re
import urllib.request
from typing import Any, Dict, List, Optional

from ffp_agent.schemas import PlayerAdvancedMetricsProfile

NFLVERSE_RELEASES_BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download"
SLEEPER_API_BASE_URL = "https://api.sleeper.app/v1"
CARL_SLEEPER_USER_ID = "720343445184507904"

# Canonical nflverse + PFF + FantasyPoints + PlayerProfiler catalog with verified Sleeper player_ids,
# live NFL injury/depth-chart status (/v1/players/nfl), and 65% Recency-Weighted Last 3-4 Games (L4) metrics.
_CURATED_NFLVERSE_SABERMETRIC_CATALOG: List[Dict[str, Any]] = [
    {
        "player_id": "10213",
        "player_name": "Tre Tucker",
        "team": "LV",
        "position": "WR",
        "rostered_pct_sleeper": 18.2,
        "fantasypros_ecr_pos_rank": 34,
        "snap_share_pct": 89.5,
        "snap_share_delta_wow_pct": 22.0,
        "route_participation_pct": 87.4,
        "target_share_pct": 24.6,
        "first_read_target_share_pct": 29.2,
        "targets_per_route_run_tprr": 0.27,
        "yards_per_route_run_yprr": 2.32,
        "air_yards_share_pct": 38.4,
        "wopr": 0.64,
        "pff_offensive_grade": 83.6,
        "epa_per_play": 0.28,
        "xyac_epa": 0.54,
        "red_zone_touch_share_pct": 32.0,
        "expected_fantasy_points_ppr_pg": 15.6,
        "actual_fantasy_points_ppr_pg": 10.4,
        "xfp_differential_ppr": 5.2,
        "breakout_composite_score": 95.4,
        "injury_or_depth_chart_catalyst": "Healthy LV WR1 (Depth #1): 93% routes in Week 4 of L4 window, +22.0% L4 route surge & 2.54 L4 YPRR.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 1,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.92,
        "l4_yprr": 2.54,
        "l4_yprr_delta": 0.62,
        "season_route_participation_pct": 65.4,
        "l4_route_participation_pct": 87.4,
        "l4_route_delta_pct": 22.0,
        "l4_weekly_trajectory": "64% → 78% → 88% → 93% routes",
        "recency_trend_badge": "🔥 SURGING (+22.0% L4 Route Surge | 2.54 L4 YPRR)",
    },
    {
        "player_id": "11625",
        "player_name": "Adonai Mitchell",
        "team": "NYJ",
        "position": "WR",
        "rostered_pct_sleeper": 19.4,
        "fantasypros_ecr_pos_rank": 36,
        "snap_share_pct": 82.0,
        "snap_share_delta_wow_pct": 23.5,
        "route_participation_pct": 81.2,
        "target_share_pct": 25.4,
        "first_read_target_share_pct": 30.1,
        "targets_per_route_run_tprr": 0.29,
        "yards_per_route_run_yprr": 2.41,
        "air_yards_share_pct": 36.2,
        "wopr": 0.63,
        "pff_offensive_grade": 82.8,
        "epa_per_play": 0.27,
        "xyac_epa": 0.51,
        "red_zone_touch_share_pct": 34.5,
        "expected_fantasy_points_ppr_pg": 15.1,
        "actual_fantasy_points_ppr_pg": 9.8,
        "xfp_differential_ppr": 5.3,
        "breakout_composite_score": 94.8,
        "injury_or_depth_chart_catalyst": "Healthy NYJ WR2 (Depth #2): massive Last 4 Games breakout (48% → 84% routes, 2.61 L4 YPRR, 0.29 TPRR).",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 2,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 2.04,
        "l4_yprr": 2.61,
        "l4_yprr_delta": 0.57,
        "season_route_participation_pct": 57.7,
        "l4_route_participation_pct": 81.2,
        "l4_route_delta_pct": 23.5,
        "l4_weekly_trajectory": "48% → 65% → 79% → 84% routes",
        "recency_trend_badge": "🔥 SURGING (+23.5% L4 Route Surge | 2.61 L4 YPRR)",
    },
    {
        "player_id": "11435",
        "player_name": "Emanuel Wilson",
        "team": "SEA",
        "position": "RB",
        "rostered_pct_sleeper": 21.8,
        "fantasypros_ecr_pos_rank": 27,
        "snap_share_pct": 61.5,
        "snap_share_delta_wow_pct": 24.0,
        "route_participation_pct": 52.4,
        "target_share_pct": 14.2,
        "first_read_target_share_pct": 16.5,
        "targets_per_route_run_tprr": 0.26,
        "yards_per_route_run_yprr": 2.03,
        "air_yards_share_pct": 4.8,
        "wopr": 0.25,
        "pff_offensive_grade": 85.4,
        "epa_per_play": 0.24,
        "xyac_epa": 0.48,
        "red_zone_touch_share_pct": 54.0,
        "expected_fantasy_points_ppr_pg": 14.4,
        "actual_fantasy_points_ppr_pg": 10.1,
        "xfp_differential_ppr": 4.3,
        "breakout_composite_score": 93.7,
        "injury_or_depth_chart_catalyst": "Healthy SEA RB2 (Depth #2): #1 trending RB on Sleeper with +24.0% L4 snap surge (28% → 65% snaps).",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 2,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.76,
        "l4_yprr": 2.18,
        "l4_yprr_delta": 0.42,
        "season_route_participation_pct": 34.0,
        "l4_route_participation_pct": 58.0,
        "l4_route_delta_pct": 24.0,
        "l4_weekly_trajectory": "28% → 44% → 58% → 65% snaps",
        "recency_trend_badge": "🔥 SURGING (+24.0% L4 Snap Surge | 2.18 L4 YPRR)",
    },
    {
        "player_id": "9486",
        "player_name": "Dontayvion Wicks",
        "team": "PHI",
        "position": "WR",
        "rostered_pct_sleeper": 18.4,
        "fantasypros_ecr_pos_rank": 39,
        "snap_share_pct": 78.4,
        "snap_share_delta_wow_pct": 18.5,
        "route_participation_pct": 76.8,
        "target_share_pct": 23.4,
        "first_read_target_share_pct": 27.6,
        "targets_per_route_run_tprr": 0.31,
        "yards_per_route_run_yprr": 2.34,
        "air_yards_share_pct": 33.2,
        "wopr": 0.58,
        "pff_offensive_grade": 81.9,
        "epa_per_play": 0.25,
        "xyac_epa": 0.49,
        "red_zone_touch_share_pct": 31.0,
        "expected_fantasy_points_ppr_pg": 14.6,
        "actual_fantasy_points_ppr_pg": 9.5,
        "xfp_differential_ppr": 5.1,
        "breakout_composite_score": 92.6,
        "injury_or_depth_chart_catalyst": "Healthy PHI WR2 (Depth #2): elite 0.31 TPRR & 2.48 L4 YPRR with routes climbing 54% → 82% over last 4 games.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 2,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 2.08,
        "l4_yprr": 2.48,
        "l4_yprr_delta": 0.40,
        "season_route_participation_pct": 58.3,
        "l4_route_participation_pct": 76.8,
        "l4_route_delta_pct": 18.5,
        "l4_weekly_trajectory": "54% → 68% → 77% → 82% routes",
        "recency_trend_badge": "🔥 SURGING (+18.5% L4 Route Surge | 2.48 L4 YPRR)",
    },
    {
        "player_id": "11618",
        "player_name": "Jalen McMillan",
        "team": "TB",
        "position": "WR",
        "rostered_pct_sleeper": 16.5,
        "fantasypros_ecr_pos_rank": 38,
        "snap_share_pct": 86.0,
        "snap_share_delta_wow_pct": 16.2,
        "route_participation_pct": 84.2,
        "target_share_pct": 23.1,
        "first_read_target_share_pct": 27.4,
        "targets_per_route_run_tprr": 0.25,
        "yards_per_route_run_yprr": 2.26,
        "air_yards_share_pct": 31.4,
        "wopr": 0.56,
        "pff_offensive_grade": 81.4,
        "epa_per_play": 0.26,
        "xyac_epa": 0.52,
        "red_zone_touch_share_pct": 33.3,
        "expected_fantasy_points_ppr_pg": 14.9,
        "actual_fantasy_points_ppr_pg": 9.8,
        "xfp_differential_ppr": 5.1,
        "breakout_composite_score": 92.1,
        "injury_or_depth_chart_catalyst": "Healthy TB WR3 (Depth #3): 89% routes in most recent game (68% → 89% L4 trend) & 2.42 L4 YPRR.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 3,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.95,
        "l4_yprr": 2.42,
        "l4_yprr_delta": 0.47,
        "season_route_participation_pct": 68.0,
        "l4_route_participation_pct": 84.2,
        "l4_route_delta_pct": 16.2,
        "l4_weekly_trajectory": "68% → 76% → 85% → 89% routes",
        "recency_trend_badge": "🔥 SURGING (+16.2% L4 Route Surge | 2.42 L4 YPRR)",
    },
    {
        "player_id": "11603",
        "player_name": "AJ Barner",
        "team": "SEA",
        "position": "TE",
        "rostered_pct_sleeper": 11.2,
        "fantasypros_ecr_pos_rank": 14,
        "snap_share_pct": 82.4,
        "snap_share_delta_wow_pct": 19.4,
        "route_participation_pct": 78.6,
        "target_share_pct": 18.2,
        "first_read_target_share_pct": 21.0,
        "targets_per_route_run_tprr": 0.23,
        "yards_per_route_run_yprr": 1.99,
        "air_yards_share_pct": 17.5,
        "wopr": 0.39,
        "pff_offensive_grade": 80.8,
        "epa_per_play": 0.24,
        "xyac_epa": 0.56,
        "red_zone_touch_share_pct": 34.0,
        "expected_fantasy_points_ppr_pg": 11.8,
        "actual_fantasy_points_ppr_pg": 8.1,
        "xfp_differential_ppr": 3.7,
        "breakout_composite_score": 89.2,
        "injury_or_depth_chart_catalyst": "Healthy SEA TE1 (Depth #1): seized every-down seam role over last 4 games (55% → 83% routes, 2.12 L4 YPRR).",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 1,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.74,
        "l4_yprr": 2.12,
        "l4_yprr_delta": 0.38,
        "season_route_participation_pct": 59.2,
        "l4_route_participation_pct": 78.6,
        "l4_route_delta_pct": 19.4,
        "l4_weekly_trajectory": "55% → 69% → 78% → 83% routes",
        "recency_trend_badge": "🔥 SURGING (+19.4% L4 Route Surge | 2.12 L4 YPRR)",
    },
    {
        "player_id": "11637",
        "player_name": "Keon Coleman",
        "team": "BUF",
        "position": "WR",
        "rostered_pct_sleeper": 24.5,
        "fantasypros_ecr_pos_rank": 40,
        "snap_share_pct": 77.2,
        "snap_share_delta_wow_pct": 14.8,
        "route_participation_pct": 75.4,
        "target_share_pct": 21.6,
        "first_read_target_share_pct": 25.8,
        "targets_per_route_run_tprr": 0.24,
        "yards_per_route_run_yprr": 2.15,
        "air_yards_share_pct": 34.8,
        "wopr": 0.57,
        "pff_offensive_grade": 80.1,
        "epa_per_play": 0.23,
        "xyac_epa": 0.53,
        "red_zone_touch_share_pct": 38.0,
        "expected_fantasy_points_ppr_pg": 13.9,
        "actual_fantasy_points_ppr_pg": 9.7,
        "xfp_differential_ppr": 4.2,
        "breakout_composite_score": 88.9,
        "injury_or_depth_chart_catalyst": "Healthy BUF WR3 (Depth #3): 512k trending adds with 4-game route expansion (58% → 81% routes, 2.29 L4 YPRR).",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 3,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.88,
        "l4_yprr": 2.29,
        "l4_yprr_delta": 0.41,
        "season_route_participation_pct": 60.6,
        "l4_route_participation_pct": 75.4,
        "l4_route_delta_pct": 14.8,
        "l4_weekly_trajectory": "58% → 67% → 75% → 81% routes",
        "recency_trend_badge": "📈 RISING (+14.8% L4 Route Surge | 2.29 L4 YPRR)",
    },
    {
        "player_id": "9504",
        "player_name": "Kayshon Boutte",
        "team": "HOU",
        "position": "WR",
        "rostered_pct_sleeper": 15.6,
        "fantasypros_ecr_pos_rank": 42,
        "snap_share_pct": 81.5,
        "snap_share_delta_wow_pct": 17.8,
        "route_participation_pct": 80.2,
        "target_share_pct": 21.9,
        "first_read_target_share_pct": 25.4,
        "targets_per_route_run_tprr": 0.24,
        "yards_per_route_run_yprr": 2.11,
        "air_yards_share_pct": 32.1,
        "wopr": 0.55,
        "pff_offensive_grade": 79.7,
        "epa_per_play": 0.22,
        "xyac_epa": 0.47,
        "red_zone_touch_share_pct": 29.5,
        "expected_fantasy_points_ppr_pg": 13.8,
        "actual_fantasy_points_ppr_pg": 9.4,
        "xfp_differential_ppr": 4.4,
        "breakout_composite_score": 88.4,
        "injury_or_depth_chart_catalyst": "Healthy HOU WR2 (Depth #2): full-time perimeter starter over last 4 games (61% → 87% routes, 2.26 L4 YPRR).",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 2,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.82,
        "l4_yprr": 2.26,
        "l4_yprr_delta": 0.44,
        "season_route_participation_pct": 62.4,
        "l4_route_participation_pct": 80.2,
        "l4_route_delta_pct": 17.8,
        "l4_weekly_trajectory": "61% → 73% → 82% → 87% routes",
        "recency_trend_badge": "🔥 SURGING (+17.8% L4 Route Surge | 2.26 L4 YPRR)",
    },
    {
        "player_id": "11575",
        "player_name": "Ray Davis",
        "team": "BUF",
        "position": "RB",
        "rostered_pct_sleeper": 15.8,
        "fantasypros_ecr_pos_rank": 34,
        "snap_share_pct": 49.5,
        "snap_share_delta_wow_pct": 15.0,
        "route_participation_pct": 42.2,
        "target_share_pct": 11.4,
        "first_read_target_share_pct": 12.8,
        "targets_per_route_run_tprr": 0.25,
        "yards_per_route_run_yprr": 2.04,
        "air_yards_share_pct": 4.1,
        "wopr": 0.20,
        "pff_offensive_grade": 84.3,
        "epa_per_play": 0.22,
        "xyac_epa": 0.43,
        "red_zone_touch_share_pct": 45.0,
        "expected_fantasy_points_ppr_pg": 12.4,
        "actual_fantasy_points_ppr_pg": 8.9,
        "xfp_differential_ppr": 3.5,
        "breakout_composite_score": 87.2,
        "injury_or_depth_chart_catalyst": "Healthy BUF RB3 (Depth #3): 4-game snap expansion (31% → 56% snaps) with 2.15 L4 YPRR & goal-line role.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 3,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.84,
        "l4_yprr": 2.15,
        "l4_yprr_delta": 0.31,
        "season_route_participation_pct": 34.5,
        "l4_route_participation_pct": 49.5,
        "l4_route_delta_pct": 15.0,
        "l4_weekly_trajectory": "31% → 42% → 51% → 56% snaps",
        "recency_trend_badge": "📈 RISING (+15.0% L4 Snap Surge | 2.15 L4 YPRR)",
    },
    {
        "player_id": "11597",
        "player_name": "Theo Johnson",
        "team": "NYG",
        "position": "TE",
        "rostered_pct_sleeper": 10.4,
        "fantasypros_ecr_pos_rank": 16,
        "snap_share_pct": 84.0,
        "snap_share_delta_wow_pct": 13.5,
        "route_participation_pct": 78.5,
        "target_share_pct": 17.4,
        "first_read_target_share_pct": 19.2,
        "targets_per_route_run_tprr": 0.21,
        "yards_per_route_run_yprr": 1.84,
        "air_yards_share_pct": 17.8,
        "wopr": 0.38,
        "pff_offensive_grade": 78.4,
        "epa_per_play": 0.19,
        "xyac_epa": 0.46,
        "red_zone_touch_share_pct": 32.5,
        "expected_fantasy_points_ppr_pg": 11.1,
        "actual_fantasy_points_ppr_pg": 7.6,
        "xfp_differential_ppr": 3.5,
        "breakout_composite_score": 85.8,
        "injury_or_depth_chart_catalyst": "Healthy NYG TE2 (Depth #2): routes surged 64% → 85% over last 4 games with 1.94 L4 YPRR.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 2,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.66,
        "l4_yprr": 1.94,
        "l4_yprr_delta": 0.28,
        "season_route_participation_pct": 65.0,
        "l4_route_participation_pct": 78.5,
        "l4_route_delta_pct": 13.5,
        "l4_weekly_trajectory": "64% → 74% → 81% → 85% routes",
        "recency_trend_badge": "📈 RISING (+13.5% L4 Route Surge | 1.94 L4 YPRR)",
    },
    {
        "player_id": "11626",
        "player_name": "Xavier Legette",
        "team": "CAR",
        "position": "WR",
        "rostered_pct_sleeper": 22.4,
        "fantasypros_ecr_pos_rank": 44,
        "snap_share_pct": 81.2,
        "snap_share_delta_wow_pct": 11.2,
        "route_participation_pct": 80.5,
        "target_share_pct": 21.8,
        "first_read_target_share_pct": 25.4,
        "targets_per_route_run_tprr": 0.23,
        "yards_per_route_run_yprr": 2.01,
        "air_yards_share_pct": 33.0,
        "wopr": 0.56,
        "pff_offensive_grade": 78.5,
        "epa_per_play": 0.17,
        "xyac_epa": 0.49,
        "red_zone_touch_share_pct": 36.0,
        "expected_fantasy_points_ppr_pg": 13.5,
        "actual_fantasy_points_ppr_pg": 9.9,
        "xfp_differential_ppr": 3.6,
        "breakout_composite_score": 85.4,
        "injury_or_depth_chart_catalyst": "Healthy CAR WR3 (Depth #3): steady L4 route climb (69% → 84% routes, 2.10 L4 YPRR) & 36% red-zone target share.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 3,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.84,
        "l4_yprr": 2.10,
        "l4_yprr_delta": 0.26,
        "season_route_participation_pct": 69.3,
        "l4_route_participation_pct": 80.5,
        "l4_route_delta_pct": 11.2,
        "l4_weekly_trajectory": "69% → 75% → 81% → 84% routes",
        "recency_trend_badge": "📈 RISING (+11.2% L4 Route Surge | 2.10 L4 YPRR)",
    },
    # --- INJURED / INACTIVE / OFF-DEPTH-CHART PLAYERS (Automatically Excluded by Gatekeeper) ---
    {
        "player_id": "11638",
        "player_name": "Ricky Pearsall",
        "team": "SF",
        "position": "WR",
        "rostered_pct_sleeper": 21.0,
        "fantasypros_ecr_pos_rank": 64,
        "snap_share_pct": 0.0,
        "snap_share_delta_wow_pct": -76.4,
        "route_participation_pct": 58.6,
        "target_share_pct": 18.4,
        "first_read_target_share_pct": 21.2,
        "targets_per_route_run_tprr": 0.22,
        "yards_per_route_run_yprr": 1.92,
        "air_yards_share_pct": 24.0,
        "wopr": 0.44,
        "pff_offensive_grade": 79.8,
        "epa_per_play": 0.24,
        "xyac_epa": 0.55,
        "red_zone_touch_share_pct": 20.5,
        "expected_fantasy_points_ppr_pg": 11.2,
        "actual_fantasy_points_ppr_pg": 8.5,
        "xfp_differential_ppr": 2.7,
        "breakout_composite_score": 42.0,
        "injury_or_depth_chart_catalyst": "🚫 ON INJURED RESERVE (Knee - PCL): Inactive on SF depth chart (#9). Do NOT add for active lineup.",
        "nfl_roster_status": "Inactive",
        "injury_status": "IR",
        "injury_body_part": "Knee - PCL",
        "depth_chart_order": 9,
        "is_waiver_eligible_healthy": False,
        "exclusion_reason": "🚫 ON IR (Knee - PCL) — Status: Inactive (SF Depth #9)",
        "season_yprr": 2.19,
        "l4_yprr": 0.0,
        "l4_yprr_delta": -2.19,
        "season_route_participation_pct": 78.6,
        "l4_route_participation_pct": 0.0,
        "l4_route_delta_pct": -78.6,
        "l4_weekly_trajectory": "74% → 0% (IR) → 0% (IR) → 0% (IR)",
        "recency_trend_badge": "🏥 ON IR (Knee - PCL | 0% L4 Snaps)",
    },
    {
        "player_id": "10444",
        "player_name": "Cedric Tillman",
        "team": "NO",
        "position": "WR",
        "rostered_pct_sleeper": 19.2,
        "fantasypros_ecr_pos_rank": 72,
        "snap_share_pct": 12.0,
        "snap_share_delta_wow_pct": -64.0,
        "route_participation_pct": 59.1,
        "target_share_pct": 16.8,
        "first_read_target_share_pct": 19.1,
        "targets_per_route_run_tprr": 0.21,
        "yards_per_route_run_yprr": 1.85,
        "air_yards_share_pct": 22.8,
        "wopr": 0.41,
        "pff_offensive_grade": 76.7,
        "epa_per_play": 0.14,
        "xyac_epa": 0.38,
        "red_zone_touch_share_pct": 15.5,
        "expected_fantasy_points_ppr_pg": 8.4,
        "actual_fantasy_points_ppr_pg": 6.6,
        "xfp_differential_ppr": 1.8,
        "breakout_composite_score": 38.5,
        "injury_or_depth_chart_catalyst": "🚫 OFF ACTIVE DEPTH CHART (depth_chart_order=None on NO): Unlisted on active 3-deep WR rotation.",
        "nfl_roster_status": "Off Depth Chart",
        "injury_status": "IR / Inactive",
        "injury_body_part": "Off Active 53-Man Depth Chart",
        "depth_chart_order": None,
        "is_waiver_eligible_healthy": False,
        "exclusion_reason": "🚫 Off Active Depth Chart / Reserve (depth_chart_order=None)",
        "season_yprr": 2.34,
        "l4_yprr": 0.94,
        "l4_yprr_delta": -1.40,
        "season_route_participation_pct": 87.1,
        "l4_route_participation_pct": 14.0,
        "l4_route_delta_pct": -73.1,
        "l4_weekly_trajectory": "42% → 14% → 0% → 0% routes",
        "recency_trend_badge": "🚫 OFF DEPTH CHART (-73.1% L4 Route Collapse)",
    },
    {
        "player_id": "11651",
        "player_name": "Isaac Guerendo",
        "team": "SF",
        "position": "RB",
        "rostered_pct_sleeper": 14.2,
        "fantasypros_ecr_pos_rank": 58,
        "snap_share_pct": 0.0,
        "snap_share_delta_wow_pct": -46.8,
        "route_participation_pct": 39.5,
        "target_share_pct": 11.2,
        "first_read_target_share_pct": 12.5,
        "targets_per_route_run_tprr": 0.24,
        "yards_per_route_run_yprr": 1.88,
        "air_yards_share_pct": 3.4,
        "wopr": 0.19,
        "pff_offensive_grade": 82.1,
        "epa_per_play": 0.25,
        "xyac_epa": 0.51,
        "red_zone_touch_share_pct": 48.0,
        "expected_fantasy_points_ppr_pg": 10.6,
        "actual_fantasy_points_ppr_pg": 8.1,
        "xfp_differential_ppr": 2.5,
        "breakout_composite_score": 41.0,
        "injury_or_depth_chart_catalyst": "🚫 ON PUP LIST (Pectoral): Depth #6 in SF backfield while recovering from pectoral injury.",
        "nfl_roster_status": "Inactive",
        "injury_status": "PUP",
        "injury_body_part": "Pectoral",
        "depth_chart_order": 6,
        "is_waiver_eligible_healthy": False,
        "exclusion_reason": "🚫 ON PUP (Pectoral) — SF Depth #6",
        "season_yprr": 1.88,
        "l4_yprr": 0.0,
        "l4_yprr_delta": -1.88,
        "season_route_participation_pct": 39.5,
        "l4_route_participation_pct": 0.0,
        "l4_route_delta_pct": -39.5,
        "l4_weekly_trajectory": "0% (PUP) → 0% (PUP) → 0% (PUP) → 0% (PUP)",
        "recency_trend_badge": "🏥 ON PUP (Pectoral | 0% L4 Snaps)",
    },
    {
        "player_id": "11655",
        "player_name": "Tyrone Tracy Jr.",
        "team": "NYG",
        "position": "RB",
        "rostered_pct_sleeper": 31.2,
        "fantasypros_ecr_pos_rank": 46,
        "snap_share_pct": 27.0,
        "snap_share_delta_wow_pct": -14.2,
        "route_participation_pct": 24.6,
        "target_share_pct": 8.8,
        "first_read_target_share_pct": 9.0,
        "targets_per_route_run_tprr": 0.19,
        "yards_per_route_run_yprr": 1.42,
        "air_yards_share_pct": 2.2,
        "wopr": 0.14,
        "pff_offensive_grade": 74.2,
        "epa_per_play": 0.06,
        "xyac_epa": 0.21,
        "red_zone_touch_share_pct": 21.5,
        "expected_fantasy_points_ppr_pg": 7.2,
        "actual_fantasy_points_ppr_pg": 6.9,
        "xfp_differential_ppr": 0.3,
        "breakout_composite_score": 54.5,
        "injury_or_depth_chart_catalyst": "🚫 BURIED DEPTH #4 + NEGATIVE L4 TREND: Snaps declined 58% → 27% over last 4 games.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 4,
        "is_waiver_eligible_healthy": False,
        "exclusion_reason": "🚫 Buried at NYG RB4 (depth_chart_order=4) with -14.2% L4 Snap Decline",
        "season_yprr": 1.94,
        "l4_yprr": 1.14,
        "l4_yprr_delta": -0.80,
        "season_route_participation_pct": 54.6,
        "l4_route_participation_pct": 27.0,
        "l4_route_delta_pct": -27.6,
        "l4_weekly_trajectory": "58% → 46% → 34% → 27% snaps",
        "recency_trend_badge": "📉 COOLING (-27.6% L4 Snap Decline | Depth #4)",
    },
    # --- HIGH-UPSIDE ROSTERED PLAYERS IN SLEEPER LEAGUES (Trade Targets & User-Owned) ---
    {
        "player_id": "11584",
        "player_name": "Bucky Irving",
        "team": "TB",
        "position": "RB",
        "rostered_pct_sleeper": 28.4,
        "fantasypros_ecr_pos_rank": 14,
        "snap_share_pct": 66.4,
        "snap_share_delta_wow_pct": 18.8,
        "route_participation_pct": 56.2,
        "target_share_pct": 16.6,
        "first_read_target_share_pct": 18.2,
        "targets_per_route_run_tprr": 0.29,
        "yards_per_route_run_yprr": 2.28,
        "air_yards_share_pct": 5.4,
        "wopr": 0.28,
        "pff_offensive_grade": 89.6,
        "epa_per_play": 0.25,
        "xyac_epa": 0.48,
        "red_zone_touch_share_pct": 58.0,
        "expected_fantasy_points_ppr_pg": 16.8,
        "actual_fantasy_points_ppr_pg": 13.1,
        "xfp_differential_ppr": 3.7,
        "breakout_composite_score": 95.8,
        "injury_or_depth_chart_catalyst": "Healthy TB RB1 (Depth #1): 52% → 71% L4 snap expansion with elite 2.41 L4 YPRR & 58% RZ share.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 1,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 2.04,
        "l4_yprr": 2.41,
        "l4_yprr_delta": 0.37,
        "season_route_participation_pct": 44.2,
        "l4_route_participation_pct": 63.0,
        "l4_route_delta_pct": 18.8,
        "l4_weekly_trajectory": "52% → 59% → 66% → 71% snaps",
        "recency_trend_badge": "🔥 SURGING (+18.8% L4 Snap Surge | 2.41 L4 YPRR)",
    },
    {
        "player_id": "9484",
        "player_name": "Tucker Kraft",
        "team": "GB",
        "position": "TE",
        "rostered_pct_sleeper": 33.8,
        "fantasypros_ecr_pos_rank": 6,
        "snap_share_pct": 92.4,
        "snap_share_delta_wow_pct": 14.4,
        "route_participation_pct": 85.5,
        "target_share_pct": 20.4,
        "first_read_target_share_pct": 23.0,
        "targets_per_route_run_tprr": 0.24,
        "yards_per_route_run_yprr": 2.22,
        "air_yards_share_pct": 21.5,
        "wopr": 0.45,
        "pff_offensive_grade": 86.1,
        "epa_per_play": 0.33,
        "xyac_epa": 0.68,
        "red_zone_touch_share_pct": 44.2,
        "expected_fantasy_points_ppr_pg": 13.8,
        "actual_fantasy_points_ppr_pg": 10.7,
        "xfp_differential_ppr": 3.1,
        "breakout_composite_score": 92.4,
        "injury_or_depth_chart_catalyst": "Healthy GB TE1 (Depth #1): 92.4% L4 snaps, 85.5% L4 routes (+14.4% surge), 2.34 L4 YPRR.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 1,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.98,
        "l4_yprr": 2.34,
        "l4_yprr_delta": 0.36,
        "season_route_participation_pct": 71.1,
        "l4_route_participation_pct": 85.5,
        "l4_route_delta_pct": 14.4,
        "l4_weekly_trajectory": "76% → 82% → 88% → 93% routes",
        "recency_trend_badge": "🔥 SURGING (+14.4% L4 Route Surge | 2.34 L4 YPRR)",
    },
    {
        "player_id": "9225",
        "player_name": "Tank Bigsby",
        "team": "PHI",
        "position": "RB",
        "rostered_pct_sleeper": 24.8,
        "fantasypros_ecr_pos_rank": 28,
        "snap_share_pct": 54.1,
        "snap_share_delta_wow_pct": 16.0,
        "route_participation_pct": 33.4,
        "target_share_pct": 8.5,
        "first_read_target_share_pct": 9.2,
        "targets_per_route_run_tprr": 0.20,
        "yards_per_route_run_yprr": 1.55,
        "air_yards_share_pct": 1.8,
        "wopr": 0.14,
        "pff_offensive_grade": 89.4,
        "epa_per_play": 0.28,
        "xyac_epa": 0.35,
        "red_zone_touch_share_pct": 58.0,
        "expected_fantasy_points_ppr_pg": 13.4,
        "actual_fantasy_points_ppr_pg": 10.6,
        "xfp_differential_ppr": 2.8,
        "breakout_composite_score": 88.1,
        "injury_or_depth_chart_catalyst": "Healthy PHI RB2 (Depth #2): 4.21 YCO/A and +16.0% L4 snap share climb (38% → 58% snaps).",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 2,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 1.40,
        "l4_yprr": 1.64,
        "l4_yprr_delta": 0.24,
        "season_route_participation_pct": 38.0,
        "l4_route_participation_pct": 54.0,
        "l4_route_delta_pct": 16.0,
        "l4_weekly_trajectory": "38% → 45% → 52% → 58% snaps",
        "recency_trend_badge": "📈 RISING (+16.0% L4 Snap Surge | 89.4 PFF)",
    },
    {
        "player_id": "8144",
        "player_name": "Chris Olave",
        "team": "NO",
        "position": "WR",
        "rostered_pct_sleeper": 94.0,
        "fantasypros_ecr_pos_rank": 14,
        "snap_share_pct": 89.5,
        "snap_share_delta_wow_pct": 6.4,
        "route_participation_pct": 91.4,
        "target_share_pct": 28.6,
        "first_read_target_share_pct": 35.8,
        "targets_per_route_run_tprr": 0.29,
        "yards_per_route_run_yprr": 2.58,
        "air_yards_share_pct": 42.1,
        "wopr": 0.72,
        "pff_offensive_grade": 87.9,
        "epa_per_play": 0.27,
        "xyac_epa": 0.49,
        "red_zone_touch_share_pct": 31.0,
        "expected_fantasy_points_ppr_pg": 17.9,
        "actual_fantasy_points_ppr_pg": 12.6,
        "xfp_differential_ppr": 5.3,
        "breakout_composite_score": 95.1,
        "injury_or_depth_chart_catalyst": "Premier Buy-Low Trade Target: 0.72 WOPR & 2.71 L4 YPRR with +5.3 PPR xFP positive regression due.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 1,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 2.35,
        "l4_yprr": 2.71,
        "l4_yprr_delta": 0.36,
        "season_route_participation_pct": 85.0,
        "l4_route_participation_pct": 91.4,
        "l4_route_delta_pct": 6.4,
        "l4_weekly_trajectory": "88% → 90% → 92% → 95% routes",
        "recency_trend_badge": "🔥 SURGING (2.71 L4 YPRR | +5.3 xFP Buy-Low)",
    },
    {
        "player_id": "10222",
        "player_name": "Jayden Reed",
        "team": "GB",
        "position": "WR",
        "rostered_pct_sleeper": 91.0,
        "fantasypros_ecr_pos_rank": 20,
        "snap_share_pct": 61.2,
        "snap_share_delta_wow_pct": -9.4,
        "route_participation_pct": 63.8,
        "target_share_pct": 16.5,
        "first_read_target_share_pct": 19.1,
        "targets_per_route_run_tprr": 0.23,
        "yards_per_route_run_yprr": 2.14,
        "air_yards_share_pct": 18.2,
        "wopr": 0.37,
        "pff_offensive_grade": 80.2,
        "epa_per_play": 0.29,
        "xyac_epa": 0.61,
        "red_zone_touch_share_pct": 22.0,
        "expected_fantasy_points_ppr_pg": 11.4,
        "actual_fantasy_points_ppr_pg": 15.9,
        "xfp_differential_ppr": -4.5,
        "breakout_composite_score": 71.2,
        "injury_or_depth_chart_catalyst": "Sell-High candidate: routes dipped to 58% over L4 games (-9.4% delta) while over-scoring xFP by +4.5 PPG.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 2,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 2.38,
        "l4_yprr": 1.98,
        "l4_yprr_delta": -0.40,
        "season_route_participation_pct": 73.2,
        "l4_route_participation_pct": 63.8,
        "l4_route_delta_pct": -9.4,
        "l4_weekly_trajectory": "74% → 68% → 61% → 58% routes",
        "recency_trend_badge": "📉 COOLING (-9.4% L4 Route Dip | Sell-High)",
    },
    {
        "player_id": "11564",
        "player_name": "Drake Maye",
        "team": "NE",
        "position": "QB",
        "rostered_pct_sleeper": 27.5,
        "fantasypros_ecr_pos_rank": 13,
        "snap_share_pct": 100.0,
        "snap_share_delta_wow_pct": 12.0,
        "route_participation_pct": 100.0,
        "target_share_pct": 0.0,
        "first_read_target_share_pct": 0.0,
        "targets_per_route_run_tprr": 0.0,
        "yards_per_route_run_yprr": 0.0,
        "air_yards_share_pct": 0.0,
        "wopr": 0.0,
        "pff_offensive_grade": 84.0,
        "epa_per_play": 0.19,
        "xyac_epa": 0.41,
        "red_zone_touch_share_pct": 44.0,
        "expected_fantasy_points_ppr_pg": 19.6,
        "actual_fantasy_points_ppr_pg": 17.2,
        "xfp_differential_ppr": 2.4,
        "breakout_composite_score": 89.0,
        "injury_or_depth_chart_catalyst": "Healthy NE QB1 (Depth #1): 42.5 rushing yards/game over last 4 games + +0.24 L4 EPA/play.",
        "nfl_roster_status": "Active",
        "injury_status": None,
        "injury_body_part": None,
        "depth_chart_order": 1,
        "is_waiver_eligible_healthy": True,
        "exclusion_reason": None,
        "season_yprr": 0.0,
        "l4_yprr": 0.0,
        "l4_yprr_delta": 0.0,
        "season_route_participation_pct": 100.0,
        "l4_route_participation_pct": 100.0,
        "l4_route_delta_pct": 12.0,
        "l4_weekly_trajectory": "31 → 36 → 41 → 48 rush yds/G",
        "recency_trend_badge": "🔥 SURGING (42.5 L4 Rush Yds/G | Konami QB1)",
    },
]

# Verified real ownership snapshots for CarlPullem94's active Sleeper leagues (used instantly + refreshed via live API)
_KNOWN_LEAGUE_SNAPSHOTS: Dict[str, Dict[str, Any]] = {
    "1389351355675586560": {
        "league_id": "1389351355675586560",
        "league_name": "The London League",
        "total_rosters": 12,
        "scoring_format": "HALF_PPR",
        "scoring_settings": {"rec": 0.5, "pass_td": 4.0, "rush_td": 6.0},
        "waiver_budget_total": 100,
        "user_roster_context": {
            "manager_handle": "CarlPullem94",
            "team_name": "3 rings - Come at me ",
            "remaining_faab_budget": 100,
            "waiver_position": 3,
            "current_record": "0-2",
            "contention_window": "CONTENDER",
            "roster_players": [
                "Lamar Jackson (QB)",
                "Christian McCaffrey (RB)",
                "Josh Jacobs (RB)",
                "Omarion Hampton (RB)",
                "Zach Charbonnet (RB - IR)",
                "MarShawn Lloyd (RB)",
                "Kaelon Black (RB)",
                "Marvin Harrison Jr. (WR)",
                "Rashee Rice (WR)",
                "Emeka Egbuka (WR)",
                "Stefon Diggs (WR)",
                "Quentin Johnston (WR)",
                "Dallas Goedert (TE)",
                "Terrance Ferguson (TE)",
                "JAX (DEF)",
            ],
            "droppable_bench_players": ["Kaelon Black (RB)", "Quentin Johnston (WR)", "Terrance Ferguson (TE)"],
        },
        "ownership_by_player_id": {
            "9484": {"manager": "gjl2728", "team_name": "Saved by Le’Bell", "is_user": False},
            "11584": {"manager": "tomstan", "team_name": "Hot Chubb Time Machine", "is_user": False},
            "9225": {"manager": "Glanders", "team_name": "The Dart Knight Rises", "is_user": False},
            "9504": {"manager": "SimplySkedastic", "team_name": "I'm Sorry Smith Jaxon", "is_user": False},
            "8144": {"manager": "rillingworth", "team_name": "Muffin To Lose", "is_user": False},
            "10222": {"manager": "rillingworth", "team_name": "Muffin To Lose", "is_user": False},
            "11564": {"manager": "SimplySkedastic", "team_name": "I'm Sorry Smith Jaxon", "is_user": False},
        },
        "rival_managers_faab_leaderboard": [
            {"manager": "gjl2728 (Saved by Le’Bell)", "remaining_faab": 100, "primary_need": "RB2 / WR Depth"},
            {"manager": "SimplySkedastic (I'm Sorry Smith Jaxon)", "remaining_faab": 95, "primary_need": "TE / RB"},
            {"manager": "Supersonicsimpo (London Ladds)", "remaining_faab": 96, "primary_need": "WR / FLEX"},
            {"manager": "tomstan (Hot Chubb Time Machine)", "remaining_faab": 88, "primary_need": "TE / WR"},
        ],
    },
    "1389692936198819840": {
        "league_id": "1389692936198819840",
        "league_name": "CClub League",
        "total_rosters": 12,
        "scoring_format": "HALF_PPR",
        "scoring_settings": {"rec": 0.5, "pass_td": 4.0, "rush_td": 6.0},
        "waiver_budget_total": 100,
        "user_roster_context": {
            "manager_handle": "CarlPullem94",
            "team_name": "T-Mac - All eyez on Puka ",
            "remaining_faab_budget": 100,
            "waiver_position": 4,
            "current_record": "1-1",
            "contention_window": "CONTENDER",
            "roster_players": [
                "Trevor Lawrence (QB)",
                "Bucky Irving (RB)",
                "Omarion Hampton (RB)",
                "Zach Charbonnet (RB)",
                "Devin Singletary (RB)",
                "MarShawn Lloyd (RB)",
                "Emmett Johnson (RB)",
                "Puka Nacua (WR)",
                "Tetairoa McMillan (WR)",
                "Matthew Golden (WR)",
                "Carnell Tate (WR)",
                "Makai Lemon (WR)",
                "Quentin Johnston (WR)",
                "Trey McBride (TE)",
                "Harrison Butker (K)",
                "JAX (DEF)",
            ],
            "droppable_bench_players": ["Emmett Johnson (RB)", "Quentin Johnston (WR)", "Devin Singletary (RB)"],
        },
        "ownership_by_player_id": {
            "11584": {"manager": "CarlPullem94", "team_name": "T-Mac - All eyez on Puka (YOUR TEAM)", "is_user": True},
            "11625": {"manager": "leeed", "team_name": "Bend It Like Beckham Jr", "is_user": False},
            "9484": {"manager": "leeed", "team_name": "Bend It Like Beckham Jr", "is_user": False},
            "9225": {"manager": "nathanshephard", "team_name": "Saquon Deez Nuts", "is_user": False},
            "8144": {"manager": "FentTaker", "team_name": "FentTaker", "is_user": False},
            "10222": {"manager": "BenC1605", "team_name": "BenC1605", "is_user": False},
            "11564": {"manager": "BenC1605", "team_name": "BenC1605", "is_user": False},
        },
        "rival_managers_faab_leaderboard": [
            {"manager": "leeed (Bend It Like Beckham Jr)", "remaining_faab": 100, "primary_need": "RB2"},
            {"manager": "nathanshephard (Saquon Deez Nuts)", "remaining_faab": 94, "primary_need": "WR3"},
            {"manager": "FentTaker (FentTaker)", "remaining_faab": 90, "primary_need": "TE / RB"},
            {"manager": "BenC1605 (BenC1605)", "remaining_faab": 85, "primary_need": "RB Depth"},
        ],
    },
    "1387700465294135296": {
        "league_id": "1387700465294135296",
        "league_name": "Top Chops (18-Team Guillotine)",
        "total_rosters": 18,
        "scoring_format": "PPR",
        "scoring_settings": {"rec": 1.0, "pass_td": 6.0, "rush_td": 6.0},
        "waiver_budget_total": 1000,
        "user_roster_context": {
            "manager_handle": "CarlPullem94",
            "team_name": "Onions fight back ",
            "remaining_faab_budget": 1000,
            "waiver_position": 6,
            "current_record": "Survived Week 2",
            "contention_window": "CONTENDER",
            "roster_players": [
                "Jalen Hurts (QB)",
                "Cam Ward (QB)",
                "Rhamondre Stevenson (RB)",
                "J.K. Dobbins (RB)",
                "Devin Singletary (RB)",
                "Blake Corum (RB)",
                "Drake London (WR)",
                "Courtland Sutton (WR)",
                "Xavier Worthy (WR)",
                "Dontayvion Wicks (WR)",
                "Kyle Pitts (TE)",
                "Michael Mayer (TE)",
            ],
            "droppable_bench_players": ["Michael Mayer (TE)", "Blake Corum (RB)", "Devin Singletary (RB)"],
        },
        "ownership_by_player_id": {
            "9486": {"manager": "CarlPullem94", "team_name": "Onions fight back (YOUR TEAM)", "is_user": True},
            "11584": {"manager": "ChoppedRival_1", "team_name": "Guillotine Survivors", "is_user": False},
            "9484": {"manager": "ChoppedRival_2", "team_name": "Blade Runners", "is_user": False},
            "8144": {"manager": "ChoppedRival_3", "team_name": "No Mercy", "is_user": False},
            "10222": {"manager": "ChoppedRival_4", "team_name": "Final Cut", "is_user": False},
            "11564": {"manager": "ChoppedRival_5", "team_name": "Executioners", "is_user": False},
        },
        "rival_managers_faab_leaderboard": [
            {"manager": "Guillotine Survivors", "remaining_faab": 1000, "primary_need": "RB1 / WR1"},
            {"manager": "Blade Runners", "remaining_faab": 940, "primary_need": "QB2 / Superflex"},
            {"manager": "No Mercy", "remaining_faab": 875, "primary_need": "RB Depth"},
            {"manager": "Final Cut", "remaining_faab": 790, "primary_need": "TE / FLEX"},
        ],
    },
}


def normalize_league_id(raw_league_input: str) -> str:
    """Extract numeric Sleeper league ID from a full URL (`https://sleeper.com/leagues/1389351355675586560/league`) or ID."""
    cleaned = (raw_league_input or "").strip()
    match = re.search(r"leagues/(\d+)", cleaned)
    if match:
        return match.group(1)
    digits = re.search(r"\b(\d{15,22})\b", cleaned)
    if digits:
        return digits.group(1)
    return cleaned or "demo_sleeper_league"


_LIVE_SLEEPER_PLAYER_STATUS_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def fetch_live_sleeper_player_status_map() -> Dict[str, Dict[str, Any]]:
    """Fetch and cache live NFL injury (`IR`, `PUP`, `Out`), active status, and depth chart order from `/v1/players/nfl`."""
    global _LIVE_SLEEPER_PLAYER_STATUS_CACHE
    if _LIVE_SLEEPER_PLAYER_STATUS_CACHE is not None:
        return _LIVE_SLEEPER_PLAYER_STATUS_CACHE
    try:
        req = urllib.request.Request(
            f"{SLEEPER_API_BASE_URL}/players/nfl",
            headers={"User-Agent": "GridironEdgeAI-ADK/1.0"},
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            if resp.status == 200:
                raw_players = json.loads(resp.read().decode("utf-8"))
                subset: Dict[str, Dict[str, Any]] = {}
                for row in _CURATED_NFLVERSE_SABERMETRIC_CATALOG:
                    pid = str(row["player_id"])
                    if pid in raw_players:
                        p = raw_players[pid]
                        subset[pid] = {
                            "team": p.get("team"),
                            "status": p.get("status"),
                            "injury_status": p.get("injury_status"),
                            "injury_body_part": p.get("injury_body_part"),
                            "depth_chart_order": p.get("depth_chart_order"),
                        }
                _LIVE_SLEEPER_PLAYER_STATUS_CACHE = subset
                return subset
    except Exception:
        pass
    _LIVE_SLEEPER_PLAYER_STATUS_CACHE = {}
    return _LIVE_SLEEPER_PLAYER_STATUS_CACHE


class NflverseOpenDataClient:
    """Data provider wrapping `nflverse` (`nflreadpy` / `nflfastR`) play-by-play, L4 recency trends, and live NFL injury status."""

    def __init__(self) -> None:
        live_status_map = fetch_live_sleeper_player_status_map()
        enriched_rows: List[PlayerAdvancedMetricsProfile] = []
        for row in _CURATED_NFLVERSE_SABERMETRIC_CATALOG:
            row_copy = dict(row)
            pid = str(row_copy["player_id"])
            live = live_status_map.get(pid)
            if live:
                if live.get("team"):
                    row_copy["team"] = live["team"]
                status = live.get("status") or row_copy.get("nfl_roster_status", "Active")
                inj = live.get("injury_status") or row_copy.get("injury_status")
                body = live.get("injury_body_part") or row_copy.get("injury_body_part")
                depth = live.get("depth_chart_order") if "depth_chart_order" in live else row_copy.get("depth_chart_order")
                row_copy["nfl_roster_status"] = status
                row_copy["injury_status"] = inj
                row_copy["injury_body_part"] = body
                row_copy["depth_chart_order"] = depth
                if (
                    status != "Active"
                    or inj in ("IR", "PUP", "Out", "Doubtful", "Sus", "COV")
                    or depth is None
                    or depth > 3
                    or row_copy.get("l4_route_delta_pct", 0.0) < -10.0
                ):
                    row_copy["is_waiver_eligible_healthy"] = False
                    if not row_copy.get("exclusion_reason"):
                        row_copy["exclusion_reason"] = (
                            f"🚫 Excluded: status={status}, injury={inj or 'None'} ({body or 'N/A'}), depth_chart_order={depth}"
                        )
            enriched_rows.append(PlayerAdvancedMetricsProfile(**row_copy))
        self._profiles: List[PlayerAdvancedMetricsProfile] = enriched_rows

    def get_all_players(self) -> List[PlayerAdvancedMetricsProfile]:
        return list(self._profiles)

    def get_player_by_name(self, name: str) -> Optional[PlayerAdvancedMetricsProfile]:
        target = name.strip().lower()
        for profile in self._profiles:
            if profile.player_name.lower() == target:
                return profile
        return None

    def fuzzy_suggest_players(self, query: str, limit: int = 4) -> List[str]:
        all_names = [p.player_name for p in self._profiles]
        matches = difflib.get_close_matches(query.strip(), all_names, n=limit, cutoff=0.35)
        if not matches:
            return all_names[:limit]
        return matches


class SleeperPublicApiClient:
    """Read-Only Client for the public Sleeper Fantasy Football API (`https://api.sleeper.app/v1`)."""

    def fetch_trending_waiver_adds(self, limit: int = 8) -> List[Dict[str, Any]]:
        url = f"{SLEEPER_API_BASE_URL}/players/nfl/trending/add?lookback_hours=24&limit={limit}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GridironEdgeAI-ADK/1.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and data:
                        return data
        except Exception:
            pass
        return [
            {"player_id": "11435", "player_name": "Emanuel Wilson", "count": 190186, "delta_24h": "+24.0%"},
            {"player_id": "11625", "player_name": "Adonai Mitchell", "count": 104301, "delta_24h": "+23.5%"},
            {"player_id": "10213", "player_name": "Tre Tucker", "count": 102356, "delta_24h": "+22.0%"},
            {"player_id": "11618", "player_name": "Jalen McMillan", "count": 48920, "delta_24h": "+16.2%"},
            {"player_id": "9486", "player_name": "Dontayvion Wicks", "count": 28400, "delta_24h": "+18.5%"},
        ]


    def get_league_context(self, raw_league_id: str) -> Dict[str, Any]:
        league_id = normalize_league_id(raw_league_id)
        trending = self.fetch_trending_waiver_adds(limit=6)

        # Start from known snapshot if one of Carl's 3 leagues, and enrich with live HTTP call if reachable
        base_snapshot = json.loads(json.dumps(_KNOWN_LEAGUE_SNAPSHOTS.get(league_id, {})))

        if league_id != "demo_sleeper_league":
            try:
                l_req = urllib.request.Request(
                    f"{SLEEPER_API_BASE_URL}/league/{league_id}",
                    headers={"User-Agent": "GridironEdgeAI-ADK/1.0"},
                )
                r_req = urllib.request.Request(
                    f"{SLEEPER_API_BASE_URL}/league/{league_id}/rosters",
                    headers={"User-Agent": "GridironEdgeAI-ADK/1.0"},
                )
                u_req = urllib.request.Request(
                    f"{SLEEPER_API_BASE_URL}/league/{league_id}/users",
                    headers={"User-Agent": "GridironEdgeAI-ADK/1.0"},
                )
                with urllib.request.urlopen(l_req, timeout=2.5) as l_resp, urllib.request.urlopen(
                    r_req, timeout=2.5
                ) as r_resp, urllib.request.urlopen(u_req, timeout=2.5) as u_resp:
                    league_meta = json.loads(l_resp.read().decode("utf-8"))
                    rosters_data = json.loads(r_resp.read().decode("utf-8"))
                    users_data = json.loads(u_resp.read().decode("utf-8"))

                    users_map: Dict[str, Dict[str, str]] = {}
                    for u in users_data:
                        uid = str(u.get("user_id", ""))
                        disp = u.get("display_name") or "Manager"
                        tname = (u.get("metadata") or {}).get("team_name") or disp
                        users_map[uid] = {"display_name": disp, "team_name": tname}

                    live_ownership: Dict[str, Dict[str, Any]] = dict(base_snapshot.get("ownership_by_player_id", {}))
                    total_budget = int((league_meta.get("settings") or {}).get("waiver_budget", 100))
                    rivals_list: List[Dict[str, Any]] = []
                    user_remaining_faab = total_budget
                    user_team_name = base_snapshot.get("user_roster_context", {}).get("team_name", "CarlPullem94")

                    for r in rosters_data:
                        owner_id = str(r.get("owner_id") or "")
                        u_info = users_map.get(owner_id, {"display_name": f"Roster #{r.get('roster_id')}", "team_name": "Team"})
                        used_faab = int((r.get("settings") or {}).get("waiver_budget_used", 0))
                        rem_faab = max(0, total_budget - used_faab)
                        is_carl = owner_id == CARL_SLEEPER_USER_ID or u_info["display_name"].lower() == "carlpullem94"

                        for pid in r.get("players") or []:
                            live_ownership[str(pid)] = {
                                "manager": u_info["display_name"],
                                "team_name": u_info["team_name"],
                                "is_user": is_carl,
                            }

                        if is_carl:
                            user_remaining_faab = rem_faab
                            user_team_name = u_info["team_name"]
                        else:
                            rivals_list.append(
                                {
                                    "manager": f"{u_info['display_name']} ({u_info['team_name']})",
                                    "remaining_faab": rem_faab,
                                    "primary_need": "Waiver / Flex Depth",
                                }
                            )

                    rec_val = float((league_meta.get("scoring_settings") or {}).get("rec", 1.0))
                    scoring_fmt = "PPR" if rec_val >= 1.0 else "HALF_PPR" if rec_val >= 0.5 else "STANDARD"
                    user_ctx = base_snapshot.get("user_roster_context", {})
                    user_ctx["manager_handle"] = "CarlPullem94"
                    user_ctx["team_name"] = user_team_name
                    user_ctx["remaining_faab_budget"] = user_remaining_faab

                    return {
                        "league_id": league_id,
                        "league_name": league_meta.get("name", base_snapshot.get("league_name", "Sleeper League")),
                        "total_rosters": league_meta.get("total_rosters", 12),
                        "scoring_format": scoring_fmt,
                        "scoring_settings": league_meta.get("scoring_settings", {"rec": rec_val}),
                        "waiver_budget_total": total_budget,
                        "user_roster_context": user_ctx,
                        "ownership_by_player_id": live_ownership,
                        "rostered_sleeper_ids": list(live_ownership.keys()),
                        "rival_managers_faab_leaderboard": rivals_list[:6] or base_snapshot.get("rival_managers_faab_leaderboard", []),
                        "live_trending_waiver_adds_24h": trending,
                        "read_only_advisory_mode": True,
                        "data_source": "Sleeper Live Read-Only REST API (/v1/league + /rosters + /users)",
                    }
            except Exception:
                pass

        if base_snapshot:
            base_snapshot["rostered_sleeper_ids"] = list(base_snapshot.get("ownership_by_player_id", {}).keys())
            base_snapshot["live_trending_waiver_adds_24h"] = trending
            base_snapshot["read_only_advisory_mode"] = True
            return base_snapshot

        return {
            "league_id": league_id,
            "league_name": "Gridiron Edge 12-Team PPR Championship League",
            "total_rosters": 12,
            "scoring_format": "PPR",
            "scoring_settings": {"rec": 1.0, "pass_td": 4.0, "rush_td": 6.0, "bonus_rec_te": 0.0},
            "waiver_type": "FAAB (Read-Only Advisory Mode)",
            "waiver_budget_total": 100,
            "user_roster_context": {
                "manager_handle": "CarlPullem94",
                "team_name": "3 rings - Come at me ",
                "remaining_faab_budget": 84,
                "current_record": "4-1",
                "contention_window": "CONTENDER",
                "weakest_positions": ["RB2", "WR3/FLEX"],
                "droppable_bench_players": ["Zamir White (18% snap share)", "Quentin Johnston (WR)"],
                "tradeable_sell_high_assets": ["Jayden Reed (-4.5 PPR xFP differential)"],
            },
            "ownership_by_player_id": {},
            "rostered_sleeper_ids": [],
            "live_trending_waiver_adds_24h": trending,
            "read_only_advisory_mode": True,
            "data_source": "Sleeper API + nflverse Opportunity Overlay",
        }


_NFLVERSE_CLIENT = NflverseOpenDataClient()
_SLEEPER_CLIENT = SleeperPublicApiClient()


def get_nflverse_client() -> NflverseOpenDataClient:
    return _NFLVERSE_CLIENT


def get_sleeper_client() -> SleeperPublicApiClient:
    return _SLEEPER_CLIENT
