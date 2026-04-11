"""
AI Orchestration Module

LangGraph-based multi-agent system for maternal health risk assessment.

Usage:
    from app.ai import create_ArogyaMaa_graph, build_ai_evaluation
    
    graph = create_ArogyaMaa_graph()
    result = graph.invoke(assessment_data)
    ai_evaluation = build_ai_evaluation(result)
"""

# Try to import LangGraph components, gracefully handle if not available
try:
    from .graph import create_ArogyaMaa_graph
    from .state import ArogyaMaaState
    from .helpers import build_ai_evaluation, prepare_assessment_for_ai
    from .alerts import send_ai_alerts
    
    __all__ = [
        'create_ArogyaMaa_graph', 
        'ArogyaMaaState',
        'build_ai_evaluation',
        'prepare_assessment_for_ai',
        'send_ai_alerts'
    ]
except ImportError as e:
    # LangGraph not available - functions will not be exported
    __all__ = []
    import logging
    logging.warning(f"[AI] LangGraph not available: {e}. AI features will use fallback.")


