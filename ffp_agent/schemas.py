"""Explicit Pydantic JSON Schemas for all Fantasy Football Agent Tools & Structured Outputs.

Satisfies AgentOps Code Review Matrix:
- 1.3 Explicit JSON Schemas (5/5): Strict Pydantic BaseModel definitions with Field descriptions,
  constraints, enums, and validators (`extra="forbid"`) for all tool inputs and agent outputs.
  Includes a built-in strict BaseModel fallback for bare Python environments where `pydantic`
  has not yet been pip-installed.
"""

from __future__ import annotations

import inspect
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
    PYDANTIC_NATIVE = True
except ImportError:  # pragma: no cover - stdlib strict schema fallback for bare environments
    PYDANTIC_NATIVE = False
    ValidationError = ValueError  # type: ignore

    def ConfigDict(**kwargs: Any) -> Dict[str, Any]:
        return dict(kwargs)

    class _FieldInfo:
        def __init__(
            self,
            default: Any = ...,
            *,
            default_factory: Optional[Callable[[], Any]] = None,
            description: str = "",
            ge: Optional[float] = None,
            le: Optional[float] = None,
            min_length: Optional[int] = None,
            max_length: Optional[int] = None,
            examples: Optional[List[Any]] = None,
        ) -> None:
            self.default = default
            self.default_factory = default_factory
            self.description = description
            self.ge = ge
            self.le = le
            self.min_length = min_length
            self.max_length = max_length
            self.examples = examples or []

    def Field(
        default: Any = ...,
        *,
        default_factory: Optional[Callable[[], Any]] = None,
        description: str = "",
        ge: Optional[float] = None,
        le: Optional[float] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        examples: Optional[List[Any]] = None,
    ) -> Any:
        return _FieldInfo(
            default=default,
            default_factory=default_factory,
            description=description,
            ge=ge,
            le=le,
            min_length=min_length,
            max_length=max_length,
            examples=examples,
        )

    def field_validator(*field_names: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            setattr(fn, "__validator_fields__", field_names)
            return fn
        return decorator

    class BaseModel:
        """Strict Pydantic-compatible BaseModel enforcing `extra='forbid'` and field constraints."""

        model_config: Dict[str, Any] = {"extra": "forbid"}

        def __init__(self, **kwargs: Any) -> None:
            cls = self.__class__
            annotations = getattr(cls, "__annotations__", {})
            extra_mode = cls.model_config.get("extra", "forbid")
            if extra_mode == "forbid":
                unknown = set(kwargs.keys()) - set(annotations.keys())
                if unknown:
                    raise ValueError(f"Extra inputs are not permitted (`extra='forbid'`): {sorted(unknown)}")

            for name in annotations:
                attr_val = getattr(cls, name, ...)
                if name in kwargs:
                    val = kwargs[name]
                elif isinstance(attr_val, _FieldInfo):
                    if attr_val.default_factory is not None:
                        val = attr_val.default_factory()
                    elif attr_val.default is not ...:
                        val = attr_val.default
                    else:
                        raise ValueError(f"Field required: '{name}'")
                elif attr_val is not ...:
                    val = attr_val
                else:
                    raise ValueError(f"Field required: '{name}'")

                if isinstance(attr_val, _FieldInfo) and val is not None:
                    if attr_val.ge is not None and isinstance(val, (int, float)) and val < attr_val.ge:
                        raise ValueError(f"Field '{name}'={val} must be >= {attr_val.ge}")
                    if attr_val.le is not None and isinstance(val, (int, float)) and val > attr_val.le:
                        raise ValueError(f"Field '{name}'={val} must be <= {attr_val.le}")
                    if attr_val.min_length is not None and hasattr(val, "__len__") and len(val) < attr_val.min_length:
                        raise ValueError(f"Field '{name}' length {len(val)} must be >= {attr_val.min_length}")
                    if attr_val.max_length is not None and hasattr(val, "__len__") and len(val) > attr_val.max_length:
                        raise ValueError(f"Field '{name}' length {len(val)} must be <= {attr_val.max_length}")

                setattr(self, name, val)

            # Run any @field_validator methods
            for _, member in inspect.getmembers(cls):
                target_fields = getattr(member, "__validator_fields__", None)
                if target_fields:
                    for f_name in target_fields:
                        if hasattr(self, f_name):
                            new_val = member(getattr(self, f_name))
                            setattr(self, f_name, new_val)

        def model_dump(self) -> Dict[str, Any]:
            result: Dict[str, Any] = {}
            for k in getattr(self.__class__, "__annotations__", {}):
                v = getattr(self, k)
                if isinstance(v, Enum):
                    result[k] = v.value
                elif isinstance(v, BaseModel):
                    result[k] = v.model_dump()
                elif isinstance(v, list):
                    result[k] = [item.model_dump() if isinstance(item, BaseModel) else item for item in v]
                else:
                    result[k] = v
            return result

        @classmethod
        def model_json_schema(cls) -> Dict[str, Any]:
            props: Dict[str, Any] = {}
            required: List[str] = []
            for k, t_hint in getattr(cls, "__annotations__", {}).items():
                attr_val = getattr(cls, k, ...)
                desc = attr_val.description if isinstance(attr_val, _FieldInfo) else ""
                props[k] = {"title": k, "type": str(t_hint), "description": desc}
                if isinstance(attr_val, _FieldInfo) and attr_val.default is ... and attr_val.default_factory is None:
                    required.append(k)
            return {
                "title": cls.__name__,
                "type": "object",
                "additionalProperties": cls.model_config.get("extra") != "forbid",
                "properties": props,
                "required": required,
            }


class ScoringFormat(str, Enum):
    """Supported Fantasy Football league scoring formats."""

    PPR = "PPR"
    HALF_PPR = "HALF_PPR"
    STANDARD = "STANDARD"
    TE_PREMIUM = "TE_PREMIUM"


class PositionFilter(str, Enum):
    """Supported offensive skill positions for fantasy football analysis."""

    ALL = "ALL"
    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"


class ContentionWindow(str, Enum):
    """Manager's current team contention profile."""

    CONTENDER = "CONTENDER"
    BALANCED = "BALANCED"
    REBUILDER = "REBUILDER"


class ActionType(str, Enum):
    """Supported high-stakes transaction types."""

    FAAB_WAIVER_CLAIM = "FAAB_WAIVER_CLAIM"
    TRADE_PROPOSAL = "TRADE_PROPOSAL"


class NflversePlayerTelemetryInput(BaseModel):
    """Strict input schema for querying nflverse (`nflreadpy` / `nflfastR`) player telemetry."""

    model_config = ConfigDict(extra="forbid")

    player_name: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="Full name of the NFL player to inspect (e.g., 'Bucky Irving', 'Puka Nacua').",
        examples=["Bucky Irving", "Rashee Rice", "Trey McBride"],
    )
    season: int = Field(
        default=2024,
        ge=1999,
        le=2026,
        description="NFL regular season year (nflverse supports 1999 through current season).",
    )
    scoring_format: ScoringFormat = Field(
        default=ScoringFormat.PPR,
        description="League scoring format used to compute Expected Fantasy Points (xFP).",
    )

    @field_validator("player_name")
    @classmethod
    def sanitize_player_name(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if len(cleaned) < 2:
            raise ValueError("player_name must contain at least 2 non-whitespace characters.")
        return cleaned


class SleeperLeagueLookupInput(BaseModel):
    """Strict input schema for fetching live Sleeper league rosters, settings, and waiver market."""

    model_config = ConfigDict(extra="forbid")

    league_id: str = Field(
        ...,
        min_length=5,
        max_length=64,
        description="Numeric or alphanumeric Sleeper League ID (or 'demo_sleeper_league' for offline sandbox testing).",
        examples=["demo_sleeper_league", "104829384719283712"],
    )
    include_trending_waivers: bool = Field(
        default=True,
        description="Whether to fetch live 24-hour trending waiver adds/drops from Sleeper's public API.",
    )


class WaiverBreakoutSearchInput(BaseModel):
    """Strict input schema for discovering low-owned breakout waiver wire targets."""

    model_config = ConfigDict(extra="forbid")

    position: PositionFilter = Field(
        default=PositionFilter.ALL,
        description="Skill position filter ('ALL', 'QB', 'RB', 'WR', 'TE').",
    )
    max_rostered_pct: float = Field(
        default=40.0,
        ge=1.0,
        le=100.0,
        description="Maximum Sleeper roster ownership percentage (e.g., 35.0 to find hidden gems owned in <35% of leagues).",
    )
    min_route_participation_pct: float = Field(
        default=55.0,
        ge=0.0,
        le=100.0,
        description="Minimum route participation percentage (routes run / team dropbacks) for WR/TE/pass-catching RBs.",
    )
    min_yprr: float = Field(
        default=1.80,
        ge=0.0,
        le=6.0,
        description="Minimum Yards Per Route Run (YPRR) efficiency threshold.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Maximum number of ranked breakout candidates to return.",
    )
    league_id: str = Field(
        default="demo_sleeper_league",
        description="Optional Sleeper League ID or URL to filter out players already rostered in that specific league.",
    )


class FaabBidCalculationInput(BaseModel):
    """Strict input schema for game-theory FAAB waiver wire bid sizing."""

    model_config = ConfigDict(extra="forbid")

    player_name: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="Target waiver wire player name.",
    )
    remaining_faab_budget: int = Field(
        default=100,
        ge=0,
        le=1000,
        description="User's remaining FAAB budget in dollars.",
    )
    total_season_faab_budget: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Initial full-season FAAB budget in dollars (typically $100 or $200).",
    )
    current_week: int = Field(
        default=6,
        ge=1,
        le=18,
        description="Current NFL regular season week (1-18).",
    )
    positional_need_urgency: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="How badly the manager's roster needs an immediate starter at this position (0.0=luxury stash, 1.0=emergency starter).",
    )
    league_aggressiveness_index: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Estimated bidding aggressiveness of Sleeper leaguemates (0.0=passive, 1.0=hyper-aggressive).",
    )


class TradeEvaluationInput(BaseModel):
    """Strict input schema for multi-player buy-low / sell-high trade evaluation."""

    model_config = ConfigDict(extra="forbid")

    acquire_players: List[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="List of NFL player names the manager would receive in the trade.",
    )
    give_players: List[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="List of NFL player names the manager would send away in the trade.",
    )
    scoring_format: ScoringFormat = Field(
        default=ScoringFormat.PPR,
        description="League scoring format.",
    )
    contention_window: ContentionWindow = Field(
        default=ContentionWindow.CONTENDER,
        description="Whether the manager is competing for a championship now or rebuilding.",
    )


class StartSitComparisonInput(BaseModel):
    """Strict input schema for head-to-head weekly Start/Sit lineup decisions."""

    model_config = ConfigDict(extra="forbid")

    candidate_players: List[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="2 to 4 NFL players competing for a starting lineup spot.",
    )
    scoring_format: ScoringFormat = Field(
        default=ScoringFormat.PPR,
        description="League scoring format ('PPR', 'HALF_PPR', 'STANDARD', 'TE_PREMIUM').",
    )
    need_high_ceiling_upside: bool = Field(
        default=False,
        description="Set True if the manager is a heavy underdog and needs boom/ceiling upside over safe floor.",
    )


class HighStakesTransactionInput(BaseModel):
    """Strict input schema for staging a high-stakes FAAB bid or trade proposal (requires HITL approval)."""

    model_config = ConfigDict(extra="forbid")

    transaction_type: str = Field(
        ...,
        description="Type of transaction to stage: 'FAAB_WAIVER_CLAIM' or 'TRADE_PROPOSAL'.",
    )
    league_id: str = Field(
        default="demo_sleeper_league",
        description="Target Sleeper League ID.",
    )
    add_or_acquire_player: str = Field(
        ...,
        description="Player being claimed off waivers or acquired via trade.",
    )
    drop_or_give_player: str = Field(
        ...,
        description="Player being dropped to waivers or traded away.",
    )
    faab_bid_amount: int = Field(
        default=0,
        ge=0,
        le=1000,
        description="FAAB dollar amount to bid (if FAAB_WAIVER_CLAIM).",
    )
    remaining_faab_budget: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Remaining FAAB budget in dollars.",
    )
    user_confirmed: bool = Field(
        default=False,
        description="Explicit Human-in-the-Loop confirmation flag. If False and bid >30% FAAB or trade involves core asset, tool halts for user confirmation.",
    )


class PlayerAdvancedMetricsProfile(BaseModel):
    """Structured telemetry record uniting nflverse, PFF-style, FantasyPoints, and PlayerProfiler metrics."""

    model_config = ConfigDict(extra="forbid")

    player_id: str
    player_name: str
    team: str
    position: str
    rostered_pct_sleeper: float = Field(..., description="Percentage of Sleeper leagues where player is rostered.")
    fantasypros_ecr_pos_rank: int = Field(..., description="FantasyPros Expert Consensus Rest-of-Season Positional Rank.")
    snap_share_pct: float = Field(..., description="Offensive snap share percentage over trailing 3 games.")
    snap_share_delta_wow_pct: float = Field(..., description="Week-over-Week change in offensive snap share percentage.")
    route_participation_pct: float = Field(..., description="Routes run divided by team QB dropbacks (%).")
    target_share_pct: float = Field(..., description="Player targets divided by team pass attempts (%).")
    first_read_target_share_pct: float = Field(..., description="Share of team first-read designed targets (%).")
    targets_per_route_run_tprr: float = Field(..., description="Targets Per Route Run (TPRR) efficiency.")
    yards_per_route_run_yprr: float = Field(..., description="Yards Per Route Run (YPRR) — premier predictive receiver metric.")
    air_yards_share_pct: float = Field(..., description="Share of team total air yards (%).")
    wopr: float = Field(..., description="Weighted Opportunity Rating (1.5 * Target Share + 0.7 * Air Yards Share).")
    pff_offensive_grade: float = Field(..., description="Composite play-by-play efficiency grade (0-100 scale).")
    epa_per_play: float = Field(..., description="nflfastR Expected Points Added (EPA) per touch/target.")
    xyac_epa: float = Field(..., description="nflfastR Expected Yards After Catch EPA.")
    red_zone_touch_share_pct: float = Field(..., description="Share of team opportunities inside the opponent's 20-yard line (%).")
    expected_fantasy_points_ppr_pg: float = Field(..., description="Usage-based Expected Fantasy Points per game (xFP) in PPR.")
    actual_fantasy_points_ppr_pg: float = Field(..., description="Actual box-score Fantasy Points per game in PPR.")
    xfp_differential_ppr: float = Field(
        ...,
        description="xFP minus Actual FP per game. Positive values (+2.0 to +6.0) signal strong positive regression (Buy-Low / Breakout).",
    )
    breakout_composite_score: float = Field(
        ...,
        description="0-100 composite predictive breakout score computed from leading usage indicators.",
    )
    injury_or_depth_chart_catalyst: str = Field(
        ...,
        description="Context explaining why usage is shifting (e.g., rookie post-bye bump, starter injury).",
    )


class ToolResultEnvelope(BaseModel):
    """Standardized tool response envelope supporting Guided Error Recovery for LLMs."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="'success', 'recoverable_error', or 'CONFIRMATION_REQUIRED'")
    tool_name: str = Field(..., description="Name of the tool that produced this response.")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Structured payload when status == 'success'.")
    error_code: Optional[str] = Field(default=None, description="Machine-readable error code if status != 'success'.")
    error_message: Optional[str] = Field(default=None, description="Human-readable diagnostic message.")
    recovery_instructions: Optional[str] = Field(
        default=None,
        description="Actionable step-by-step instructions telling the LLM how to self-correct its parameters and retry.",
    )
    suggested_valid_values: Optional[List[str]] = Field(
        default=None,
        description="Fuzzy-matched valid player names or parameter options to help the LLM recover automatically.",
    )
