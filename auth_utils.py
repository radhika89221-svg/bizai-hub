from functools import wraps

from flask_login import current_user

from extensions import db
from response_utils import json_error


def api_login_required(view):
    """Require an authenticated user for JSON APIs."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return json_error('Authentication required.', 401)
        return view(*args, **kwargs)
    return wrapped


def require_quota():
    """Ensure the authenticated user still has quota remaining."""
    if not current_user.is_authenticated:
        return json_error('Authentication required.', 401)

    current_user.refresh_daily_quota()
    db.session.commit()

    if current_user.quota_remaining() <= 0:
        return json_error('Daily quota reached for your account.', 429)

    return None


def consume_quota():
    """Consume one quota unit for the current user."""
    if not current_user.is_authenticated:
        return

    current_user.refresh_daily_quota()
    current_user.daily_used += 1
    db.session.commit()
