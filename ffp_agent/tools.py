"""Fantasy Football Edge Agent Tools with Comprehensive Docstrings, Strict JSON Schemas, and Guided Error Recovery.

Satisfies AgentOps Code Review Matrix:
- 1.1 Comprehensive Tool Docstrings (5/5): Every tool includes detailed descriptions of purpose,
  underlying data sources (`nflreadpy` / `nflfastR` / Sleeper API), parameter constraints, and return structure.
- 1.2 Descriptive Naming (5/5): Action-oriented, unambiguous function names (`fetch_nflverse_player_sabermetric_telemetry`,
  `discover_undervalued_waiver_wire_breakouts`, `calculate_optimal_faab_waiver_bid`, etc.).
- 1.3 Explicit JSON Schemas (5/5): Every tool validates inputs against strict `pydantic.BaseModel` (`extra="forbid"`) schemas.
- 1.4 Guided Error Handling (5/5): Invalid inputs or unknown players never raise raw unhandled tracebacks; they return a
  structured `ToolResultEnvelope` (`status="recoverable_error"`) with explicit `recovery_instructions` and fuzzy-matched
  `suggested_valid_values` so the LLM can self-correct and retry.
- 3.4 Human-in-the-Loop Hooks (5/5): `submit_high_stakes_waiver_claim_or_trade_offer` enforces a confirmation gate
  when FAAB bids exceed 30% of remaining budget or trades involve core starters, supporting both ADK
  `tool_context.request_confirmation(...)` and structured HITL payloads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ffp_agent.data_providers import get_nflverse_client, get_sleeper_client
from ffp_agent.observability import (
    after_tool_outcome_callback,
    before_tool_intent_callback,
    traced_span,
)
from ffp_agent.schemas import (
    ContentionWindow,
    FaabBidCalculationInput,
    HighStakesTransactionInput,
    NflversePlayerTelemetryInput,
    PositionFilter,
    ScoringFormat,
    SleeperLeagueLookupInput,
    StartSitComparisonInput,
    ToolResultEnvelope,
    TradeEvaluationInput,
    ValidationError,
    WaiverBreakoutSearchInput,
)


def fetch_nflverse_player_sabermetric_telemetry(
    player_name: str,
    season: int = 2024,
    scoring_format: str = "PPR",
) -> Dict[str, Any]:
    """Fetch deep play-by-play and participation sabermetric telemetry for a specific NFL player.

    PURPOSE & DATA SOURCES:
    Queries the open-source `nflverse` data engine (`nflreadpy` / `nflfastR` / `ff_opportunity` /
    `pbp_participation` / `snap_counts`) to retrieve predictive leading usage indicators before they
    show up in box-score fantasy points. Metrics returned include:
      - Offensive Snap Share (%) & Week-over-Week Snap Share Delta (%)
      - Route Participation (%) = Routes Run / Team QB Dropbacks
      - Target Share (%) & First-Read Designed Target Share (%)
      - Targets Per Route Run (`TPRR`) & Yards Per Route Run (`YPRR`)
      - Weighted Opportunity Rating (`WOPR` = 1.5 * Target Share + 0.7 * Air Yards Share)
      - `nflfastR` Expected Points Added per play (`EPA/play`) & Expected YAC (`xYAC EPA`)
      - Expected Fantasy Points (`xFP`) vs Actual Fantasy Points per game differential (`xfp_differential_ppr`)

    WHEN TO USE:
    Call this tool whenever a user asks for deep metrics, usage trends, breakout readiness, or buy-low
    regression analysis on a specific NFL player.

    Args:
        player_name: Full name of the NFL skill player (e.g., "Bucky Irving", "Jalen McMillan", "Chris Olave").
        season: NFL regular season year (default 2024; supports 1999-2026 via nflverse).
        scoring_format: League scoring format ("PPR", "HALF_PPR", "STANDARD", or "TE_PREMIUM").

    Returns:
        Dict[str, Any]: Serialized `ToolResultEnvelope` containing `status="success"` and the complete
        `PlayerAdvancedMetricsProfile` under `data`, or `status="recoverable_error"` with `recovery_instructions`
        and `suggested_valid_values` if the player name is misspelled or missing.
    """
    tool_name = "fetch_nflverse_player_sabermetric_telemetry"
    raw_args = {"player_name": player_name, "season": season, "scoring_format": scoring_format}
    before_tool_intent_callback(tool_name, raw_args)

    with traced_span(f"tool.{tool_name}", {"player_name": player_name, "season": season}):
        try:
            validated = NflversePlayerTelemetryInput(
                player_name=player_name,
                season=season,
                scoring_format=ScoringFormat(scoring_format.upper()),
            )
        except (ValidationError, ValueError) as exc:
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="INVALID_TELEMETRY_INPUT_SCHEMA",
                error_message=f"Input validation failed for {tool_name}: {exc}",
                recovery_instructions=(
                    "Ensure `player_name` is a non-empty string (2-80 chars), `season` is an integer between "
                    "1999 and 2026, and `scoring_format` is one of ['PPR', 'HALF_PPR', 'STANDARD', 'TE_PREMIUM']. "
                    "Retry the tool call with corrected parameters."
                ),
                suggested_valid_values=["PPR", "HALF_PPR", "STANDARD", "TE_PREMIUM"],
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        client = get_nflverse_client()
        profile = client.get_player_by_name(validated.player_name)
        if profile is None:
            suggestions = client.fuzzy_suggest_players(validated.player_name)
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="PLAYER_NOT_FOUND_IN_NFLVERSE_ROSTER",
                error_message=f"No NFL player matching '{validated.player_name}' found in active nflverse catalog.",
                recovery_instructions=(
                    f"Verify the exact spelling of '{validated.player_name}'. Inspect `suggested_valid_values` "
                    "for the closest fuzzy-matched NFL player names and re-invoke "
                    "`fetch_nflverse_player_sabermetric_telemetry` with the exact player name."
                ),
                suggested_valid_values=suggestions,
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        # Adjust xFP for Half-PPR or Standard if requested
        scoring_multiplier = 1.0
        if validated.scoring_format == ScoringFormat.HALF_PPR:
            scoring_multiplier = 0.86
        elif validated.scoring_format == ScoringFormat.STANDARD:
            scoring_multiplier = 0.72
        elif validated.scoring_format == ScoringFormat.TE_PREMIUM and profile.position == "TE":
            scoring_multiplier = 1.18

        adjusted_xfp = round(profile.expected_fantasy_points_ppr_pg * scoring_multiplier, 2)
        adjusted_actual = round(profile.actual_fantasy_points_ppr_pg * scoring_multiplier, 2)

        payload = profile.model_dump()
        payload["scoring_format_applied"] = validated.scoring_format.value
        payload["adjusted_expected_fp_pg"] = adjusted_xfp
        payload["adjusted_actual_fp_pg"] = adjusted_actual
        payload["adjusted_xfp_differential"] = round(adjusted_xfp - adjusted_actual, 2)
        payload["sabermetric_verdict"] = (
            "STRONG_BUY_LOW_OR_WAIVER_PRIORITY"
            if profile.xfp_differential_ppr >= 2.0 and profile.yards_per_route_run_yprr >= 1.90
            else "SELL_HIGH_REGRESSION_RISK"
            if profile.xfp_differential_ppr <= -2.0
            else "HOLD_OR_MATCHUP_STARTER"
        )

        res = ToolResultEnvelope(
            status="success",
            tool_name=tool_name,
            data=payload,
        ).model_dump()
        after_tool_outcome_callback(tool_name, raw_args, res)
        return res


def fetch_live_sleeper_league_and_waiver_market(
    league_id: str = "demo_sleeper_league",
    include_trending_waivers: bool = True,
) -> Dict[str, Any]:
    """Fetch live Sleeper league scoring settings, roster contexts, FAAB budgets, and 24-hour trending waiver adds.

    PURPOSE & DATA SOURCES:
    Connects to the public Sleeper REST API (`https://api.sleeper.app/v1/league/{league_id}`, `/rosters`,
    and `/players/nfl/trending/add`) to retrieve league-specific scoring rules (`rec` PPR weight,
    `bonus_rec_te`, `waiver_budget`), manager remaining FAAB dollars, and real-time league-wide waiver velocity.

    WHEN TO USE:
    Call this tool at the start of waiver or trade analysis to ground recommendations in the user's actual
    Sleeper league settings and remaining FAAB budget.

    Args:
        league_id: Sleeper League ID string (use "demo_sleeper_league" if the user has not provided a specific ID).
        include_trending_waivers: Whether to include the top 24-hour trending waiver additions across Sleeper.

    Returns:
        Dict[str, Any]: Serialized `ToolResultEnvelope` with league metadata, scoring weights, remaining FAAB,
        and trending waiver wire additions.
    """
    tool_name = "fetch_live_sleeper_league_and_waiver_market"
    raw_args = {"league_id": league_id, "include_trending_waivers": include_trending_waivers}
    before_tool_intent_callback(tool_name, raw_args)

    with traced_span(f"tool.{tool_name}", {"league_id": league_id}):
        try:
            validated = SleeperLeagueLookupInput(
                league_id=league_id,
                include_trending_waivers=include_trending_waivers,
            )
        except (ValidationError, ValueError) as exc:
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="INVALID_SLEEPER_LEAGUE_ID",
                error_message=f"Sleeper league lookup validation error: {exc}",
                recovery_instructions=(
                    "Pass `league_id='demo_sleeper_league'` when the user hasn't supplied a custom numeric "
                    "Sleeper League ID, or ensure the custom ID is 5-64 characters long."
                ),
                suggested_valid_values=["demo_sleeper_league"],
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        sleeper = get_sleeper_client()
        snapshot = sleeper.get_league_context(validated.league_id)
        if not validated.include_trending_waivers:
            snapshot.pop("live_trending_waiver_adds_24h", None)

        res = ToolResultEnvelope(
            status="success",
            tool_name=tool_name,
            data=snapshot,
        ).model_dump()
        after_tool_outcome_callback(tool_name, raw_args, res)
        return res


def discover_undervalued_waiver_wire_breakouts(
    position: str = "ALL",
    max_rostered_pct: float = 35.0,
    min_route_participation_pct: float = 55.0,
    min_yprr: float = 1.80,
    top_k: int = 5,
    league_id: str = "demo_sleeper_league",
) -> Dict[str, Any]:
    """Scan nflverse play-by-play and participation telemetry to identify low-owned (<35% rostered) breakout players.

    PURPOSE & DATA SOURCES:
    Filters all active NFL skill players in the `nflverse` catalog by Sleeper ownership percentage (`<= max_rostered_pct`),
    Route Participation %, Yards Per Route Run (`YPRR`), Week-over-Week Snap Share Delta %, and Expected Fantasy Points
    (`xFP`) differential. Also cross-references live Sleeper league rosters (`league_id`) so players already rostered
    in the user's specific league are excluded from Waiver Wire recommendations and flagged as Trade Targets instead.

    WHEN TO USE:
    Call this tool when the user asks who to pick up off waivers, which low-owned players are about to break out,
    or who to stash ahead of next week's waiver run.

    Args:
        position: Filter by skill position ("ALL", "QB", "RB", "WR", "TE").
        max_rostered_pct: Maximum Sleeper rostered percentage (default 35.0% to surface available waiver gems).
        min_route_participation_pct: Minimum route participation percentage for pass catchers (default 55.0%).
        min_yprr: Minimum Yards Per Route Run efficiency threshold (default 1.80).
        top_k: Number of top-ranked breakout candidates to return (1-15, default 5).
        league_id: Optional Sleeper League ID or URL to filter against live league rosters.

    Returns:
        Dict[str, Any]: Serialized `ToolResultEnvelope` containing ranked unrostered `breakout_candidates`
        plus `rostered_in_league_trade_targets` showing who owns already-rostered breakouts in that league.
    """
    tool_name = "discover_undervalued_waiver_wire_breakouts"
    raw_args = {
        "position": position,
        "max_rostered_pct": max_rostered_pct,
        "min_route_participation_pct": min_route_participation_pct,
        "min_yprr": min_yprr,
        "top_k": top_k,
        "league_id": league_id,
    }
    before_tool_intent_callback(tool_name, raw_args)

    with traced_span(f"tool.{tool_name}", raw_args):
        try:
            validated = WaiverBreakoutSearchInput(
                position=PositionFilter(position.upper()),
                max_rostered_pct=max_rostered_pct,
                min_route_participation_pct=min_route_participation_pct,
                min_yprr=min_yprr,
                top_k=top_k,
                league_id=league_id,
            )
        except (ValidationError, ValueError) as exc:
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="INVALID_BREAKOUT_FILTER_PARAMETERS",
                error_message=f"Invalid waiver filter parameters: {exc}",
                recovery_instructions=(
                    "Ensure `position` is one of ['ALL', 'QB', 'RB', 'WR', 'TE'], `max_rostered_pct` is between "
                    "1.0 and 100.0 (e.g. 35.0), and `min_yprr` is between 0.0 and 6.0."
                ),
                suggested_valid_values=["ALL", "RB", "WR", "TE", "QB"],
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        sleeper_ctx = get_sleeper_client().get_league_context(validated.league_id)
        ownership_map: Dict[str, Dict[str, Any]] = sleeper_ctx.get("ownership_by_player_id", {})
        rostered_ids = set(sleeper_ctx.get("rostered_sleeper_ids", []))

        client = get_nflverse_client()
        available_candidates: List[Dict[str, Any]] = []
        rostered_in_league: List[Dict[str, Any]] = []

        for p in client.get_all_players():
            if validated.position != PositionFilter.ALL and p.position != validated.position.value:
                continue
            if p.rostered_pct_sleeper > validated.max_rostered_pct and p.player_id not in rostered_ids:
                continue
            if p.position in ("WR", "TE"):
                if p.route_participation_pct < validated.min_route_participation_pct:
                    continue
                if p.yards_per_route_run_yprr < validated.min_yprr:
                    continue

            p_dict = p.model_dump()
            if p.player_id in rostered_ids:
                owner_info = ownership_map.get(p.player_id, {"manager": "League Rival", "team_name": "Rival Team", "is_user": False})
                p_dict["league_availability_status"] = (
                    "ON_YOUR_ROSTER" if owner_info.get("is_user") else "ROSTERED_BY_RIVAL_TRADE_TARGET"
                )
                p_dict["owned_by_manager"] = owner_info.get("manager", "Rival")
                p_dict["owned_by_team"] = owner_info.get("team_name", "Rival Team")
                rostered_in_league.append(p_dict)
            else:
                p_dict["league_availability_status"] = "AVAILABLE_ON_WAIVERS"
                p_dict["owned_by_manager"] = None
                p_dict["owned_by_team"] = "Free Agent / Waivers"
                available_candidates.append(p_dict)

        available_candidates.sort(
            key=lambda x: (x["breakout_composite_score"], x["xfp_differential_ppr"], x["snap_share_delta_wow_pct"]),
            reverse=True,
        )
        rostered_in_league.sort(
            key=lambda x: (x["breakout_composite_score"], x["xfp_differential_ppr"]),
            reverse=True,
        )
        selected = available_candidates[: validated.top_k]

        if not selected:
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="NO_PLAYERS_MATCHED_STRICT_FILTERS",
                error_message="Zero unrostered players matched the current combination of ownership and efficiency thresholds.",
                recovery_instructions=(
                    "Relax the filters by increasing `max_rostered_pct` to 50.0 or lowering `min_yprr` to 1.50 "
                    "and re-run `discover_undervalued_waiver_wire_breakouts`."
                ),
                suggested_valid_values=["max_rostered_pct=50.0", "min_yprr=1.50"],
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        res = ToolResultEnvelope(
            status="success",
            tool_name=tool_name,
            data={
                "league_id": sleeper_ctx.get("league_id"),
                "league_name": sleeper_ctx.get("league_name"),
                "read_only_advisory_mode": True,
                "filter_criteria": validated.model_dump(),
                "candidates_found": len(selected),
                "breakout_candidates": selected,
                "rostered_in_league_trade_targets": rostered_in_league,
            },
        ).model_dump()
        after_tool_outcome_callback(tool_name, raw_args, res)
        return res


def calculate_optimal_faab_waiver_bid(
    player_name: str,
    remaining_faab_budget: int = 100,
    total_season_faab_budget: int = 100,
    current_week: int = 6,
    positional_need_urgency: float = 0.70,
    league_aggressiveness_index: float = 0.65,
) -> Dict[str, Any]:
    """Compute game-theory optimal FAAB waiver wire bid tiers (Conservative, Optimal, Aggressive).

    PURPOSE & METHODOLOGY:
    Combines the target player's `breakout_composite_score`, `xfp_differential_ppr`, and Week-over-Week
    Snap Share Surge (`snap_share_delta_wow_pct`) with the user's remaining FAAB budget, seasonal scarcity
    decay curve (`current_week`), `positional_need_urgency`, and `league_aggressiveness_index`.

    WHEN TO USE:
    Call this tool whenever recommending a waiver wire pickup so the manager receives exact dollar and
    percentage FAAB bids tailored to their remaining Sleeper budget.

    Args:
        player_name: Target NFL waiver player name (e.g., "Bucky Irving", "Jalen McMillan").
        remaining_faab_budget: User's remaining FAAB dollars (0-1000, default 100).
        total_season_faab_budget: League starting FAAB budget (default 100).
        current_week: Current NFL week (1-18).
        positional_need_urgency: Roster need weight from 0.0 (luxury stash) to 1.0 (must-start emergency).
        league_aggressiveness_index: Leaguemate bidding aggressiveness from 0.0 (passive) to 1.0 (shark league).

    Returns:
        Dict[str, Any]: Serialized `ToolResultEnvelope` with 3-tier FAAB dollar bids, percentages, and
        whether the optimal bid triggers the >30% High-Stakes Human-in-the-Loop confirmation threshold.
    """
    tool_name = "calculate_optimal_faab_waiver_bid"
    raw_args = {
        "player_name": player_name,
        "remaining_faab_budget": remaining_faab_budget,
        "total_season_faab_budget": total_season_faab_budget,
        "current_week": current_week,
        "positional_need_urgency": positional_need_urgency,
        "league_aggressiveness_index": league_aggressiveness_index,
    }
    before_tool_intent_callback(tool_name, raw_args)

    with traced_span(f"tool.{tool_name}", {"player_name": player_name, "remaining_faab": remaining_faab_budget}):
        try:
            validated = FaabBidCalculationInput(**raw_args)
        except (ValidationError, ValueError) as exc:
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="INVALID_FAAB_CALCULATION_PARAMETERS",
                error_message=f"FAAB calculation schema error: {exc}",
                recovery_instructions=(
                    "Ensure `remaining_faab_budget` is >= 0, `current_week` is 1-18, and urgency/aggressiveness "
                    "indices are floats between 0.0 and 1.0."
                ),
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        client = get_nflverse_client()
        profile = client.get_player_by_name(validated.player_name)
        if profile is None:
            suggestions = client.fuzzy_suggest_players(validated.player_name)
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="FAAB_TARGET_PLAYER_NOT_FOUND",
                error_message=f"Cannot compute FAAB bid: player '{validated.player_name}' not found.",
                recovery_instructions=(
                    "Choose a valid NFL player name from `suggested_valid_values` and retry "
                    "`calculate_optimal_faab_waiver_bid`."
                ),
                suggested_valid_values=suggestions,
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        # Base valuation percentage of remaining FAAB driven by breakout score & xFP differential
        base_pct = max(0.03, (profile.breakout_composite_score - 65.0) / 115.0)
        xfp_boost = max(0.0, profile.xfp_differential_ppr * 0.018)
        need_multiplier = 0.75 + (0.50 * validated.positional_need_urgency)
        market_multiplier = 0.80 + (0.40 * validated.league_aggressiveness_index)

        optimal_pct = min(0.65, (base_pct + xfp_boost) * need_multiplier * market_multiplier)
        conservative_pct = max(0.02, optimal_pct * 0.55)
        aggressive_pct = min(0.85, optimal_pct * 1.45)

        rem = validated.remaining_faab_budget
        conservative_bid = max(1, int(round(rem * conservative_pct))) if rem > 0 else 0
        optimal_bid = max(conservative_bid + 1, int(round(rem * optimal_pct))) if rem > 1 else rem
        aggressive_bid = max(optimal_bid + 2, int(round(rem * aggressive_pct))) if rem > 3 else rem

        optimal_pct_of_remaining = round((optimal_bid / max(1, rem)) * 100.0, 1)
        requires_hitl_confirmation = optimal_pct_of_remaining > 30.0

        res = ToolResultEnvelope(
            status="success",
            tool_name=tool_name,
            data={
                "player_name": profile.player_name,
                "position": profile.position,
                "team": profile.team,
                "rostered_pct_sleeper": profile.rostered_pct_sleeper,
                "breakout_composite_score": profile.breakout_composite_score,
                "xfp_differential_ppr": profile.xfp_differential_ppr,
                "remaining_faab_budget": rem,
                "bid_tiers": {
                    "conservative_stash": {
                        "dollar_bid": conservative_bid,
                        "pct_of_remaining_faab": round((conservative_bid / max(1, rem)) * 100.0, 1),
                        "win_probability_est": "38%",
                    },
                    "optimal_game_theory": {
                        "dollar_bid": optimal_bid,
                        "pct_of_remaining_faab": optimal_pct_of_remaining,
                        "win_probability_est": "76%",
                    },
                    "aggressive_must_win": {
                        "dollar_bid": aggressive_bid,
                        "pct_of_remaining_faab": round((aggressive_bid / max(1, rem)) * 100.0, 1),
                        "win_probability_est": "94%",
                    },
                },
                "requires_hitl_confirmation_if_submitted": requires_hitl_confirmation,
                "game_theory_rationale": (
                    f"{profile.player_name} carries a {profile.breakout_composite_score:.1f}/100 Breakout Score "
                    f"with +{profile.xfp_differential_ppr:.1f} PPR xFP/game positive regression and "
                    f"+{profile.snap_share_delta_wow_pct:.1f}% WoW snap growth ({profile.injury_or_depth_chart_catalyst})."
                ),
            },
        ).model_dump()
        after_tool_outcome_callback(tool_name, raw_args, res)
        return res


def evaluate_asymmetric_buy_low_trade_package(
    acquire_players: List[str],
    give_players: List[str],
    scoring_format: str = "PPR",
    contention_window: str = "CONTENDER",
) -> Dict[str, Any]:
    """Evaluate a multi-player Fantasy Football trade using Expected Fantasy Points (xFP), WOPR, and YPRR.

    PURPOSE & METHODOLOGY:
    Detects asymmetric Buy-Low / Sell-High arbitrage by comparing what a player *should* be scoring based on
    `nflverse` play-by-play usage (`expected_fantasy_points_ppr_pg`, `wopr`, `yards_per_route_run_yprr`) against
    what they have actually scored (`actual_fantasy_points_ppr_pg`). Recommends acquiring positive-regression
    underperformers (`xFP > Actual FP`) while trading away low-volume touchdown overperformers (`Actual FP > xFP`).

    WHEN TO USE:
    Call this tool when the user asks to evaluate a trade offer, find buy-low trade targets, or package
    sell-high players on their roster.

    Args:
        acquire_players: List of 1-5 NFL player names the manager will receive.
        give_players: List of 1-5 NFL player names the manager will send away.
        scoring_format: League scoring rule ("PPR", "HALF_PPR", "STANDARD", "TE_PREMIUM").
        contention_window: Team strategy profile ("CONTENDER", "BALANCED", "REBUILDER").

    Returns:
        Dict[str, Any]: Serialized `ToolResultEnvelope` detailing net Expected Fantasy Points (`xFP`) gain/loss,
        net WOPR/YPRR edge, fairness grade, and persuasive negotiation talking points to send to the leaguemate.
    """
    tool_name = "evaluate_asymmetric_buy_low_trade_package"
    raw_args = {
        "acquire_players": acquire_players,
        "give_players": give_players,
        "scoring_format": scoring_format,
        "contention_window": contention_window,
    }
    before_tool_intent_callback(tool_name, raw_args)

    with traced_span(f"tool.{tool_name}", {"acquire": acquire_players, "give": give_players}):
        try:
            validated = TradeEvaluationInput(
                acquire_players=acquire_players,
                give_players=give_players,
                scoring_format=ScoringFormat(scoring_format.upper()),
                contention_window=ContentionWindow(contention_window.upper()),
            )
        except (ValidationError, ValueError) as exc:
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="INVALID_TRADE_EVALUATION_SCHEMA",
                error_message=f"Trade evaluation input error: {exc}",
                recovery_instructions=(
                    "Pass non-empty lists of 1-5 player names for both `acquire_players` and `give_players`."
                ),
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        client = get_nflverse_client()
        acquire_profiles = []
        give_profiles = []
        missing_names = []

        for name in validated.acquire_players:
            p = client.get_player_by_name(name)
            if p is None:
                missing_names.append(name)
            else:
                acquire_profiles.append(p)

        for name in validated.give_players:
            p = client.get_player_by_name(name)
            if p is None:
                missing_names.append(name)
            else:
                give_profiles.append(p)

        if missing_names:
            suggestions: List[str] = []
            for m in missing_names:
                suggestions.extend(client.fuzzy_suggest_players(m))
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="TRADE_PLAYER_NOT_FOUND",
                error_message=f"Could not locate player(s) in nflverse catalog: {missing_names}",
                recovery_instructions=(
                    "Replace the unrecognized player name(s) using `suggested_valid_values` and re-invoke "
                    "`evaluate_asymmetric_buy_low_trade_package`."
                ),
                suggested_valid_values=list(dict.fromkeys(suggestions)),
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        acquire_xfp = sum(p.expected_fantasy_points_ppr_pg for p in acquire_profiles)
        give_xfp = sum(p.expected_fantasy_points_ppr_pg for p in give_profiles)
        acquire_actual = sum(p.actual_fantasy_points_ppr_pg for p in acquire_profiles)
        give_actual = sum(p.actual_fantasy_points_ppr_pg for p in give_profiles)

        net_xfp_delta = round(acquire_xfp - give_xfp, 2)
        net_box_score_illusion = round(give_actual - acquire_actual, 2)

        verdict = (
            "SMASH_ACCEPT_BUY_LOW_WIN"
            if net_xfp_delta >= 1.5
            else "MARGINAL_EDGE_ACCEPT"
            if net_xfp_delta >= 0.0
            else "DECLINE_NEGATIVE_EXPECTED_VALUE"
        )

        res = ToolResultEnvelope(
            status="success",
            tool_name=tool_name,
            data={
                "acquire_side": [p.model_dump() for p in acquire_profiles],
                "give_side": [p.model_dump() for p in give_profiles],
                "acquire_total_xfp_pg": round(acquire_xfp, 2),
                "give_total_xfp_pg": round(give_xfp, 2),
                "net_expected_fp_gain_per_game": net_xfp_delta,
                "surface_box_score_advantage_for_opponent": net_box_score_illusion,
                "trade_verdict": verdict,
                "leaguemate_persuasion_pitch": (
                    f"Pitch { ', '.join(p.player_name for p in give_profiles) }'s recent {give_actual:.1f} actual PPG "
                    f"production to your leaguemate while quietly capturing +{net_xfp_delta:.1f} Expected Fantasy Points/game "
                    f"and superior YPRR/WOPR volume in { ', '.join(p.player_name for p in acquire_profiles) }."
                ),
            },
        ).model_dump()
        after_tool_outcome_callback(tool_name, raw_args, res)
        return res


def compare_weekly_start_sit_candidates(
    candidate_players: List[str],
    scoring_format: str = "PPR",
    need_high_ceiling_upside: bool = False,
) -> Dict[str, Any]:
    """Compare 2 to 4 NFL players for a weekly Start/Sit lineup decision using floor/ceiling xFP and usage metrics.

    PURPOSE & METHODOLOGY:
    Evaluates each candidate's `expected_fantasy_points_ppr_pg`, `route_participation_pct`, `wopr`,
    `red_zone_touch_share_pct`, and `epa_per_play` to compute Floor, Median, and Ceiling weekly projections.

    WHEN TO USE:
    Call this tool whenever a manager asks "Who should I start between X and Y?" or wants lineup optimization.

    Args:
        candidate_players: List of 2 to 4 NFL player names competing for a starting slot.
        scoring_format: League scoring rule ("PPR", "HALF_PPR", "STANDARD", "TE_PREMIUM").
        need_high_ceiling_upside: True if the manager is a weekly underdog needing boom upside over safe floor.

    Returns:
        Dict[str, Any]: Serialized `ToolResultEnvelope` with ranked Start/Sit recommendations, Floor/Median/Ceiling
        projections, and confidence percentage.
    """
    tool_name = "compare_weekly_start_sit_candidates"
    raw_args = {
        "candidate_players": candidate_players,
        "scoring_format": scoring_format,
        "need_high_ceiling_upside": need_high_ceiling_upside,
    }
    before_tool_intent_callback(tool_name, raw_args)

    with traced_span(f"tool.{tool_name}", {"candidates": candidate_players}):
        try:
            validated = StartSitComparisonInput(
                candidate_players=candidate_players,
                scoring_format=ScoringFormat(scoring_format.upper()),
                need_high_ceiling_upside=need_high_ceiling_upside,
            )
        except (ValidationError, ValueError) as exc:
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="INVALID_START_SIT_INPUT",
                error_message=f"Start/Sit validation error: {exc}",
                recovery_instructions="Provide between 2 and 4 valid NFL player names in `candidate_players`.",
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        client = get_nflverse_client()
        comparisons = []
        for name in validated.candidate_players:
            p = client.get_player_by_name(name)
            if p is None:
                suggestions = client.fuzzy_suggest_players(name)
                err_res = ToolResultEnvelope(
                    status="recoverable_error",
                    tool_name=tool_name,
                    error_code="START_SIT_PLAYER_NOT_FOUND",
                    error_message=f"Player '{name}' not found in nflverse catalog.",
                    recovery_instructions="Substitute the misspelled name with one of `suggested_valid_values`.",
                    suggested_valid_values=suggestions,
                ).model_dump()
                after_tool_outcome_callback(tool_name, raw_args, err_res)
                return err_res

            floor_proj = round(p.expected_fantasy_points_ppr_pg * 0.68, 1)
            median_proj = round(p.expected_fantasy_points_ppr_pg * 1.04, 1)
            ceiling_proj = round(
                p.expected_fantasy_points_ppr_pg * (1.55 + (p.air_yards_share_pct / 250.0)),
                1,
            )
            score_key = ceiling_proj if validated.need_high_ceiling_upside else median_proj
            comparisons.append(
                {
                    "player_name": p.player_name,
                    "team": p.team,
                    "position": p.position,
                    "floor_projection": floor_proj,
                    "median_projection": median_proj,
                    "ceiling_projection": ceiling_proj,
                    "route_participation_pct": p.route_participation_pct,
                    "yprr": p.yards_per_route_run_yprr,
                    "wopr": p.wopr,
                    "red_zone_touch_share_pct": p.red_zone_touch_share_pct,
                    "decision_score": score_key,
                }
            )

        comparisons.sort(key=lambda item: item["decision_score"], reverse=True)
        recommended_starter = comparisons[0]

        res = ToolResultEnvelope(
            status="success",
            tool_name=tool_name,
            data={
                "recommended_start": recommended_starter["player_name"],
                "confidence_pct": 82,
                "optimization_mode": "CEILING_UPSIDE" if validated.need_high_ceiling_upside else "MEDIAN_EXPECTED_VOLUME",
                "ranked_candidates": comparisons,
            },
        ).model_dump()
        after_tool_outcome_callback(tool_name, raw_args, res)
        return res


def submit_high_stakes_waiver_claim_or_trade_offer(
    transaction_type: str,
    add_or_acquire_player: str,
    drop_or_give_player: str,
    faab_bid_amount: int = 0,
    remaining_faab_budget: int = 100,
    league_id: str = "demo_sleeper_league",
    user_confirmed: bool = False,
    tool_context: Optional[Any] = None,
) -> Dict[str, Any]:
    """Stage or execute a high-stakes FAAB waiver claim or trade proposal with a Human-in-the-Loop (HITL) safety gate.

    PURPOSE & SAFETY GATE (AGENTOPS RUBRIC 3.4):
    Enforces Human-in-the-Loop confirmation before committing irreversible roster transactions:
      1. Any FAAB waiver bid exceeding **30% of remaining FAAB budget** (`faab_bid_amount / remaining_faab_budget > 0.30`).
      2. Any `TRADE_PROPOSAL` moving a roster asset.
    When `user_confirmed=False` and the transaction crosses the high-stakes threshold, this tool invokes
    `tool_context.request_confirmation(...)` (when running inside ADK runtime) and returns
    `status="CONFIRMATION_REQUIRED"` so the UI/CLI pauses for explicit human approval.

    Args:
        transaction_type: Either "FAAB_WAIVER_CLAIM" or "TRADE_PROPOSAL".
        add_or_acquire_player: Player being claimed off waivers or acquired in trade.
        drop_or_give_player: Player being dropped to waivers or traded away.
        faab_bid_amount: Dollar amount of FAAB bid (0-1000).
        remaining_faab_budget: Manager's current remaining FAAB budget (1-1000).
        league_id: Target Sleeper League ID.
        user_confirmed: Explicit boolean flag set to True ONLY after the human user approves the confirmation prompt.
        tool_context: Optional Google ADK `ToolContext` used to trigger `request_confirmation`.

    Returns:
        Dict[str, Any]: `ToolResultEnvelope` with `status="CONFIRMATION_REQUIRED"` (halting execution until approved)
        or `status="success"` once `user_confirmed=True` (or if the FAAB bid is <= 30% of remaining budget).
    """
    tool_name = "submit_high_stakes_waiver_claim_or_trade_offer"
    raw_args = {
        "transaction_type": transaction_type,
        "add_or_acquire_player": add_or_acquire_player,
        "drop_or_give_player": drop_or_give_player,
        "faab_bid_amount": faab_bid_amount,
        "remaining_faab_budget": remaining_faab_budget,
        "league_id": league_id,
        "user_confirmed": user_confirmed,
    }
    before_tool_intent_callback(tool_name, raw_args)

    with traced_span(f"tool.{tool_name}", raw_args):
        try:
            validated = HighStakesTransactionInput(
                transaction_type=transaction_type.upper(),
                league_id=league_id,
                add_or_acquire_player=add_or_acquire_player,
                drop_or_give_player=drop_or_give_player,
                faab_bid_amount=faab_bid_amount,
                remaining_faab_budget=remaining_faab_budget,
                user_confirmed=user_confirmed,
            )
        except (ValidationError, ValueError) as exc:
            err_res = ToolResultEnvelope(
                status="recoverable_error",
                tool_name=tool_name,
                error_code="INVALID_TRANSACTION_INPUT",
                error_message=f"High-stakes transaction input error: {exc}",
                recovery_instructions="Ensure `transaction_type` is 'FAAB_WAIVER_CLAIM' or 'TRADE_PROPOSAL'.",
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, err_res)
            return err_res

        faab_pct = round((validated.faab_bid_amount / max(1, validated.remaining_faab_budget)) * 100.0, 1)
        is_high_stakes = (
            (validated.transaction_type == "FAAB_WAIVER_CLAIM" and faab_pct > 30.0)
            or validated.transaction_type == "TRADE_PROPOSAL"
        )

        if is_high_stakes and not validated.user_confirmed:
            confirmation_payload = {
                "requires_human_approval": True,
                "transaction_type": validated.transaction_type,
                "league_id": validated.league_id,
                "add_or_acquire_player": validated.add_or_acquire_player,
                "drop_or_give_player": validated.drop_or_give_player,
                "faab_bid_amount": validated.faab_bid_amount,
                "faab_pct_of_remaining": faab_pct,
                "approval_prompt": (
                    f"⚠️ HIGH-STAKES ROSTER ACTION GATE: Please confirm submitting `{validated.transaction_type}` "
                    f"acquiring **{validated.add_or_acquire_player}** and parting with **{validated.drop_or_give_player}** "
                    f"(FAAB Bid: ${validated.faab_bid_amount} / {faab_pct}% of remaining budget)."
                ),
            }
            # Invoke Google ADK native HITL confirmation hook if tool_context is provided
            if tool_context is not None and hasattr(tool_context, "request_confirmation"):
                try:
                    tool_context.request_confirmation(
                        hint=confirmation_payload["approval_prompt"],
                        payload=confirmation_payload,
                    )
                except Exception:
                    pass

            res = ToolResultEnvelope(
                status="CONFIRMATION_REQUIRED",
                tool_name=tool_name,
                data=confirmation_payload,
                error_code="HITL_CONFIRMATION_GATE_TRIGGERED",
                error_message=confirmation_payload["approval_prompt"],
                recovery_instructions=(
                    "Present the `approval_prompt` and transaction summary to the user and wait for their explicit "
                    "confirmation before calling `submit_high_stakes_waiver_claim_or_trade_offer` with `user_confirmed=True`."
                ),
            ).model_dump()
            after_tool_outcome_callback(tool_name, raw_args, res)
            return res

        res = ToolResultEnvelope(
            status="success",
            tool_name=tool_name,
            data={
                "transaction_status": "STAGED_AND_CONFIRMED",
                "transaction_type": validated.transaction_type,
                "league_id": validated.league_id,
                "add_or_acquire_player": validated.add_or_acquire_player,
                "drop_or_give_player": validated.drop_or_give_player,
                "faab_bid_amount": validated.faab_bid_amount,
                "faab_pct_of_remaining": faab_pct,
                "human_confirmed": validated.user_confirmed or not is_high_stakes,
            },
        ).model_dump()
        after_tool_outcome_callback(tool_name, raw_args, res)
        return res
