"""
Flask API Integration for ASHA RAG Chatbot

Provides REST API endpoints for ASHA portal integration.
"""

from flask import Blueprint, request, jsonify, current_app
from functools import wraps
import logging
from datetime import datetime
from bson import ObjectId

from app.rag.retriever import ASHARAGEngine
from app.rag.safety import ASHASafetyFilter, ResponseValidator, ConfidenceScorer, QuerySafetyLevel

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
asha_rag_bp = Blueprint('asha_rag', __name__, url_prefix='/asha/rag')

# Initialize RAG engine (lazy loading)
_rag_engine = None
_safety_filter = None


def calculate_confidence(documents, response, query):
    """
    Calculate real confidence score based on:
    - Number of retrieved documents
    - Document relevance (based on content overlap)
    - Response completeness
    """
    score = 0.0
    
    # Factor 1: Number of documents retrieved (max 0.3)
    doc_count = len(documents) if documents else 0
    if doc_count >= 4:
        score += 0.3
    elif doc_count >= 2:
        score += 0.2
    elif doc_count >= 1:
        score += 0.1
    
    # Factor 2: Query terms found in documents (max 0.3)
    query_terms = set(query.lower().split())
    stop_words = {'what', 'is', 'the', 'a', 'an', 'to', 'do', 'if', 'when', 'how', 'for', 'in', 'on', 'at', 'are', 'of'}
    query_terms = query_terms - stop_words
    
    if documents and query_terms:
        doc_text = ' '.join([doc.page_content.lower() for doc in documents])
        matches = sum(1 for term in query_terms if term in doc_text)
        term_coverage = matches / len(query_terms) if query_terms else 0
        score += min(0.3, term_coverage * 0.3)
    
    # Factor 3: Response completeness (max 0.25)
    if response:
        has_guidance = bool(response.get('guidance'))
        has_checklist = bool(response.get('checklist')) and len(response.get('checklist', [])) >= 2
        has_escalation = bool(response.get('escalation_rule'))
        
        completeness = (has_guidance * 0.1) + (has_checklist * 0.1) + (has_escalation * 0.05)
        score += completeness
    
    # Factor 4: Source documents cited (max 0.15)
    sources = response.get('source_documents', []) if response else []
    if len(sources) >= 2:
        score += 0.15
    elif len(sources) >= 1:
        score += 0.1
    
    # Ensure score is between 0 and 1
    return min(1.0, max(0.0, score))


def get_rag_engine():
    """Get or initialize RAG engine."""
    global _rag_engine
    if _rag_engine is None:
        try:
            _rag_engine = ASHARAGEngine()
            logger.info("✓ ASHA RAG engine initialized")
        except Exception as e:
            logger.error(f"✗ Failed to initialize RAG engine: {e}")
            raise
    return _rag_engine


def get_safety_filter():
    """Get or initialize safety filter."""
    global _safety_filter
    if _safety_filter is None:
        _safety_filter = ASHASafetyFilter()
        logger.info("✓ Safety filter initialized")
    return _safety_filter


def require_asha_role(f):
    """Decorator to ensure only ASHA workers can access endpoint."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # In production, verify user role from session/JWT
        # For now, we'll skip authentication
        return f(*args, **kwargs)
    return decorated_function


@asha_rag_bp.route('/query', methods=['POST'])
@require_asha_role
def asha_query():
    """
    Main ASHA RAG query endpoint.
    
    Request Body:
    {
        "query": "BP is 150/95 at 28 weeks, what to do?",
        "asha_id": "optional_asha_worker_id",
        "mother_id": "optional_mother_id"
    }
    
    Response:
    {
        "status": "success",
        "response": {
            "guidance": "...",
            "checklist": [...],
            "escalation_rule": "...",
            "source_documents": [...],
            "disclaimer": "..."
        },
        "confidence": 0.85,
        "flag_for_review": false,
        "blocked": false
    }
    """
    try:
        # Parse request
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                "status": "error",
                "message": "Missing 'query' field in request body"
            }), 400
        
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
            
            return jsonify({
                "status": "blocked",
                "response": blocked_response,
                "confidence": 0.0,
                "flag_for_review": True,
                "blocked": True,
                "block_reason": block_reason
            }), 200
        
        # Step 2: Query RAG engine and get confidence data
        rag_engine = get_rag_engine()
        
        # Get documents for confidence calculation
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
            return jsonify({
                "status": "error",
                "message": f"Response validation failed: {validation_error}"
            }), 500
        
        # Step 4: Sanitize response
        response = validator.sanitize_response(response)
        
        # Step 5: Calculate REAL confidence based on retrieved documents
        confidence = calculate_confidence(documents, response, user_query)
        
        flag_for_review = confidence < 0.7
        
        logger.info(f"Response generated (confidence: {confidence:.2f})")
        
        return jsonify({
            "status": "success",
            "response": response,
            "confidence": confidence,
            "flag_for_review": flag_for_review,
            "blocked": False
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Internal server error: {str(e)}"
        }), 500


@asha_rag_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        # Check if RAG engine can be initialized
        engine = get_rag_engine()
        
        return jsonify({
            "status": "healthy",
            "service": "ASHA RAG Chatbot",
            "rag_engine": "initialized",
            "safety_filter": "active"
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503


@asha_rag_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get RAG system statistics."""
    try:
        from app.rag.knowledge_ingestion import ASHAKnowledgeIngestion
        
        ingestion = ASHAKnowledgeIngestion()
        ingestion.load_existing_db()
        stats = ingestion.get_stats()
        
        return jsonify({
            "status": "success",
            "stats": stats
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================================
# CHAT HISTORY PERSISTENCE (LangGraph-style threading)
# ============================================================================

def get_db():
    """Get MongoDB database connection."""
    from app.db import get_db as get_mongo_db
    return get_mongo_db()


@asha_rag_bp.route('/threads', methods=['GET'])
def list_threads():
    """List all chat threads for an ASHA worker."""
    try:
        asha_id = request.args.get('asha_id')
        if not asha_id:
            return jsonify({"status": "error", "message": "asha_id required"}), 400
        
        db = get_db()
        threads = list(db.rag_chat_threads.find(
            {"asha_id": asha_id},
            {"messages": 0}  # Exclude messages for list view
        ).sort("updated_at", -1).limit(50))
        
        # Convert ObjectId to string
        for thread in threads:
            thread['_id'] = str(thread['_id'])
        
        return jsonify({
            "status": "success",
            "threads": threads
        }), 200
        
    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@asha_rag_bp.route('/threads', methods=['POST'])
def create_thread():
    """Create a new chat thread."""
    try:
        data = request.get_json()
        asha_id = data.get('asha_id')
        title = data.get('title', 'New Chat')
        
        if not asha_id:
            return jsonify({"status": "error", "message": "asha_id required"}), 400
        
        db = get_db()
        thread = {
            "asha_id": asha_id,
            "title": title,
            "messages": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = db.rag_chat_threads.insert_one(thread)
        thread['_id'] = str(result.inserted_id)
        
        return jsonify({
            "status": "success",
            "thread": thread
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@asha_rag_bp.route('/threads/<thread_id>', methods=['GET'])
def get_thread(thread_id):
    """Get a specific chat thread with all messages."""
    try:
        db = get_db()
        thread = db.rag_chat_threads.find_one({"_id": ObjectId(thread_id)})
        
        if not thread:
            return jsonify({"status": "error", "message": "Thread not found"}), 404
        
        thread['_id'] = str(thread['_id'])
        
        return jsonify({
            "status": "success",
            "thread": thread
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting thread: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@asha_rag_bp.route('/threads/<thread_id>/messages', methods=['POST'])
def add_message(thread_id):
    """Add a message to a thread and get RAG response."""
    try:
        data = request.get_json()
        user_query = data.get('query', '').strip()
        asha_id = data.get('asha_id')
        
        if not user_query:
            return jsonify({"status": "error", "message": "Query required"}), 400
        
        db = get_db()
        
        # Create user message
        user_message = {
            "role": "user",
            "content": user_query,
            "timestamp": datetime.utcnow()
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
                "timestamp": datetime.utcnow()
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
                "timestamp": datetime.utcnow()
            }
        
        # Update thread with new messages
        db.rag_chat_threads.update_one(
            {"_id": ObjectId(thread_id)},
            {
                "$push": {"messages": {"$each": [user_message, assistant_message]}},
                "$set": {
                    "updated_at": datetime.utcnow(),
                    "title": user_query[:50] + "..." if len(user_query) > 50 else user_query
                }
            }
        )
        
        return jsonify({
            "status": "success",
            "response": assistant_message["content"],
            "confidence": assistant_message.get("confidence", 0.8),
            "blocked": assistant_message.get("blocked", False)
        }), 200
        
    except Exception as e:
        logger.error(f"Error adding message: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@asha_rag_bp.route('/threads/<thread_id>', methods=['DELETE'])
def delete_thread(thread_id):
    """Delete a chat thread."""
    try:
        db = get_db()
        result = db.rag_chat_threads.delete_one({"_id": ObjectId(thread_id)})
        
        if result.deleted_count == 0:
            return jsonify({"status": "error", "message": "Thread not found"}), 404
        
        return jsonify({"status": "success", "message": "Thread deleted"}), 200
        
    except Exception as e:
        logger.error(f"Error deleting thread: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
