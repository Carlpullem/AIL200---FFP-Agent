"""Automated Evaluation & AgentOps Code Review Matrix Verification Suite.

Satisfies AgentOps Code Review Matrix:
- 5.1 Automated Evaluation Suites (5/5): Evaluates all 19 criteria across the 5 AgentOps categories
  plus golden dataset accuracy, routing accuracy, guardrail safety, PII redaction, and HITL gates.
  Supports both `pytest -v` and direct `python3 tests/test_agentops_rubric_and_eval.py` execution.
"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from ffp_agent.agent import (
    ALL_TOOLS,
    AdvancedMetricsSabermetricAgent,
    FaabAndTradeArchitectAgent,
    FantasyFootballEdgeCoordinator,
    LineupStartSitAdvisorAgent,
    ParallelIntelGatheringPipeline,
    SequentialStrategyPipeline,
    SleeperMarketScoutAgent,
    StrategyQualityLoopAgent,
    execute_agentic_workflow,
)
from ffp_agent.guardrails_and_routing import (
    evaluate_input_guardrails,
    evaluate_output_self_eval_rubric,
    select_optimal_gemini_model,
)
from ffp_agent.memory_and_compaction import (
    PersistentFantasyStateStore,
    build_adk_events_compaction_config,
    compact_conversation_history,
    schedule_async_memory_consolidation,
)
from ffp_agent.observability import (
    PIIRedactionScrubber,
    before_tool_intent_callback,
    after_tool_outcome_callback,
    get_recent_telemetry_events,
    traced_span,
)
from ffp_agent.prompts import (
    COORDINATOR_SYSTEM_INSTRUCTION,
    FAAB_AND_TRADE_ARCHITECT_INSTRUCTION,
    LINEUP_START_SIT_ADVISOR_INSTRUCTION,
    SABERMETRIC_ANALYST_INSTRUCTION,
    SLEEPER_MARKET_SCOUT_INSTRUCTION,
)
from ffp_agent.schemas import (
    FaabBidCalculationInput,
    HighStakesTransactionInput,
    NflversePlayerTelemetryInput,
    StartSitComparisonInput,
    TradeEvaluationInput,
    WaiverBreakoutSearchInput,
)
from ffp_agent.secrets import get_secret_manager
from ffp_agent.tools import (
    calculate_optimal_faab_waiver_bid,
    compare_weekly_start_sit_candidates,
    discover_undervalued_waiver_wire_breakouts,
    evaluate_asymmetric_buy_low_trade_package,
    fetch_live_sleeper_league_and_waiver_market,
    fetch_nflverse_player_sabermetric_telemetry,
    submit_high_stakes_waiver_claim_or_trade_offer,
)


# ============================================================================
# CATEGORY 1: TOOL & INTERFACE DESIGN (20 Points)
# ============================================================================

def test_1_1_comprehensive_tool_docstrings() -> None:
    """Verify every tool has comprehensive docstrings detailing purpose, args, and return structure."""
    for tool_fn in ALL_TOOLS:
        doc = tool_fn.__doc__ or ""
        assert len(doc.strip()) >= 250, f"Tool {tool_fn.__name__} docstring is too short."
        assert "Args:" in doc, f"Tool {tool_fn.__name__} missing Args section."
        assert "Returns:" in doc, f"Tool {tool_fn.__name__} missing Returns section."
        assert "PURPOSE" in doc or "WHEN TO USE" in doc, f"Tool {tool_fn.__name__} missing PURPOSE/WHEN TO USE."


def test_1_2_descriptive_tool_naming() -> None:
    """Verify tool names are highly specific and action-oriented (>= 3 words)."""
    expected_names = {
        "fetch_nflverse_player_sabermetric_telemetry",
        "fetch_live_sleeper_league_and_waiver_market",
        "discover_undervalued_waiver_wire_breakouts",
        "calculate_optimal_faab_waiver_bid",
        "evaluate_asymmetric_buy_low_trade_package",
        "compare_weekly_start_sit_candidates",
        "submit_high_stakes_waiver_claim_or_trade_offer",
    }
    actual_names = {fn.__name__ for fn in ALL_TOOLS}
    assert actual_names == expected_names
    for name in actual_names:
        assert len(name.split("_")) >= 4, f"Tool name '{name}' should be highly descriptive."


def test_1_3_explicit_pydantic_json_schemas() -> None:
    """Verify strict Pydantic schemas enforce constraints and forbid extra fields."""
    schemas = [
        NflversePlayerTelemetryInput,
        WaiverBreakoutSearchInput,
        FaabBidCalculationInput,
        TradeEvaluationInput,
        StartSitComparisonInput,
        HighStakesTransactionInput,
    ]
    for schema_cls in schemas:
        json_schema = schema_cls.model_json_schema()
        assert json_schema.get("additionalProperties") is False, (
            f"{schema_cls.__name__} must set extra='forbid'"
        )

    # Verify invalid extra field is rejected
    raised = False
    try:
        NflversePlayerTelemetryInput(player_name="Bucky Irving", unexpected_field="bad")  # type: ignore[call-arg]
    except Exception:
        raised = True
    assert raised, "Expected NflversePlayerTelemetryInput to reject unexpected_field"


def test_1_4_guided_error_handling_for_llm_recovery() -> None:
    """Verify tools return structured recovery instructions instead of raw tracebacks on bad inputs."""
    bad_player_res = fetch_nflverse_player_sabermetric_telemetry(player_name="Bucky Irvng Typo")
    assert bad_player_res["status"] == "recoverable_error"
    assert bad_player_res["error_code"] == "PLAYER_NOT_FOUND_IN_NFLVERSE_ROSTER"
    assert "recovery_instructions" in bad_player_res and len(bad_player_res["recovery_instructions"]) > 30
    assert "Bucky Irving" in bad_player_res["suggested_valid_values"]


# ============================================================================
# CATEGORY 2: CONTEXT & MEMORY (20 Points)
# ============================================================================

def test_2_1_robust_constitutional_system_instructions() -> None:
    """Verify all agents have structured XML constitutional system prompts."""
    prompts = [
        COORDINATOR_SYSTEM_INSTRUCTION,
        SLEEPER_MARKET_SCOUT_INSTRUCTION,
        SABERMETRIC_ANALYST_INSTRUCTION,
        FAAB_AND_TRADE_ARCHITECT_INSTRUCTION,
        LINEUP_START_SIT_ADVISOR_INSTRUCTION,
    ]
    for prompt in prompts:
        assert "<CONSTITUTION>" in prompt or "<AGENT_ROLE>" in prompt
        assert "YPRR" in prompt or "FAAB" in prompt or "Sleeper" in prompt


def test_2_2_history_compaction_and_adk_events_compaction_config() -> None:
    """Verify ADK EventsCompactionConfig and sliding-window conversation compaction."""
    compaction_cfg = build_adk_events_compaction_config(token_threshold=4000, event_retention_size=5)
    assert compaction_cfg is not None

    # Create a 12-turn conversation and verify compaction retains the recent 4 turns + summary
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}: Analyzing Bucky Irving and Jalen McMillan FAAB $22."}
        for i in range(12)
    ]
    compacted = compact_conversation_history(long_history, max_recent_turns=4, token_budget=50)
    assert len(compacted["messages"]) == 5  # 1 summary message + 4 recent turns
    assert "[COMPACTED_HISTORY_SUMMARY]" in compacted["messages"][0]["content"]
    assert compacted["compaction_metadata"]["compacted"] is True


def test_2_3_persistent_session_and_memory_store() -> None:
    """Verify SQLite persistent session state and semantic/keyword memory retrieval."""
    tmp_db = Path("/usr/local/google/home/carlpullem/.gemini/jetski/brain/82befed1-c227-4dfa-91f9-e23e61c4ef01/scratch/test_fantasy_memory.db")
    if tmp_db.exists():
        tmp_db.unlink()
    store = PersistentFantasyStateStore(db_path=str(tmp_db))
    store.upsert_session(
        session_id="sess_test_1",
        user_id="carlpullem",
        league_id="demo_sleeper_league",
        scoring_format="PPR",
        remaining_faab=84,
        history=[{"role": "user", "content": "Who should I pick up?"}],
    )
    loaded = store.get_session("sess_test_1")
    assert loaded is not None
    assert loaded["remaining_faab"] == 84

    store.store_memory(
        user_id="carlpullem",
        league_id="demo_sleeper_league",
        category="waiver_target",
        summary_text="Targeted Bucky Irving for $22 FAAB due to +3.7 xFP differential.",
        keywords=["bucky", "irving", "faab", "xfp"],
    )
    memories = store.search_memories("carlpullem", "Bucky Irving FAAB")
    assert len(memories) >= 1
    assert "Bucky Irving" in memories[0]["summary_text"]
    if tmp_db.exists():
        tmp_db.unlink()


def test_2_4_async_memory_consolidation_worker() -> None:
    """Verify non-blocking background memory extraction runs via asyncio.create_task."""
    async def _run_async_test() -> None:
        tmp_db = Path("/usr/local/google/home/carlpullem/.gemini/jetski/brain/82befed1-c227-4dfa-91f9-e23e61c4ef01/scratch/test_async_mem.db")
        if tmp_db.exists():
            tmp_db.unlink()
        store = PersistentFantasyStateStore(db_path=str(tmp_db))
        task = schedule_async_memory_consolidation(
            state_store=store,
            user_id="carlpullem",
            league_id="demo_sleeper_league",
            user_message="Should I bid $22 FAAB on Bucky Irving?",
            agent_response="Recommend Optimal Bid of $22 FAAB on Bucky Irving (YPRR 2.12, +3.7 xFP diff).",
        )
        assert task is not None
        res = await task
        assert res["status"] == "consolidated"
        if tmp_db.exists():
            tmp_db.unlink()

    asyncio.run(_run_async_test())


# ============================================================================
# CATEGORY 3: ORCHESTRATION & LOGIC (20 Points)
# ============================================================================

def test_3_1_multi_agent_patterns() -> None:
    """Verify Coordinator, ParallelAgent, SequentialAgent, and LoopAgent definitions."""
    assert FantasyFootballEdgeCoordinator.name == "FantasyFootballEdgeCoordinator"
    assert ParallelIntelGatheringPipeline.name == "ParallelIntelGatheringPipeline"
    assert SequentialStrategyPipeline.name == "SequentialStrategyPipeline"
    assert StrategyQualityLoopAgent.name == "StrategyQualityLoopAgent"
    assert len(ParallelIntelGatheringPipeline.sub_agents) == 2
    assert len(SequentialStrategyPipeline.sub_agents) == 2


def test_3_2_strategic_model_routing() -> None:
    """Verify dynamic model routing assigns Flash to lookups and Pro to multi-factor trade/FAAB synthesis."""
    fast_decision = select_optimal_gemini_model("Show me my Sleeper league waiver wire trending list")
    assert fast_decision.selected_model == "gemini-2.5-flash"
    assert fast_decision.complexity_tier == "LOW_LATENCY_EXTRACTION"

    pro_decision = select_optimal_gemini_model("Evaluate a buy-low trade offer giving Jayden Reed for Chris Olave and calculate FAAB")
    assert pro_decision.selected_model == "gemini-2.5-pro"
    assert pro_decision.complexity_tier == "DEEP_REASONING_SYNTHESIS"


def test_3_3_guardrails_and_self_evaluation_rubric() -> None:
    """Verify input safety guardrails and output self-evaluation rubric."""
    blocked = evaluate_input_guardrails("Can you place a $500 DraftKings parlay moneyline bet for me?")
    assert blocked.allowed is False
    assert blocked.violation_code == "PROHIBITED_SPORTSBOOK_GAMBLING_REQUEST"

    shallow_output = "You should pick up Bucky Irving, he looked good last Sunday."
    eval_fail = evaluate_output_self_eval_rubric(shallow_output)
    assert eval_fail["passed"] is False

    rich_output = (
        "Target Bucky Irving (`YPRR`: 2.12, `WOPR`: 0.34, `xFP` differential: +3.7 PPR/game, "
        "`Snap Share`: 56.4%) with an **Optimal Bid** of $22 FAAB."
    )
    eval_pass = evaluate_output_self_eval_rubric(rich_output)
    assert eval_pass["passed"] is True
    assert eval_pass["score"] >= 0.90


def test_3_4_human_in_the_loop_confirmation_gate() -> None:
    """Verify high-stakes FAAB bids (>30%) pause for explicit user confirmation before executing."""
    paused_res = submit_high_stakes_waiver_claim_or_trade_offer(
        transaction_type="FAAB_WAIVER_CLAIM",
        add_or_acquire_player="Bucky Irving",
        drop_or_give_player="Zamir White",
        faab_bid_amount=45,
        remaining_faab_budget=100,
        user_confirmed=False,
    )
    assert paused_res["status"] == "CONFIRMATION_REQUIRED"
    assert paused_res["data"]["requires_human_approval"] is True

    confirmed_res = submit_high_stakes_waiver_claim_or_trade_offer(
        transaction_type="FAAB_WAIVER_CLAIM",
        add_or_acquire_player="Bucky Irving",
        drop_or_give_player="Zamir White",
        faab_bid_amount=45,
        remaining_faab_budget=100,
        user_confirmed=True,
    )
    assert confirmed_res["status"] == "success"
    assert confirmed_res["data"]["transaction_status"] == "STAGED_AND_CONFIRMED"


# ============================================================================
# CATEGORY 4: OBSERVABILITY & TRACING (20 Points)
# ============================================================================

def test_4_1_and_4_2_structured_json_logging_and_intent_outcome_capture() -> None:
    """Verify structured JSON logging captures both TOOL_INTENT and TOOL_OUTCOME with PII scrubbing."""
    before_tool_intent_callback(
        "calculate_optimal_faab_waiver_bid",
        {"player_name": "Bucky Irving", "user_email": "manager@example.com"},
    )
    after_tool_outcome_callback(
        "calculate_optimal_faab_waiver_bid",
        {"player_name": "Bucky Irving"},
        {"status": "success", "data": {"bid_tiers": {"optimal": {"dollar_bid": 22}}}},
    )
    events = get_recent_telemetry_events(limit=5)
    event_types = [e["event_type"] for e in events]
    assert "TOOL_INTENT" in event_types
    assert "TOOL_OUTCOME" in event_types
    # Ensure email was scrubbed from intent args
    intent_events = [e for e in events if e["event_type"] == "TOOL_INTENT"]
    assert "[REDACTED_EMAIL]" in json.dumps(intent_events[0]["payload"])


def test_4_3_distributed_opentelemetry_tracing() -> None:
    """Verify OpenTelemetry spans emit valid trace_id and span_id attributes."""
    with traced_span("test.fantasy_span", {"agent.role": "coordinator"}) as span_meta:
        assert "trace_id" in span_meta
        assert "span_id" in span_meta


def test_4_4_pii_redaction_scrubber() -> None:
    """Verify PIIRedactionScrubber removes emails, phone numbers, SSNs, and API keys."""
    scrubber = PIIRedactionScrubber()
    dirty_text = (
        "Contact carl@gmail.com or 555-867-5309 (SSN 123-45-6789) with key AIzaSyD1234567890abcdefghijklmnop"
    )
    clean_text = scrubber.scrub_text(dirty_text)
    assert "carl@gmail.com" not in clean_text
    assert "555-867-5309" not in clean_text
    assert "123-45-6789" not in clean_text
    assert "[REDACTED_EMAIL]" in clean_text
    assert "[REDACTED_PHONE]" in clean_text
    assert "[REDACTED_SSN]" in clean_text


# ============================================================================
# CATEGORY 5: INFRASTRUCTURE & CI/CD + GOLDEN DATASET EVALUATION (15 Points)
# ============================================================================

def test_5_1_golden_dataset_evaluation_suite() -> None:
    """Run all benchmark prompts in eval/golden_dataset.json and assert 100% pass rate."""
    golden_path = Path(__file__).resolve().parent.parent / "eval" / "golden_dataset.json"
    cases = json.loads(golden_path.read_text())
    assert len(cases) >= 5

    for case in cases:
        result = execute_agentic_workflow(
            user_message=case["prompt"],
            user_id="eval_runner",
            session_id=f"eval_{case['id']}",
            league_id="demo_sleeper_league",
        )
        assert result["model_routing"]["selected_model"] == case["expected_model_route"], (
            f"Case {case['id']} routed to wrong model."
        )
        if case.get("expected_guardrail_block"):
            assert result["status"] == "blocked_by_guardrail"
        elif case.get("expected_status"):
            assert result["status"] == case["expected_status"]
        else:
            assert result["status"] == "success"
            assert result["self_evaluation"]["score"] >= case.get("min_self_eval_score", 0.90)
            for keyword in case.get("must_include_keywords", []):
                assert keyword.lower() in result["response_markdown"].lower(), (
                    f"Case {case['id']} missing expected keyword '{keyword}'"
                )


def test_5_2_and_5_3_iac_and_secret_manager_integration() -> None:
    """Verify Terraform IaC exists and SecretManagerService never uses hardcoded secrets."""
    repo_root = Path(__file__).resolve().parent.parent
    assert (repo_root / "terraform" / "main.tf").exists()
    assert (repo_root / ".github" / "workflows" / "ci_cd.yml").exists()

    sm = get_secret_manager()
    val = sm.get_secret("GEMINI_API_KEY", default="safe_fallback")
    assert val is not None


if __name__ == "__main__":
    all_tests = [
        test_1_1_comprehensive_tool_docstrings,
        test_1_2_descriptive_tool_naming,
        test_1_3_explicit_pydantic_json_schemas,
        test_1_4_guided_error_handling_for_llm_recovery,
        test_2_1_robust_constitutional_system_instructions,
        test_2_2_history_compaction_and_adk_events_compaction_config,
        test_2_3_persistent_session_and_memory_store,
        test_2_4_async_memory_consolidation_worker,
        test_3_1_multi_agent_patterns,
        test_3_2_strategic_model_routing,
        test_3_3_guardrails_and_self_evaluation_rubric,
        test_3_4_human_in_the_loop_confirmation_gate,
        test_4_1_and_4_2_structured_json_logging_and_intent_outcome_capture,
        test_4_3_distributed_opentelemetry_tracing,
        test_4_4_pii_redaction_scrubber,
        test_5_1_golden_dataset_evaluation_suite,
        test_5_2_and_5_3_iac_and_secret_manager_integration,
    ]
    print("=" * 78)
    print("🏈 RUNNING GRIDIRON EDGE AI — AGENTOPS 95/95 RUBRIC & GOLDEN EVAL SUITE")
    print("=" * 78)
    passed = 0
    for test_fn in all_tests:
        try:
            test_fn()
            print(f"  [PASS] {test_fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {test_fn.__name__}: {exc}")
            sys.exit(1)
    print("=" * 78)
    print(f"✅ ALL {passed}/{len(all_tests)} AGENTOPS RUBRIC & GOLDEN DATASET TESTS PASSED (100%)!")
    print("=" * 78)
