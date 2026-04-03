import json
import os
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_STORE_PATH = os.path.join(BASE_DIR, 'bizgenius_history.json')


def init_history_store():
    """Ensure the local history JSON store exists."""
    if not os.path.exists(HISTORY_STORE_PATH):
        with open(HISTORY_STORE_PATH, 'w', encoding='utf-8') as history_file:
            json.dump({'last_id': 0, 'items': []}, history_file)


def read_history_store():
    """Read the persisted history payload from disk."""
    init_history_store()
    with open(HISTORY_STORE_PATH, 'r', encoding='utf-8') as history_file:
        return json.load(history_file)


def write_history_store(payload):
    """Write the full history payload back to disk."""
    with open(HISTORY_STORE_PATH, 'w', encoding='utf-8') as history_file:
        json.dump(payload, history_file, ensure_ascii=True, indent=2)


def save_history_entry(tool, input_text, output_text='', meta=None):
    """Persist a generated result for later viewing in the UI."""
    payload = read_history_store()
    payload['last_id'] += 1
    payload['items'].append({
        'id': payload['last_id'],
        'tool': tool,
        'input_text': input_text,
        'output_text': output_text,
        'meta': meta or {},
        'created_at': datetime.utcnow().isoformat(timespec='seconds')
    })
    payload['items'] = payload['items'][-200:]
    write_history_store(payload)


def fetch_history_entries(tool, limit=10):
    """Read recent history items for a tool."""
    safe_limit = max(1, min(int(limit), 30))
    payload = read_history_store()
    items = [item for item in payload.get('items', []) if item.get('tool') == tool]
    return list(reversed(items[-safe_limit:]))


def clear_history_entries(tool):
    """Delete saved history for a specific tool."""
    payload = read_history_store()
    payload['items'] = [item for item in payload.get('items', []) if item.get('tool') != tool]
    write_history_store(payload)


init_history_store()
