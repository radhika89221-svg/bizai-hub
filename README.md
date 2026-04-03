# BizGenius AI

BizGenius AI is a Flask-based business toolkit that combines multiple AI-powered tools in one website. It includes content generation, chatbot support, sentiment analysis, image generation, audio utilities, and sales prediction.

## Features

- AI Content Writer
- AI Business Chatbot
- Sentiment Analyzer
- AI Image Generator with provider fallback
- Audio Tools
- Sales Predictor
- Local history/persistence for major tools

## Tech Stack

- Python
- Flask
- TextBlob
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
|- history_store.py
|- response_utils.py
|- routes/
|  |- __init__.py
|  |- api.py
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
```

Notes:

- `OPENROUTER_KEY` is used for text generation and as an image fallback.
- `HF_TOKEN` is used for Hugging Face image generation.
- Do not commit `.env`.

## Install Locally

From the project folder:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If TextBlob corpora are missing in your environment, install them:

```powershell
python -m textblob.download_corpora
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

## Production / Render Deploy

This project is set up for Gunicorn deployment.

- Build command:

```text
pip install -r requirements.txt
```

- Start command:

```text
gunicorn app:app
```

- Required environment variables on Render:
  - `OPENROUTER_KEY`
  - `HF_TOKEN`

## Image Generation Flow

The image generator uses backend provider fallback in this order:

1. Hugging Face
2. OpenRouter
3. Pollinations

Generated images are saved into `static/generated/` and then served back to the browser with a normal static URL.

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

## Main Routes

Pages:

- `/`
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

## Future Improvements

- Add authentication
- Move history to a real database
- Add automated tests
- Add rate limiting and API protection
- Share more frontend utilities across pages
