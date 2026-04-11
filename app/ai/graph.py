"""
LangGraph Workflow Definition

Builds the multi-agent orchestration graph for ArogyaMaa.
"""

import os
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


def should_run_symptom_reasoning(state: ArogyaMaaState) -> str:
    """Conditional edge: Run symptom reasoning if symptoms present"""
    if "symptom_reasoning" in state.get("agents_invoked", []):
        return "symptom_reasoning"
    return "skip_to_trend"


def should_run_trend_analysis(state: ArogyaMaaState) -> str:
    """Conditional edge: Run trend analysis if historical data exists"""
    if "trend_analysis" in state.get("agents_invoked", []):
        return "trend_analysis"
    return "skip_to_document"


def should_run_document_analysis(state: ArogyaMaaState) -> str:
    """Conditional edge: Run document analysis if documents uploaded"""
    if "document_analysis" in state.get("agents_invoked", []):
        return "document_analysis"
    return "nutrition_lifestyle"


def create_ArogyaMaa_graph():
    """
    Create the LangGraph workflow for ArogyaMaa AI orchestration.
    
    Graph Structure:
    
    START → orchestrator → risk_stratification → [conditional]
                                                      ↓
                                            symptom_reasoning? → [conditional]
                                                                      ↓
                                                            trend_analysis? → [conditional]
                                                                                  ↓
                                                                    document_analysis? → nutrition_lifestyle
                                                                                              ↓
                                                                                        communication
                                                                                              ↓
                                                                                          finalize → END
    """
    # Enable LangSmith tracing
    if os.getenv("LANGCHAIN_TRACING_V2") == "true":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "ArogyaMaa")
        print("[LANGGRAPH] LangSmith tracing enabled")
    
    # Create the graph
    workflow = StateGraph(ArogyaMaaState)
    
    # Add all nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("risk_stratification", risk_stratification_node)
    workflow.add_node("symptom_reasoning", symptom_reasoning_node)
    workflow.add_node("trend_analysis", trend_analysis_node)
    workflow.add_node("document_analysis", document_analysis_node)
    workflow.add_node("nutrition_lifestyle", nutrition_lifestyle_node)
    workflow.add_node("communication", communication_node)
    workflow.add_node("finalize", finalize_node)
    
    # Define edges
    workflow.set_entry_point("orchestrator")
    workflow.add_edge("orchestrator", "risk_stratification")
    
    # Conditional routing: risk_stratification → symptom_reasoning OR skip
    workflow.add_conditional_edges(
        "risk_stratification",
        should_run_symptom_reasoning,
        {
            "symptom_reasoning": "symptom_reasoning",
            "skip_to_trend": "trend_analysis"  # Will check if trend should run
        }
    )
    
    # Conditional routing: symptom_reasoning → trend_analysis (check)
    workflow.add_conditional_edges(
        "symptom_reasoning",
        should_run_trend_analysis,
        {
            "trend_analysis": "trend_analysis",
            "skip_to_document": "document_analysis"  # Will check if document should run
        }
    )
    
    # Conditional routing: trend_analysis → document_analysis (check)
    workflow.add_conditional_edges(
        "trend_analysis",
        should_run_document_analysis,
        {
            "document_analysis": "document_analysis",
            "nutrition_lifestyle": "nutrition_lifestyle"
        }
    )
    
    # document_analysis always goes to nutrition
    workflow.add_edge("document_analysis", "nutrition_lifestyle")
    
    # Final sequential steps
    workflow.add_edge("nutrition_lifestyle", "communication")
    workflow.add_edge("communication", "finalize")
    workflow.add_edge("finalize", END)
    
    # Compile the graph
    app = workflow.compile()
    
    return app
