# BizGenius AI

BizGenius AI is a Flask-based business toolkit that combines multiple AI-powered tools in one website. It includes content generation, chatbot support, sentiment analysis, image generation, audio utilities, and sales prediction.

## Features

- AI Content Writer
- AI Business Chatbot
- Sentiment Analyzer
- AI Image Generator with provider fallback
- Audio Tools
- Sales Predictor
- User accounts with login/register/logout
- Dashboard with quota tracking
- Local history/persistence for major tools
- Structured request logging
- Stable default text model configuration
- Image caching for repeated generations

## Tech Stack

- Python
- Flask
- Flask-Login
- Flask-SQLAlchemy
- Flask-Limiter
- Requests
- Gunicorn
- Hugging Face Inference
- OpenRouter
- Browser speech APIs

## Project Structure

```text
bizai-hub/
|- app.py
|- ai_services.py
|- auth_utils.py
|- extensions.py
|- history_store.py
|- models.py
|- response_utils.py
|- routes/
|  |- __init__.py
|  |- api.py
|  |- auth.py
|  `- pages.py
|- static/
|  `- generated/
|- templates/
|  |- index.html
|  |- image_generator.html
|  |- content_writer.html
|  |- chatbot.html
|  |- sentiment.html
|  |- sales_predictor.html
|  |- audio_tools.html
|  |- dashboard.html
|  |- login.html
|  |- register.html
|  `- tool_base.html
|- requirements.txt
|- Procfile
`- .gitignore
```

## Environment Variables

Create a `.env` file in the project root.

```env
OPENROUTER_KEY=your_openrouter_key
HF_TOKEN=your_huggingface_token
SECRET_KEY=your_secret_key
DATABASE_URL=optional_database_url
RATELIMIT_STORAGE_URI=optional_rate_limit_storage
OPENROUTER_TEXT_MODEL=optional_openrouter_text_model
OPENROUTER_TEXT_MODELS=optional_comma_separated_model_fallbacks
```

Notes:

- `OPENROUTER_KEY` is used for text generation and as an image fallback.
- `HF_TOKEN` is used for Hugging Face image generation.
- `SECRET_KEY` is used for login sessions and flash messages.
- `DATABASE_URL` is optional. If omitted, the app uses a local SQLite database.
- `RATELIMIT_STORAGE_URI` is optional. Default is in-memory limiter storage for development.
- `OPENROUTER_TEXT_MODEL` is optional. It sets the first default text model used for AI text responses.
- `OPENROUTER_TEXT_MODELS` is optional. It lets you define a comma-separated fallback list, for example `stepfun/step-3.5-flash:free,qwen/qwen3.6-plus:free`.
- `OPENROUTER_CHAT_MODELS` is optional. It overrides the preferred model order for the business advisor chat tool.
- `OPENROUTER_CONTENT_MODELS` is optional. It overrides the preferred model order for the content writer tool.
- Do not commit `.env`.

## Install Locally

From the project folder:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run Locally

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B app.py
```

Open:

```text
http://127.0.0.1:5000/
```

If your machine has broken proxy variables set, clear them in the same terminal before running:

```powershell
$env:HTTP_PROXY=''
$env:HTTPS_PROXY=''
$env:ALL_PROXY=''
```

## Production / Render Deploy

This project is set up for Gunicorn deployment.

- Build command:

```text
pip install -r requirements.txt
```

- Start command:

```text
gunicorn app:app --timeout 120
```

- Required environment variables on Render:
  - `OPENROUTER_KEY`
  - `HF_TOKEN`
  - `SECRET_KEY`

- Recommended on Render:
  - set `DATABASE_URL` to a persistent production database
  - set `RATELIMIT_STORAGE_URI` to a persistent backend such as Redis

## Image Generation Flow

The image generator uses backend provider fallback in this order:

1. Hugging Face
2. OpenRouter
3. Pollinations

Generated images are saved into `static/generated/` and then served back to the browser with a normal static URL.
Repeated image requests with the same prompt and size are reused from cache when available.

## History / Persistence

The app stores lightweight local history in:

```text
bizgenius_history.json
```

History is currently used by:

- Content Writer
- Chatbot
- Sentiment Analyzer
- Image Generator
- Sales Predictor

This file is ignored by git.

When users are logged in, history is stored per-user in the database instead of the local JSON fallback.

## Auth, Quota, and Protection

- Tool pages require login
- JSON APIs return `401` when accessed without authentication
- Daily quota is tracked per user
- Major AI endpoints are rate limited
- Image generation has an extra short-window limiter to reduce burst load
- Dashboard shows current plan, usage, and recent activity
- API requests are logged in a structured format with status, latency, path, and user ID when available

## Main Routes

Pages:

- `/`
- `/login`
- `/register`
- `/dashboard`
- `/content-writer`
- `/chatbot`
- `/sentiment`
- `/image-generator`
- `/audio-tools`
- `/sales-predictor`

APIs:

- `/api/generate-content`
- `/api/chat`
- `/api/analyze-sentiment`
- `/api/generate-image-prompt`
- `/api/generate-real-image`
- `/api/predict-sales`
- `/api/history/<tool>`
- `/api/history/<tool>/clear`

## Notes

- `app_original.py` is treated as a local backup, not the active application entrypoint.
- The live app runs from `app.py`.
- Runtime-generated files such as `static/generated/` and history JSON are ignored by git.
- The default local SQLite database is created outside the repo workspace to avoid OneDrive write issues on this machine.

## Future Improvements

- Add automated tests
- Add plan upgrades and billing
- Move limiter storage to a persistent production backend
- Share more frontend utilities across pages
