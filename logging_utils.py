import json
import logging
import time
from uuid import uuid4

from flask import g, request
from flask_login import current_user


def configure_logging(app):
    """Set up a simple structured logger for local and production use."""
    logger = logging.getLogger('bizgenius')
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    app.logger.handlers = logger.handlers
    app.logger.setLevel(logger.level)

    @app.before_request
    def start_request_logging():
        g.request_started_at = time.perf_counter()
        g.request_id = uuid4().hex[:12]

    @app.after_request
    def finish_request_logging(response):
        if request.path.startswith('/static/'):
            return response

        duration_ms = None
        if hasattr(g, 'request_started_at'):
            duration_ms = round((time.perf_counter() - g.request_started_at) * 1000, 2)

        payload = {
            'event': 'request',
            'request_id': getattr(g, 'request_id', None),
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration_ms': duration_ms,
            'remote_addr': request.headers.get('X-Forwarded-For', request.remote_addr),
            'user_id': current_user.get_id() if current_user.is_authenticated else None,
        }
        logger.info(json.dumps(payload, ensure_ascii=True))
        return response

    return logger


def log_event(event, **fields):
    """Emit a structured application log event."""
    logger = logging.getLogger('bizgenius')
    payload = {'event': event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=True))
