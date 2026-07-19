"""Shared helpers for FastAPI routers."""

import json
import logging

from starlette.responses import Response

logger = logging.getLogger(__name__)


def _json_default(value):
    if hasattr(value, "isoformat"):
        # Routes are expected to isoformat datetimes themselves (Flask parity);
        # warn so any stray raw datetime is caught by the diff harness runs.
        logger.warning("json_response: serialized raw datetime %r", value)
        return value.isoformat()
    raise TypeError("Object of type %s is not JSON serializable" % type(value).__name__)


def json_response(content, status_code=200):
    """jsonify() equivalent."""
    return Response(
        content=json.dumps(content, default=_json_default),
        status_code=status_code,
        media_type="application/json",
    )
