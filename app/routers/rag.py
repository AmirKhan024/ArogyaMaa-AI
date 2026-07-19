"""
ASHA RAG Router — FastAPI port of app/rag/api.py.

Reuses the original module's engine/safety singletons and confidence logic
(imported, not duplicated) so behavior cannot drift between the two apps.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body

from app.repositories import rag_threads_repo
from app.rag.api import calculate_confidence, get_rag_engine, get_safety_filter
from app.rag.safety import ResponseValidator, QuerySafetyLevel
from app.routers._utils import json_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/asha/rag")


@router.post("/query", name="asha_rag.asha_query")
def asha_query(data: dict = Body(None)):
    """Main ASHA RAG query endpoint."""
    try:
        if not data or 'query' not in data:
            return json_response({
                "status": "error",
                "message": "Missing 'query' field in request body"
            }, 400)

        user_query = data['query'].strip()
        asha_id = data.get('asha_id')
        mother_id = data.get('mother_id')

        logger.info(f"\n{'='*70}")
        logger.info(f"ASHA RAG Query Received")
        logger.info(f"Query: {user_query}")
        logger.info(f"ASHA ID: {asha_id}")
        logger.info(f"Mother ID: {mother_id}")
        logger.info(f"{'='*70}")

        # Step 1: Safety validation
        safety_filter = get_safety_filter()
        safety_level, block_reason = safety_filter.validate_query(user_query)

        if safety_level == QuerySafetyLevel.BLOCKED:
            logger.warning(f"Query blocked: {block_reason}")

            blocked_response = safety_filter.get_blocked_response(user_query, block_reason)

            return json_response({
                "status": "blocked",
                "response": blocked_response,
                "confidence": 0.0,
                "flag_for_review": True,
                "blocked": True,
                "block_reason": block_reason
            }, 200)

        # Step 2: Query RAG engine and get confidence data
        rag_engine = get_rag_engine()

        documents = rag_engine.retriever.retrieve_documents(
            query=user_query,
            metadata_filter={"audience": "asha"}
        )

        response = rag_engine.query(user_query)

        # Step 3: Validate response
        validator = ResponseValidator()
        is_valid, validation_error = validator.validate_response(response)

        if not is_valid:
            logger.error(f"Response validation failed: {validation_error}")
            return json_response({
                "status": "error",
                "message": f"Response validation failed: {validation_error}"
            }, 500)

        # Step 4: Sanitize response
        response = validator.sanitize_response(response)

        # Step 5: Calculate REAL confidence based on retrieved documents
        confidence = calculate_confidence(documents, response, user_query)

        flag_for_review = confidence < 0.7

        logger.info(f"Response generated (confidence: {confidence:.2f})")

        return json_response({
            "status": "success",
            "response": response,
            "confidence": confidence,
            "flag_for_review": flag_for_review,
            "blocked": False
        }, 200)

    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        return json_response({
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }, 500)


@router.get("/health", name="asha_rag.health_check")
def health_check():
    """Health check endpoint."""
    try:
        engine = get_rag_engine()

        return json_response({
            "status": "healthy",
            "service": "ASHA RAG Chatbot",
            "rag_engine": "initialized",
            "safety_filter": "active"
        }, 200)

    except Exception as e:
        return json_response({
            "status": "unhealthy",
            "error": str(e)
        }, 503)


@router.get("/stats", name="asha_rag.get_stats")
def get_stats():
    """Get RAG system statistics."""
    try:
        from app.rag.knowledge_ingestion import ASHAKnowledgeIngestion

        ingestion = ASHAKnowledgeIngestion()
        ingestion.load_existing_db()
        stats = ingestion.get_stats()

        return json_response({
            "status": "success",
            "stats": stats
        }, 200)

    except Exception as e:
        return json_response({
            "status": "error",
            "message": str(e)
        }, 500)


@router.get("/threads", name="asha_rag.list_threads")
def list_threads(asha_id: str = None):
    """List all chat threads for an ASHA worker."""
    try:
        if not asha_id:
            return json_response({"status": "error", "message": "asha_id required"}, 400)

        threads = rag_threads_repo.list_by_asha(asha_id, limit=50)

        return json_response({
            "status": "success",
            "threads": threads
        }, 200)

    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        return json_response({"status": "error", "message": str(e)}, 500)


@router.post("/threads", name="asha_rag.create_thread")
def create_thread(data: dict = Body(None)):
    """Create a new chat thread."""
    try:
        data = data or {}
        asha_id = data.get('asha_id')
        title = data.get('title', 'New Chat')

        if not asha_id:
            return json_response({"status": "error", "message": "asha_id required"}, 400)

        thread = rag_threads_repo.create(asha_id, title)

        return json_response({
            "status": "success",
            "thread": thread
        }, 201)

    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        return json_response({"status": "error", "message": str(e)}, 500)


@router.get("/threads/{thread_id}", name="asha_rag.get_thread")
def get_thread(thread_id: str):
    """Get a specific chat thread with all messages."""
    try:
        thread = rag_threads_repo.get_by_id(thread_id)

        if not thread:
            return json_response({"status": "error", "message": "Thread not found"}, 404)

        return json_response({
            "status": "success",
            "thread": thread
        }, 200)

    except Exception as e:
        logger.error(f"Error getting thread: {e}")
        return json_response({"status": "error", "message": str(e)}, 500)


@router.post("/threads/{thread_id}/messages", name="asha_rag.add_message")
def add_message(thread_id: str, data: dict = Body(None)):
    """Add a message to a thread and get RAG response."""
    try:
        data = data or {}
        user_query = data.get('query', '').strip()
        asha_id = data.get('asha_id')

        if not user_query:
            return json_response({"status": "error", "message": "Query required"}, 400)

        user_message = {
            "role": "user",
            "content": user_query,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Get RAG response (reuse query logic)
        safety_filter = get_safety_filter()
        safety_level, block_reason = safety_filter.validate_query(user_query)

        if safety_level == QuerySafetyLevel.BLOCKED:
            assistant_message = {
                "role": "assistant",
                "content": safety_filter.get_blocked_response(user_query, block_reason),
                "confidence": 0.0,
                "blocked": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            rag_engine = get_rag_engine()
            documents = rag_engine.retriever.retrieve_documents(
                query=user_query,
                metadata_filter={"audience": "asha"}
            )
            response = rag_engine.query(user_query)
            confidence = calculate_confidence(documents, response, user_query)

            assistant_message = {
                "role": "assistant",
                "content": response,
                "confidence": confidence,
                "blocked": False,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        # Update thread with new messages
        new_title = user_query[:50] + "..." if len(user_query) > 50 else user_query
        rag_threads_repo.append_messages(
            thread_id, [user_message, assistant_message], title=new_title
        )

        return json_response({
            "status": "success",
            "response": assistant_message["content"],
            "confidence": assistant_message.get("confidence", 0.8),
            "blocked": assistant_message.get("blocked", False)
        }, 200)

    except Exception as e:
        logger.error(f"Error adding message: {e}")
        return json_response({"status": "error", "message": str(e)}, 500)


@router.delete("/threads/{thread_id}", name="asha_rag.delete_thread")
def delete_thread(thread_id: str):
    """Delete a chat thread."""
    try:
        if not rag_threads_repo.delete(thread_id):
            return json_response({"status": "error", "message": "Thread not found"}, 404)

        return json_response({"status": "success", "message": "Thread deleted"}, 200)

    except Exception as e:
        logger.error(f"Error deleting thread: {e}")
        return json_response({"status": "error", "message": str(e)}, 500)
