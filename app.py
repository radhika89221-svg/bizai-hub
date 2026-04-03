from dotenv import load_dotenv
from flask import Flask
import os

load_dotenv()

from routes import register_blueprints

app = Flask(__name__)
register_blueprints(app)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 50)
    print("  BizGenius AI is running!")
    print(f"  Open: http://localhost:{port}")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=port)
