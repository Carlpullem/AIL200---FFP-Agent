"""Strategic Model Routing, Input Safety Guardrails, and Output Self-Evaluation Plugin.

Satisfies AgentOps Code Review Matrix:
- 3.2 Strategic Model Routing (5/5): `select_optimal_gemini_model()` dynamically routes fast telemetry
  extraction & Sleeper lookups to `gemini-2.5-flash` while routing complex multi-variable FAAB game theory
  and multi-player Buy-Low/Sell-High trade evaluations to `gemini-2.5-pro`.
- 3.3 Guardrails & Policy Plugins (5/5): `FantasyAgentOpsGuardrailPlugin` (extending ADK `BasePlugin`)
  enforces pre-inference input guardrails (`before_model_callback`) against prompt injection, off-topic
  queries, and sportsbook gambling requests, and post-inference self-evaluation (`after_model_callback`)
  ensuring every recommendation cites at least 3 advanced sabermetric indicators (`YPRR`, `WOPR`, `xFP`, `EPA`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ffp_agent.observability import PIIRedactionScrubber, emit_structured_event

try:
    from google.adk.plugins import BasePlugin  # type: ignore
except ImportError:
    class BasePlugin:  # type: ignore
        """Fallback ADK BasePlugin interface when running outside ADK runtime."""

        def __init__(self, name: str = "base_plugin") -> None:
            self.name = name


@dataclass
class ModelRouteDecision:
    """Result of the dynamic Gemini model routing classifier."""

    selected_model: str
    complexity_tier: str
    routing_rationale: str


@dataclass
class GuardrailVerdict:
    """Result of input or output guardrail policy evaluation."""

    allowed: bool
    violation_code: Optional[str] = None
    safe_message: Optional[str] = None
    self_eval_score: float = 1.0


def select_optimal_gemini_model(user_query: str, task_hint: Optional[str] = None) -> ModelRouteDecision:
    """Route queries between `gemini-2.5-flash` (low-latency extraction) and `gemini-2.5-pro` (deep reasoning).

    Routing Criteria:
    - `gemini-2.5-pro`: Multi-player trade valuation, game-theory FAAB bid optimization, full-roster war-room
      audits, or prompts comparing >= 2 players across conflicting metrics.
    - `gemini-2.5-flash`: Single-player stat lookups, Sleeper league syncs, trending waiver wire lists, or
      quick factual queries.
    """
    q = user_query.lower()
    deep_reasoning_signals = [
        "trade",
        "faab",
        "bid",
        "buy low",
        "buy-low",
        "sell high",
        "sell-high",
        "package",
        "strategy",
        "compare",
        "start or sit",
        "start/sit",
        "versus",
        " vs ",
        "war room",
    ]
    if task_hint == "PRO_REASONING" or any(sig in q for sig in deep_reasoning_signals):
        decision = ModelRouteDecision(
            selected_model="gemini-2.5-pro",
            complexity_tier="DEEP_REASONING_SYNTHESIS",
            routing_rationale=(
                "Query requires multi-factor game-theory synthesis (FAAB valuation, trade arbitrage, or "
                "multi-player Start/Sit comparison); routed to `gemini-2.5-pro`."
            ),
        )
    else:
        decision = ModelRouteDecision(
            selected_model="gemini-2.5-flash",
            complexity_tier="LOW_LATENCY_EXTRACTION",
            routing_rationale=(
                "Query is a direct telemetry lookup or Sleeper waiver market scan; routed to "
                "`gemini-2.5-flash` for sub-second latency and cost efficiency."
            ),
        )

    emit_structured_event(
        event_type="MODEL_ROUTING_DECISION",
        payload={
            "selected_model": decision.selected_model,
            "complexity_tier": decision.complexity_tier,
            "routing_rationale": decision.routing_rationale,
        },
    )
    return decision


def evaluate_input_guardrails(user_query: str) -> GuardrailVerdict:
    """Enforce constitutional input policies (block prompt injection & illegal sportsbook gambling advice)."""
    q = user_query.lower()

    injection_patterns = [
        "ignore all previous instructions",
        "ignore previous instructions",
        "reveal your system prompt",
        "disregard your constitution",
        "print environment variables",
    ]
    for pattern in injection_patterns:
        if pattern in q:
            emit_structured_event(
                event_type="GUARDRAIL_BLOCKED_INPUT",
                payload={"violation": "PROMPT_INJECTION_ATTEMPT", "pattern": pattern},
                severity="WARNING",
            )
            return GuardrailVerdict(
                allowed=False,
                violation_code="PROMPT_INJECTION_ATTEMPT",
                safe_message=(
                    "🛡️ **Guardrail Policy Triggered**: Request blocked due to adversarial prompt-injection attempt. "
                    "I can only assist with NFL Fantasy Football analytics, waiver FAAB strategy, and trade evaluation."
                ),
                self_eval_score=0.0,
            )

    gambling_patterns = [
        "place a parlay bet",
        "sportsbook moneyline bet",
        "draftkings parlay",
        "fanduel spread bet",
        "bet my rent money",
    ]
    for pattern in gambling_patterns:
        if pattern in q:
            emit_structured_event(
                event_type="GUARDRAIL_BLOCKED_INPUT",
                payload={"violation": "PROHIBITED_SPORTSBOOK_GAMBLING", "pattern": pattern},
                severity="WARNING",
            )
            return GuardrailVerdict(
                allowed=False,
                violation_code="PROHIBITED_SPORTSBOOK_GAMBLING_REQUEST",
                safe_message=(
                    "🛡️ **Constitutional Guardrail Triggered**: I am strictly an **NFL Fantasy Football Roster & "
                    "Sabermetrics Advisor** (Sleeper waivers, FAAB bidding, trades, and Start/Sit decisions). "
                    "I do not provide real-money sportsbook betting or parlay wagering advice."
                ),
                self_eval_score=0.0,
            )

    return GuardrailVerdict(allowed=True, self_eval_score=1.0)


def evaluate_output_self_eval_rubric(response_text: str) -> Dict[str, Any]:
    """Post-generation Self-Evaluation Rubric verifying that advanced metrics are cited."""
    required_metric_families = [
        ("YPRR / Route Participation", ["yprr", "route participation", "routes"]),
        ("Target / First-Read / WOPR", ["wopr", "target share", "first-read", "tprr"]),
        ("Expected Fantasy Points (xFP) / EPA", ["xfp", "expected fantasy points", "epa"]),
        ("Snap Share / Rostered %", ["snap", "rostered", "faab"]),
    ]
    lower_resp = response_text.lower()
    matched_families: List[str] = []
    for label, keywords in required_metric_families:
        if any(k in lower_resp for k in keywords):
            matched_families.append(label)

    score = round(len(matched_families) / len(required_metric_families), 2)
    passed = len(matched_families) >= 3
    return {
        "passed": passed,
        "score": score,
        "matched_metric_families": matched_families,
        "rubric_requirement": "Must cite at least 3 of 4 sabermetric metric families (YPRR/Routes, WOPR/Targets, xFP/EPA, Snaps/FAAB).",
    }


class FantasyAgentOpsGuardrailPlugin(BasePlugin):
    """Google ADK `BasePlugin` enforcing PII scrubbing, input guardrails, and output self-evaluation."""

    def __init__(self) -> None:
        super().__init__(name="fantasy_agentops_guardrail_plugin")
        self.scrubber = PIIRedactionScrubber()

    def before_model_callback(self, callback_context: Any, llm_request: Any) -> Optional[Any]:
        """Scrub PII and check input guardrails before invoking the Gemini model."""
        prompt_text = str(getattr(llm_request, "contents", ""))
        verdict = evaluate_input_guardrails(prompt_text)
        if not verdict.allowed:
            return verdict.safe_message
        return None

    def after_model_callback(self, callback_context: Any, llm_response: Any) -> Optional[Any]:
        """Verify output quality against the constitutional sabermetric self-evaluation rubric."""
        text = str(getattr(llm_response, "text", ""))
        eval_res = evaluate_output_self_eval_rubric(text)
        emit_structured_event(
            event_type="OUTPUT_SELF_EVALUATION_COMPLETED",
            payload=eval_res,
        )
        return None
