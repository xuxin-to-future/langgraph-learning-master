# Session Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete session management (dialogue state + turn typing + retrieve gate + recall) while keeping faq/ticket/chitchat/escalate intents.

**Architecture:** New `session` graph node before `supervisor`; structured LLM updates `session_memory` / `turn_type` / `need_retrieve` / `standalone_query`; FAQ uses those fields; `session_recall` routes to chitchat recall mode.

**Tech Stack:** LangGraph, LangChain ChatOpenAI, FastAPI, existing `customer_service.services.session`

## Global Constraints

- Do not implement slot-filling guided dialogue (B); keep `slots: {}` and ignore `slot_fill`
- Do not break ticket form / escalate / SSE stream
- Prefer one structured LLM call in session node; FAQ must not call a second rewrite LLM
- API keeps `sessionId`; add `turnType`, `needRetrieve` (optional `standaloneQuery` for debug, include in schema)

## File Map

| File | Responsibility |
|------|----------------|
| `customer_service/models/state.py` | TurnType, SessionMemory fields on SupportState |
| `customer_service/services/session_memory.py` | Memory helpers, heuristic fallback, apply updates |
| `customer_service/services/session_analyze.py` | Structured LLM analyze + parse |
| `customer_service/prompts/session.md` | Session analyzer prompt |
| `customer_service/graph/nodes/session.py` | session node |
| `customer_service/graph/builder.py` | Wire START→session→supervisor |
| `customer_service/graph/edges.py` | Route session_recall → chitchat |
| `customer_service/graph/nodes/supervisor.py` | Remove compression (moved to session); pass turn_type hint |
| `customer_service/graph/nodes/faq.py` | need_retrieve / standalone_query; touch last_* |
| `customer_service/graph/nodes/chitchat.py` | Recall mode |
| `customer_service/services/rag.py` | Skip rewrite when standalone_query provided |
| `customer_service/models/schemas.py` + mapping + web | Expose turnType / needRetrieve |
| `tests/customer_service/test_session_*.py` | Unit + graph coverage |

---

### Task 1: State + memory helpers

**Files:**
- Modify: `customer_service/models/state.py`
- Create: `customer_service/services/session_memory.py`
- Test: `tests/customer_service/test_session_memory.py`

**Interfaces:**
- Produces: `TurnType`, `empty_session_memory()`, `normalize_session_memory(raw)`, `heuristic_session_update(user_text, memory, has_history) -> dict`, `touch_last_turns(memory, user, assistant) -> dict`

- [ ] **Step 1: Failing tests for memory normalize + heuristic**

```python
from customer_service.services.session_memory import (
    empty_session_memory,
    heuristic_session_update,
    normalize_session_memory,
    touch_last_turns,
)

def test_normalize_fills_defaults():
    m = normalize_session_memory(None)
    assert m["topic"] == ""
    assert m["slots"] == {}
    assert m["entities"] == []

def test_heuristic_followup_when_history():
    prev = empty_session_memory()
    prev["topic"] = "商机有效期"
    prev["last_user_question"] = "商机周期是什么"
    out = heuristic_session_update("整理成计算公式", prev, has_history=True)
    assert out["turn_type"] == "followup"
    assert out["need_retrieve"] is True
    assert "商机" in out["standalone_query"] or "周期" in out["standalone_query"]

def test_heuristic_recall():
    prev = empty_session_memory()
    prev["last_user_question"] = "退款政策"
    out = heuristic_session_update("我刚才问的是什么", prev, has_history=True)
    assert out["turn_type"] == "session_recall"
    assert out["need_retrieve"] is False

def test_touch_last_turns():
    m = touch_last_turns(empty_session_memory(), "q1", "a1")
    assert m["last_user_question"] == "q1"
    assert m["last_assistant_answer"] == "a1"
```

- [ ] **Step 2: Implement state + session_memory.py to pass**

- [ ] **Step 3: Commit** `feat(session): add dialogue state types and memory helpers`

---

### Task 2: Session analyzer (LLM + prompt)

**Files:**
- Create: `customer_service/prompts/session.md`
- Create: `customer_service/services/session_analyze.py`
- Test: `tests/customer_service/test_session_analyze.py`

**Interfaces:**
- Produces: `analyze_turn(user_text, prompt_block, memory) -> SessionAnalyzeResult` dataclass with turn_type, need_retrieve, standalone_query, memory patch

- [ ] **Step 1: Tests for JSON parse + LLM failure → heuristic**

- [ ] **Step 2: Implement prompt + analyzer**

- [ ] **Step 3: Commit** `feat(session): add structured turn analyzer`

---

### Task 3: session node + graph wiring + routing

**Files:**
- Create: `customer_service/graph/nodes/session.py`
- Modify: `customer_service/graph/builder.py`
- Modify: `customer_service/graph/edges.py`
- Modify: `customer_service/graph/nodes/supervisor.py` (move `prepare_session_update` into session node)
- Test: `tests/customer_service/test_graph.py`, `tests/customer_service/test_session_node.py`

**Interfaces:**
- `session_node(state) -> dict` writes summary/memory/turn_type/need_retrieve/standalone_query
- `route_by_intent` also checks turn_type == session_recall → chitchat

- [ ] **Step 1: Wire graph + tests with monkeypatched analyze**

- [ ] **Step 2: Implement**

- [ ] **Step 3: Commit** `feat(session): add session node before supervisor`

---

### Task 4: FAQ / chitchat consume session fields

**Files:**
- Modify: `customer_service/graph/nodes/faq.py`
- Modify: `customer_service/graph/nodes/chitchat.py`
- Modify: `customer_service/graph/nodes/ticket.py`, `escalate.py` (touch last_*)
- Modify: `customer_service/services/rag.py` (`answer_faq(..., search_query=None, skip_retrieve=False)`)
- Test: `tests/customer_service/test_nodes.py`, `test_query_rewrite.py`

- [ ] **Step 1: FAQ uses standalone_query; skip_retrieve skips retrieve_docs**

- [ ] **Step 2: chitchat recall answers from last_user_question**

- [ ] **Step 3: Commit** `feat(session): wire FAQ retrieve gate and recall answers`

---

### Task 5: API + UI debug fields

**Files:**
- Modify: `customer_service/models/schemas.py`
- Modify: `customer_service/api/mapping.py`
- Modify: `customer_service/web/js/app.js` (show turnType near intent)
- Test: `tests/customer_service/test_api_smoke.py`

- [ ] **Step 1: Add turnType, needRetrieve to ChatResponse**

- [ ] **Step 2: Frontend metadata line**

- [ ] **Step 3: Commit** `feat(session): expose turnType and needRetrieve on chat API`

---

### Task 6: End-to-end regression

- [ ] Run: `python -m pytest tests/customer_service -q`
- [ ] Manual: 商机 → 整理成公式；我刚才问的是什么；/new
- [ ] Commit if fixes needed

---

## Spec coverage check

| Spec item | Task |
|-----------|------|
| session before supervisor | 3 |
| turn_type + memory | 1–2 |
| need_retrieve gate | 4 |
| session_recall no retrieve | 3–4 |
| standalone_query no double rewrite | 4 |
| slots reserved | 1 |
| API fields | 5 |
| fallbacks | 2 |
| tests | 1–6 |
