"""
RAG Chat Threads Repository

Data access layer for the 'rag_chat_threads' table (Postgres) — the ASHA medical
chatbot's conversation history. Previously accessed inline (MongoDB) from app/rag/api.py.
Messages are stored as a JSONB array (timestamps must be ISO strings).
"""

from app.repositories._sql import fetch_all, fetch_one, insert_row, exec_write, utcnow
from app.db import to_jsonb


def list_by_asha(asha_id, limit=50):
    """List an ASHA worker's threads (without the messages payload), newest first."""
    return fetch_all(
        "select id, asha_id, title, created_at, updated_at from rag_chat_threads "
        "where asha_id = :aid order by updated_at desc limit :lim",
        {"aid": str(asha_id), "lim": int(limit)},
    )


def create(asha_id, title="New Chat"):
    """Create a new chat thread. Returns the full thread dict."""
    new_id = insert_row(
        "rag_chat_threads",
        {
            "asha_id": str(asha_id),
            "title": title,
            "messages": [],
            "created_at": utcnow(),
            "updated_at": utcnow(),
        },
        known_cols={"asha_id", "title", "messages", "created_at", "updated_at"},
        jsonb_cols={"messages"},
    )
    return get_by_id(new_id)


def get_by_id(thread_id):
    return fetch_one(
        "select * from rag_chat_threads where id = cast(:id as uuid)", {"id": str(thread_id)}
    )


def append_messages(thread_id, new_messages, title=None):
    """Append messages (JSONB ||) and refresh updated_at / optional title."""
    sets = ["messages = messages || cast(:new as jsonb)", "updated_at = now()"]
    params = {"id": str(thread_id), "new": to_jsonb(list(new_messages))}
    if title is not None:
        sets.append("title = :title")
        params["title"] = title
    return exec_write(
        f"update rag_chat_threads set {', '.join(sets)} where id = cast(:id as uuid)",
        params,
    ) > 0


def delete(thread_id):
    return exec_write(
        "delete from rag_chat_threads where id = cast(:id as uuid)", {"id": str(thread_id)}
    ) > 0
