"""
LangGraph Workflow Definition

Builds the multi-agent orchestration graph for ArogyaMaa.
"""

import os
import logging
import time
from langgraph.graph import StateGraph, END
from langsmith import Client

from .state import ArogyaMaaState
from .agents import (
    orchestrator_node,
    risk_stratification_node,
    symptom_reasoning_node,
    trend_analysis_node,
    document_analysis_node,
    nutrition_lifestyle_node,
    communication_node,
    finalize_node
)


logger = logging.getLogger(__name__)


# The state keys each node is allowed to publish. Nodes historically mutate the
# state dict in place and return it whole; the wrapper below narrows that to a
# per-node delta so nodes can later run in the same super-step without
# LangGraph raising InvalidUpdateError on multiply-written channels.
_NODE_OUTPUT_KEYS = {
    "orchestrator":        ["agents_invoked", "timestamp"],
    "risk_stratification": ["risk_stratification_result"],
    "symptom_reasoning":   ["symptom_reasoning_result"],
    "trend_analysis":      ["trend_analysis_result"],
    "document_analysis":   ["document_analysis_result"],
    "nutrition_lifestyle": ["nutrition_lifestyle_result"],
    "communication":       ["communication_result"],
    "finalize":            ["final_results", "workflow_complete", "completed_at",
                            "final_risk_level", "final_risk_score", "final_confidence"],
}


def _wrap_node(name, fn):
    """Adapt an in-place-mutating agent node to timed, delta-returning form.

    The node gets a shallow copy of the state (parallel siblings must never
    mutate the same dict), and only its declared output keys are published.
    """
    output_keys = _NODE_OUTPUT_KEYS[name]

    def wrapped(state: ArogyaMaaState):
        # Parity gate: the old conditional router only ran document analysis
        # when documents were uploaded. The node itself doesn't check, and
        # build_ai_evaluation keys off the PRESENCE of document_analysis_result,
        # so skipping must leave the key unset (not empty).
        if name == "document_analysis" and not state.get("has_uploaded_documents"):
            return {"perf_timings": [{"stage": "node:" + name, "ms": 0.0}]}

        t0 = time.perf_counter()
        result = fn(dict(state))
        ms = (time.perf_counter() - t0) * 1000
        update = {k: result[k] for k in output_keys if k in result}
        update["perf_timings"] = [{"stage": "node:" + name, "ms": round(ms, 1)}]
        logger.info("[PERF] node=%s ms=%.1f", name, ms)
        return update

    return wrapped


def create_ArogyaMaa_graph():
    """
    Create the LangGraph workflow for ArogyaMaa AI orchestration.

    Graph Structure (independent agents run concurrently; verified against
    each node's actual state reads — only nutrition/communication depend on
    another agent's output, and only on risk_stratification's):

    START → orchestrator ─┬─ risk_stratification ──┐
                          ├─ symptom_reasoning ────┤   (phase A, parallel)
                          ├─ trend_analysis ───────┤
                          └─ document_analysis ────┤
                                                   ├─┬─ nutrition_lifestyle ─┐  (phase B,
                                                   │ └─ communication ───────┤   parallel)
                                                   │                         │
                                                   └────────── finalize ← ───┘
                                                                   ↓
                                                                  END
    """
    # Enable LangSmith tracing
    if os.getenv("LANGCHAIN_TRACING_V2") == "true":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "ArogyaMaa")
        logger.info("[LANGGRAPH] LangSmith tracing enabled")
    
    # Create the graph
    workflow = StateGraph(ArogyaMaaState)
    
    # Add all nodes (wrapped: per-node timing + delta-only state updates)
    workflow.add_node("orchestrator", _wrap_node("orchestrator", orchestrator_node))
    workflow.add_node("risk_stratification", _wrap_node("risk_stratification", risk_stratification_node))
    workflow.add_node("symptom_reasoning", _wrap_node("symptom_reasoning", symptom_reasoning_node))
    workflow.add_node("trend_analysis", _wrap_node("trend_analysis", trend_analysis_node))
    workflow.add_node("document_analysis", _wrap_node("document_analysis", document_analysis_node))
    workflow.add_node("nutrition_lifestyle", _wrap_node("nutrition_lifestyle", nutrition_lifestyle_node))
    workflow.add_node("communication", _wrap_node("communication", communication_node))
    workflow.add_node("finalize", _wrap_node("finalize", finalize_node))
    
    # Define edges. Phase A nodes read only input fields (mutually
    # independent); nutrition and communication read only
    # risk_stratification_result; finalize aggregates everything. The
    # skipped-node conditions the old routers checked are enforced inside
    # the nodes themselves (deterministic short-circuits) and, for
    # document_analysis, by the parity gate in _wrap_node.
    phase_a = ["risk_stratification", "symptom_reasoning", "trend_analysis", "document_analysis"]

    workflow.set_entry_point("orchestrator")
    for node in phase_a:
        workflow.add_edge("orchestrator", node)          # fan-out: one super-step

    workflow.add_edge(phase_a, "nutrition_lifestyle")    # barrier join
    workflow.add_edge(phase_a, "communication")          # barrier join
    workflow.add_edge(["nutrition_lifestyle", "communication"], "finalize")
    workflow.add_edge("finalize", END)
    
    # Compile the graph
    app = workflow.compile()
    
    return app
