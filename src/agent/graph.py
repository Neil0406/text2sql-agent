from __future__ import annotations
"""
graph.py — Assembles the LangGraph StateGraph for the Text2SQL agent.

Workflow
--------
User Input
  └─► intent_parser
        └─► schema_fetcher
              └─► text2sql ◄──────────────────┐
                    └─► sql_validator          │ retry (up to MAX_RETRIES)
                          ├─► (valid) sql_executor         │
                          │         └─► response_router    │
                          │               ├─► (verbal/table) response_composer
                          │               └─► (chart) chart_generator → response_composer
                          ├─► (retry) ──────────────────────┘
                          ├─► (max retries exceeded) response_composer
                          └─► (unsupported) response_composer
                                  └─► END
"""
import os
from pathlib import Path
from typing import Literal

from langgraph.graph import END, StateGraph

from src.agent.state import AgentState
from src.agent.nodes.intent_parser import intent_parser_node
from src.agent.nodes.text2sql import text2sql_node
from src.agent.nodes.sql_validator import sql_validator_node
from src.agent.nodes.sql_executor import sql_executor_node
from src.agent.nodes.response_router import response_router_node
from src.agent.nodes.response_composer import response_composer_node
from src.visualization.chart_generator import chart_generator_node
from src.db.schema import get_schema_info


# ── Schema Fetcher node (lightweight — no LLM call) ──────────────────────────
def schema_fetcher_node(state: AgentState) -> dict:
    """Read the DB schema and inject it into state for the Text2SQL node."""
    _root = Path(__file__).parent.parent.parent
    db_path = os.getenv("DB_PATH") or str(_root / "data" / "supermarket.db")
    schema = get_schema_info(db_path, include_samples=True, sample_rows=2)
    return {"schema_info": schema}


# ── Conditional edge functions ────────────────────────────────────────────────
def _route_after_validation(
    state: AgentState,
) -> Literal["retry", "execute", "error", "unsupported"]:
    error = state.get("error")
    intent = state.get("intent") or {}

    if error == "unsupported_query" or intent.get("is_prediction"):
        return "unsupported"
    if error == "max_retries_exceeded":
        return "error"
    if error == "validation_failed":
        return "retry"
    return "execute"


def _route_after_router(
    state: AgentState,
) -> Literal["verbal", "table", "chart"]:
    return state.get("response_format", "verbal")  # type: ignore[return-value]


# ── Graph factory ─────────────────────────────────────────────────────────────
def create_agent_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("intent_parser",     intent_parser_node)
    workflow.add_node("schema_fetcher",    schema_fetcher_node)
    workflow.add_node("text2sql",          text2sql_node)
    workflow.add_node("sql_validator",     sql_validator_node)
    workflow.add_node("sql_executor",      sql_executor_node)
    workflow.add_node("response_router",   response_router_node)
    workflow.add_node("chart_generator",   chart_generator_node)
    workflow.add_node("response_composer", response_composer_node)

    # Entry point
    workflow.set_entry_point("intent_parser")

    # Linear edges
    workflow.add_edge("intent_parser",  "schema_fetcher")
    workflow.add_edge("schema_fetcher", "text2sql")
    workflow.add_edge("text2sql",       "sql_validator")

    # Conditional: after validation
    workflow.add_conditional_edges(
        "sql_validator",
        _route_after_validation,
        {
            "retry":       "text2sql",          # regenerate SQL
            "execute":     "sql_executor",       # run the SQL
            "error":       "response_composer",  # max retries exceeded
            "unsupported": "response_composer",  # unsupported query
        },
    )

    workflow.add_edge("sql_executor", "response_router")

    # Conditional: after routing
    workflow.add_conditional_edges(
        "response_router",
        _route_after_router,
        {
            "verbal": "response_composer",
            "table":  "response_composer",
            "chart":  "chart_generator",       # generate chart first
        },
    )

    workflow.add_edge("chart_generator",   "response_composer")
    workflow.add_edge("response_composer", END)

    return workflow.compile()


# ── Singleton ─────────────────────────────────────────────────────────────────
_agent: StateGraph | None = None


def get_agent() -> StateGraph:
    global _agent
    if _agent is None:
        _agent = create_agent_graph()
    return _agent


def run_agent(user_input: str, conversation_history: list | None = None) -> dict:
    """
    Public entry-point.  Accepts user text and returns the final AgentState.
    Pass `conversation_history` from the previous call for multi-turn support.
    """
    agent = get_agent()

    initial: AgentState = {
        "user_input":           user_input,
        "conversation_history": conversation_history or [],
        "intent":               None,
        "schema_info":          None,
        "sql_query":            None,
        "retry_count":          0,
        "sql_error":            None,
        "query_results":        None,
        "response_format":      None,
        "chart_type":           None,
        "verbal_response":      None,
        "chart_path":           None,
        "final_response":       None,
        "error":                None,
    }

    return agent.invoke(initial)
