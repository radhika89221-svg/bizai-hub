from flask import jsonify, request


def json_success(**payload):
    """Return a normalized success response."""
    return jsonify({'success': True, **payload})


def json_error(message, status_code=400, **payload):
    """Return a normalized error response."""
    return jsonify({'success': False, 'error': message, **payload}), status_code


def parse_json_request():
    """Safely read a JSON request body."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, json_error('Invalid JSON body.', 400)
    return data, None
