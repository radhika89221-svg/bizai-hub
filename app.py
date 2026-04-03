from dotenv import load_dotenv
from flask import Flask
import os
import tempfile

load_dotenv()

from extensions import db, limiter, login_manager
from logging_utils import configure_logging
from models import User
from routes import register_blueprints

app = Flask(__name__)
os.makedirs(app.instance_path, exist_ok=True)
local_data_dir = os.path.join(tempfile.gettempdir(), 'BizGeniusAI')
os.makedirs(local_data_dir, exist_ok=True)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    f"sqlite:///{os.path.join(local_data_dir, 'bizgenius.db')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['RATELIMIT_STORAGE_URI'] = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
app.config['OPENROUTER_TEXT_MODEL'] = os.environ.get(
    'OPENROUTER_TEXT_MODEL',
    'qwen/qwen3-8b:free'
)

db.init_app(app)
login_manager.init_app(app)
limiter.init_app(app)
configure_logging(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()

register_blueprints(app)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 50)
    print("  BizGenius AI is running!")
    print(f"  Open: http://localhost:{port}")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=port)
