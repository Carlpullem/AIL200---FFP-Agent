# 🎥 Video Submission Walkthrough Script (3.5 – 4.5 Minutes)

**Course**: Gemini Enterprise Agent Platform (GEAP) — AI Coding (`AIL200---FFP-Agent`)  
**Project**: **Gridiron Edge AI** — Predictive Sabermetric NFL Fantasy Football Multi-Agent Platform  

---

## ⏱️ 0:00 – 0:45 | 1. Problem Statement & Why We Built It
*(On Screen: Show the live **Gridiron Edge AI War Room** UI at `http://cpcloud.c.googlers.com:8080` alongside the `README.md` architecture diagram)*

> **"Hi everyone! For my GEAP capstone, I built Gridiron Edge AI (`AIL200---FFP-Agent`), a multi-agent NFL Fantasy Football intelligence platform built on Google ADK, the open-source `nflverse` (`nflreadpy` / `nflfastR`) data engine, and the live Sleeper API.**
>
> **The real-world problem my friends and I face every week in our Sleeper leagues is information overload and box-score lag. By the time a player scores 20 fantasy points on Sunday, everyone bids 50% of their FAAB waiver budget. To beat your league, you need predictive leading indicators—Route Participation %, Yards Per Route Run (`YPRR`), Weighted Opportunity Rating (`WOPR`), and Expected Fantasy Points (`xFP`) differential—to identify <35% rostered breakouts and buy-low trade targets *before* the points happen."**

---

## ⏱️ 0:45 – 1:45 | 2. Live Interactive Demo ("War Room" + HITL Gate)
*(On Screen: Click through the interactive War Room UI buttons)*

1. **Sync Sleeper & Breakouts**:
   - Click **"⚡ Sync League"** and **"💎 Waiver Breakouts (<35% Owned)"** in the left sidebar.
   - Point out how the agent surfaces **Bucky Irving (28.4% rostered, +14.8% WoW snap surge, +3.7 PPR xFP under-performance)** and **Jalen McMillan (16.5% rostered, 84.2% route participation, 0.56 WOPR, +5.1 PPR xFP differential)**.
2. **Game-Theory FAAB Calculator & Buy-Low Trade Analyzer**:
   - Click **"💰 Calculate FAAB Bid (Bucky Irving)"** in the chat header. Show the 3-tier FAAB bid ladder (**Conservative 11% / Optimal 22% / Aggressive 33%**) and the **AgentOps Telemetry Badges** (`Model Route: gemini-2.5-pro`, `Self-Eval Rubric: 1.0 (5 metrics cited)`).
3. **Human-in-the-Loop (HITL) Confirmation Gate**:
   - Click **"✋ Test HITL High-Stakes Gate (45% FAAB)"**.
   - Highlight the amber **Human-in-the-Loop Confirmation Required** banner (`status="CONFIRMATION_REQUIRED"`) triggered because the 45% FAAB bid exceeds our 30% constitutional threshold, pausing execution until the user clicks **"✅ Approve & Execute (HITL)"**.

---

## ⏱️ 1:45 – 3:00 | 3. Code & AgentOps Architecture Walkthrough (95/95 Rubric)
*(On Screen: Open the code files referenced in the `README.md` Traceability Matrix)*

1. **Tool & Interface Design (`ffp_agent/schemas.py` & `ffp_agent/tools.py`)**:
   - Show strict `pydantic.BaseModel` (`extra="forbid"`) schemas and the 7 descriptively named tools (`fetch_nflverse_player_sabermetric_telemetry`, `discover_undervalued_waiver_wire_breakouts`, etc.).
   - Highlight **Guided Error Handling**: when an unknown player name is queried, the tool returns `status="recoverable_error"` with `recovery_instructions` and fuzzy match suggestions rather than raising a traceback.
2. **Context & Memory (`ffp_agent/memory_and_compaction.py` & `ffp_agent/prompts.py`)**:
   - Show the XML `<CONSTITUTION>` system instructions in `prompts.py`.
   - Show `EventsCompactionConfig(token_threshold=4000, event_retention_size=5)` in `memory_and_compaction.py`, `PersistentFantasyStateStore` (SQLite session + long-term memory store), and `schedule_async_memory_consolidation()` using `asyncio.create_task()` so memory indexing never blocks user chat latency.
3. **Orchestration & Logic (`ffp_agent/agent.py` & `ffp_agent/guardrails_and_routing.py`)**:
   - Show the multi-agent hierarchy in `agent.py`: `ParallelIntelGatheringPipeline` (`ParallelAgent` running `SleeperMarketScoutAgent` + `AdvancedMetricsSabermetricAgent` on `gemini-2.5-flash`), feeding `SequentialStrategyPipeline` (`SequentialAgent` running `FaabAndTradeArchitectAgent` + `LineupStartSitAdvisorAgent` on `gemini-2.5-pro`), wrapped inside `StrategyQualityLoopAgent` (`LoopAgent`) and `FantasyAgentOpsGuardrailPlugin` (`BasePlugin`).

---

## ⏱️ 3:00 – 4:00 | 4. Observability, Security, Evaluation & CI/CD
*(On Screen: Show `ffp_agent/observability.py`, `terraform/main.tf`, and terminal running `pytest -v`)*

1. **Observability & PII Scrubbing (`ffp_agent/observability.py`)**:
   - Show `PIIRedactionScrubber` (Cloud DLP API + deterministic regex scrubbing for emails, phones, SSNs, credit cards, API keys), OpenTelemetry `TracerProvider` spans (`traced_span`), and `before_tool_intent_callback` (`TOOL_INTENT`) / `after_tool_outcome_callback` (`TOOL_OUTCOME`).
2. **Infrastructure as Code, Secret Manager & Golden Evaluation Suite**:
   - Show `ffp_agent/secrets.py` (`google-cloud-secret-manager` with zero hardcoded keys), `terraform/main.tf` (Cloud Run + Cloud SQL + Vertex AI), and `.github/workflows/ci_cd.yml`.
   - Conclude by showing the `pytest -v` run passing all 15 rubric & golden dataset evaluation tests with a 100% pass rate.
