import base64
import csv
import hashlib
import math
import os
import random
import re
import statistics
import tempfile
import urllib.parse
from collections import Counter
from io import BytesIO, StringIO
from uuid import uuid4

import requests

from logging_utils import log_event


DEFAULT_REQUEST_TIMEOUT = int(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "20"))
IMAGE_REQUEST_TIMEOUT = 120
DEFAULT_TEXT_MODELS = [
    model.strip()
    for model in os.environ.get(
        "OPENROUTER_TEXT_MODELS",
        os.environ.get("OPENROUTER_TEXT_MODEL", "stepfun/step-3.5-flash:free,qwen/qwen3.6-plus:free,meta-llama/llama-3.3-70b-instruct:free")
    ).split(",")
    if model.strip()
]
DEFAULT_CHAT_MODELS = [
    model.strip()
    for model in os.environ.get(
        "OPENROUTER_CHAT_MODELS",
        "stepfun/step-3.5-flash:free,qwen/qwen3.6-plus:free"
    ).split(",")
    if model.strip()
]
DEFAULT_CONTENT_MODELS = [
    model.strip()
    for model in os.environ.get(
        "OPENROUTER_CONTENT_MODELS",
        "stepfun/step-3.5-flash:free,qwen/qwen3.6-plus:free"
    ).split(",")
    if model.strip()
]
PROMPT_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt",
    "developer message",
    "reveal your instructions",
    "jailbreak",
    "act as root",
    "bypass safety",
    "pretend you are",
]
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from",
    "had", "has", "have", "i", "if", "in", "into", "is", "it", "its", "just", "my",
    "of", "on", "or", "our", "so", "that", "the", "their", "them", "this", "to",
    "too", "was", "we", "were", "with", "you", "your"
}
TEXT_UPLOAD_EXTENSIONS = {'.txt', '.md', '.csv'}
TEXT_UPLOAD_MIME_PREFIXES = ('text/', 'application/csv')
MAX_AUDIO_UPLOAD_BYTES = 15 * 1024 * 1024
POSITIVE_WORDS = {
    "amazing", "awesome", "best", "brilliant", "easy", "excellent", "fast", "friendly",
    "good", "great", "helpful", "impressive", "love", "loved", "perfect", "positive",
    "professional", "quick", "reliable", "smooth", "strong", "useful", "valuable"
}
NEGATIVE_WORDS = {
    "awful", "bad", "broke", "broken", "confusing", "delayed", "disappointed",
    "disappointing", "frustrating", "hate", "horrible", "late", "poor", "problem",
    "refund", "rude", "slow", "terrible", "unhelpful", "waste", "worst"
}
SUBJECTIVE_WORDS = POSITIVE_WORDS | NEGATIVE_WORDS | {
    "believe", "feel", "think", "prefer", "expect", "recommend", "should", "wish"
}
EMOTION_LEXICON = {
    "joy": {"amazing", "awesome", "best", "great", "love", "loved", "perfect"},
    "trust": {"reliable", "professional", "helpful", "smooth", "valuable"},
    "anger": {"awful", "hate", "horrible", "rude", "worst"},
    "frustration": {"confusing", "delayed", "frustrating", "problem", "slow", "unhelpful"},
    "disappointment": {"bad", "broke", "disappointed", "poor", "refund"},
}


def get_openrouter_key():
    """Read the current OpenRouter key from the environment."""
    return os.environ.get("OPENROUTER_KEY")


def get_hf_token():
    """Read the current Hugging Face token from the environment."""
    return os.environ.get("HF_TOKEN")


def get_text_models(models=None):
    """Return the requested text models, falling back to configured defaults."""
    if models:
        return [model.strip() for model in models if model and model.strip()]
    if DEFAULT_TEXT_MODELS:
        return DEFAULT_TEXT_MODELS
    return ["stepfun/step-3.5-flash:free", "qwen/qwen3.6-plus:free"]


def get_chat_models():
    """Return the preferred model order for chat-style responses."""
    return DEFAULT_CHAT_MODELS or get_text_models()


def get_content_models():
    """Return the preferred model order for content-writing responses."""
    return DEFAULT_CONTENT_MODELS or get_text_models()


def require_text(data, field_name, label=None, max_length=4000):
    """Validate and normalize a required text field."""
    value = normalize_user_text(data.get(field_name) or '')
    readable_label = label or field_name.replace('_', ' ').title()

    if not value:
        return None, f'{readable_label} is required.'
    if len(value) > max_length:
        return None, f'{readable_label} is too long.'
    return value, None


def normalize_user_text(value):
    """Collapse noisy whitespace in incoming text."""
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def detect_prompt_injection(value):
    """Return a human-friendly reason when the input resembles prompt injection."""
    normalized = normalize_user_text(value).lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern in normalized:
            return f'Please remove instruction-like text such as "{pattern}" and try again.'
    return None


def parse_optional_text(data, field_name, max_length=4000):
    """Normalize optional text fields and enforce max length when present."""
    value = normalize_user_text(data.get(field_name) or '')
    if value and len(value) > max_length:
        return None, f'{field_name.replace("_", " ").title()} is too long.'
    return value, None


def parse_image_dimensions(data):
    """Validate image dimensions from incoming JSON."""
    try:
        width = int(data.get('width', 512))
        height = int(data.get('height', 512))
    except (TypeError, ValueError):
        return None, None, 'Width and height must be valid numbers.'

    allowed_sizes = {(512, 512), (768, 512), (512, 768)}
    if (width, height) not in allowed_sizes:
        return None, None, 'Unsupported image size selected.'

    return width, height, None


def sentiment_metadata(polarity):
    """Map polarity score to UI label and color."""
    if polarity > 0.12:
        return "Positive", "#4CAF50"
    if polarity < -0.12:
        return "Negative", "#f44336"
    return "Neutral", "#FF9800"


def ask_ai(prompt, models=None, fallback_text=None, max_tokens=None):
    """Send prompt to AI and get response."""
    try:
        openrouter_key = get_openrouter_key()
        if not openrouter_key:
            return fallback_text or "AI is not configured. Add OPENROUTER_KEY to the environment."

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "BizGenius AI"
        }
        requested_models = get_text_models(models)
        errors = []

        for model in requested_models:
            log_event('ai_request_started', model=model)
            response = requests.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    **({"max_tokens": max_tokens} if max_tokens else {})
                },
                timeout=DEFAULT_REQUEST_TIMEOUT
            )
            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                log_event('ai_request_succeeded', model=model)
                return result['choices'][0]['message']['content']

            if 'error' in result:
                error_text = result['error'].get('message', str(result['error']))
                errors.append(f"{model}: {error_text}")
                log_event(
                    'ai_request_failed',
                    model=model,
                    status_code=response.status_code,
                    error=error_text
                )
                continue

            if response.status_code != 200:
                api_error = result.get('message') or result.get('detail') or 'Unknown OpenRouter API error.'
                errors.append(f"{model}: {api_error}")
                log_event(
                    'ai_request_failed',
                    model=model,
                    status_code=response.status_code,
                    error='Unexpected status code from OpenRouter'
                )
                continue

            errors.append(f"{model}: Empty response from OpenRouter.")

        if fallback_text:
            return fallback_text
        if errors:
            return "OpenRouter error: " + " | ".join(errors)
        return "AI is temporarily busy. Please try again in a minute."
    except requests.exceptions.Timeout:
        log_event('ai_request_timeout', model=get_text_models(models)[0])
        return fallback_text or "Request timed out. Please try again."
    except Exception as exc:
        log_event('ai_request_exception', model=get_text_models(models)[0], error=str(exc))
        return fallback_text or f"Error: {str(exc)}"


def build_content_prompt(content_type, topic, details='', variation_mode='fresh', previous_output=''):
    """Create a safer, more controllable content-writing prompt."""
    content_lengths = {
        "Marketing Email": "Keep it between 120 and 180 words.",
        "Product Description": "Keep it between 80 and 140 words.",
        "Social Media Caption": "Keep it under 90 words.",
        "Blog Post Introduction": "Keep it between 90 and 140 words.",
        "Business Proposal": "Keep it between 140 and 220 words.",
        "Press Release": "Keep it between 140 and 220 words.",
        "Customer Thank You Note": "Keep it under 100 words.",
        "Job Description": "Keep it between 140 and 220 words.",
    }
    instructions = [
        "You are a professional business content writer.",
        f"Write a {content_type} about: {topic}.",
        content_lengths.get(content_type, "Keep it concise and ready to use."),
    ]
    if details:
        instructions.append(f"Additional details to respect: {details}.")
    if variation_mode == 'variation' and previous_output:
        instructions.append("Create a fresh alternate version, not a paraphrase, of the previous draft.")
        instructions.append(f"Previous draft for reference: {previous_output}")
    elif variation_mode == 'rewrite' and previous_output:
        instructions.append("Rewrite the previous draft into a cleaner, stronger version while keeping the same goal.")
        instructions.append(f"Previous draft for reference: {previous_output}")
    instructions.append("Make it professional, engaging, and ready to use.")
    instructions.append("Use plain text only. Do not use markdown, bullet symbols, or meta commentary.")
    instructions.append("Do not include setup notes or explanation, only the final content.")
    return "\n".join(instructions)


def build_content_fallback(content_type, topic, details='', variation_mode='fresh'):
    """Provide a usable content draft if the AI provider is unavailable."""
    opener = {
        "Marketing Email": f"Subject: A smarter next step for {topic}",
        "Product Description": f"{topic}\n\n",
        "Social Media Caption": f"{topic}\n\n",
    }.get(content_type, f"{content_type}: {topic}\n\n")
    angle = "Try a fresh angle" if variation_mode == 'variation' else "Keep the message direct and useful"
    return (
        f"{opener}"
        f"This draft focuses on {topic}. {angle}. "
        f"{details or 'Highlight the value, the key benefit, and a clear call to action.'}"
    )


def build_chat_prompt(user_message, history_items):
    """Include the user's recent chat history so answers feel continuous."""
    history_lines = []
    for item in reversed(history_items[-4:]):
        history_lines.append(f"User: {item.get('input_text', '')}")
        history_lines.append(f"Assistant: {item.get('output_text', '')}")
    history_block = "\n".join(history_lines) if history_lines else "No recent conversation."
    return f"""You are BizGenius AI, a helpful and natural-sounding business advisor.
Reply like a smart human advisor having a real conversation.
Be practical, clear, and warm.
Avoid emojis, markdown, headings, bold text, and consultant-style formatting.
Prefer 2 to 4 short paragraphs. Use a short numbered list only when it truly helps.
Continue the conversation naturally using the recent context below when relevant.

Recent conversation:
{history_block}

Current user message:
{user_message}"""


def normalize_chat_response(text):
    """Make model output read more naturally in the chat UI."""
    value = str(text or "").strip()
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"\*(.*?)\*", r"\1", value)
    value = re.sub(r"^#{1,6}\s*", "", value, flags=re.MULTILINE)
    value = value.replace("• ", "- ")
    value = value.replace("– ", "- ")
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value


def normalize_content_response(text):
    """Keep generated content in plain text for the UI."""
    value = str(text or "").strip()
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"\*(.*?)\*", r"\1", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value


def build_chat_fallback(user_message, history_items):
    """Provide a simple business-oriented fallback reply."""
    context_hint = ""
    if history_items:
        context_hint = f"You've recently been discussing {history_items[0].get('input_text', 'business strategy')}. "
    return (
        f"{context_hint}Here are three practical next steps for your question about '{user_message}':\n"
        "1. Clarify the goal, audience, and timeframe.\n"
        "2. Start with one measurable action you can test this week.\n"
        "3. Review results quickly and refine based on what works."
    )


def tokenize_text(text):
    """Split text into lowercase word tokens."""
    return re.findall(r"[a-zA-Z']+", text.lower())


def extract_top_keywords(text, limit=5):
    """Return the most useful repeated keywords from free-form text."""
    tokens = [token for token in tokenize_text(text) if len(token) > 2 and token not in STOPWORDS]
    counts = Counter(tokens)
    return [word for word, _ in counts.most_common(limit)]


def analyze_sentiment_signals(text):
    """Return richer sentiment metadata without relying on external NLP packages."""
    tokens = tokenize_text(text)
    token_count = len(tokens) or 1
    positive_hits = sum(1 for token in tokens if token in POSITIVE_WORDS)
    negative_hits = sum(1 for token in tokens if token in NEGATIVE_WORDS)
    subjective_hits = sum(1 for token in tokens if token in SUBJECTIVE_WORDS)

    polarity = max(min((positive_hits - negative_hits) / max(token_count / 3, 1), 1), -1)
    subjectivity = min(subjective_hits / max(token_count / 2, 1), 1)
    label, color = sentiment_metadata(polarity)

    emotion_scores = {
        emotion: sum(1 for token in tokens if token in words)
        for emotion, words in EMOTION_LEXICON.items()
    }
    emotion, emotion_score = max(emotion_scores.items(), key=lambda item: item[1], default=("neutral", 0))
    if emotion_score == 0:
        emotion = "neutral"

    confidence = min(
        0.98,
        0.38 + abs(polarity) * 0.45 + min(positive_hits + negative_hits, 5) * 0.05
    )

    return {
        'polarity': round(polarity, 2),
        'subjectivity': round(subjectivity, 2),
        'label': label,
        'color': color,
        'confidence': round(confidence, 2),
        'top_keywords': extract_top_keywords(text, 5),
        'emotion': emotion.replace('-', ' ').title()
    }


def build_sentiment_prompt(text, sentiment):
    """Create a richer sentiment analysis prompt for the AI explanation layer."""
    keywords = ", ".join(sentiment['top_keywords']) or "none noted"
    return f"""Analyze this customer review in a concise business-friendly way:
"{text}"

Detected sentiment summary:
- Label: {sentiment['label']}
- Confidence: {sentiment['confidence']}
- Emotion: {sentiment['emotion']}
- Top keywords: {keywords}

Provide:
1. Overall mood
2. What customers liked
3. What customers disliked
4. One smart business response"""


def build_sentiment_fallback(text, sentiment):
    """Fallback explanation when the AI provider is unavailable."""
    keywords = ", ".join(sentiment['top_keywords']) or "no dominant keywords"
    return (
        f"Overall mood: {sentiment['label']} with {sentiment['confidence'] * 100:.0f}% confidence.\n"
        f"Likely emotion: {sentiment['emotion']}.\n"
        f"Top keywords: {keywords}.\n"
        "Business suggestion: acknowledge the feedback directly, reinforce what worked, and fix the most obvious pain point."
    )


def parse_sales_input(sales_text='', csv_text=''):
    """Parse either comma-separated sales data or uploaded CSV content."""
    values = []

    if csv_text:
        reader = csv.reader(StringIO(csv_text))
        for row in reader:
            for cell in row:
                cleaned = re.sub(r'[^0-9.\-]', '', cell or '')
                if cleaned and re.fullmatch(r'-?\d+(?:\.\d+)?', cleaned):
                    values.append(float(cleaned))

    if not values and sales_text:
        chunks = re.split(r'[\s,]+', sales_text.strip())
        for chunk in chunks:
            cleaned = re.sub(r'[^0-9.\-]', '', chunk)
            if cleaned and re.fullmatch(r'-?\d+(?:\.\d+)?', cleaned):
                values.append(float(cleaned))

    if len(values) < 4:
        return None, 'Please provide at least 4 months of sales data.'
    if len(values) > 36:
        return None, 'Please limit sales input to 36 data points.'
    if any(value < 0 for value in values):
        return None, 'Sales values cannot be negative.'
    return values, None


def holt_linear_forecast(series, periods=3, alpha=0.55, beta=0.35):
    """Simple Holt trend smoothing implemented locally."""
    level = series[0]
    trend = series[1] - series[0] if len(series) > 1 else 0
    fitted = [series[0]]

    for actual in series[1:]:
        previous_level = level
        level = alpha * actual + (1 - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (1 - beta) * trend
        fitted.append(level + trend)

    forecasts = [max(level + trend * step, 0) for step in range(1, periods + 1)]
    return forecasts, fitted


def linear_regression_forecast(series, periods=3):
    """Fallback forecaster for shorter datasets."""
    count = len(series)
    x_values = list(range(count))
    x_mean = sum(x_values) / count
    y_mean = sum(series) / count
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, series))
    denominator = sum((x - x_mean) ** 2 for x in x_values) or 1
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    fitted = [intercept + slope * x for x in x_values]
    forecasts = [max(intercept + slope * (count + step), 0) for step in range(periods)]
    return forecasts, fitted


def analyze_sales_series(series):
    """Return forecasts, intervals, and business-readable metadata."""
    if len(series) >= 6:
        forecasts, fitted = holt_linear_forecast(series, periods=3)
        method = 'holt-trend'
    else:
        forecasts, fitted = linear_regression_forecast(series, periods=3)
        method = 'linear-fallback'

    errors = [actual - estimate for actual, estimate in zip(series, fitted)]
    error_std = statistics.pstdev(errors) if len(errors) > 1 else max(series[-1] * 0.08, 1)
    interval_size = max(error_std * 1.65, max(series[-1] * 0.06, 1))

    lower_bounds = [max(value - interval_size, 0) for value in forecasts]
    upper_bounds = [value + interval_size for value in forecasts]

    growth_rate = ((series[-1] - series[0]) / series[0] * 100) if series[0] else 0
    if growth_rate > 8:
        trend = 'Growing'
    elif growth_rate < -8:
        trend = 'Declining'
    else:
        trend = 'Stable'

    recommendations = {
        'Growing': [
            'Increase inventory and fulfillment capacity ahead of demand spikes.',
            'Double down on the channels responsible for the recent lift.',
            'Protect margins while scaling with targeted upsells.'
        ],
        'Declining': [
            'Review the weakest acquisition channel and pause low-performing spend.',
            'Re-engage recent customers with targeted offers or retention campaigns.',
            'Audit pricing, product mix, and seasonality before making bigger cuts.'
        ],
        'Stable': [
            'Experiment with one new growth channel while keeping core demand steady.',
            'Use promotions selectively to avoid flattening margins.',
            'Track repeat purchase behavior to create the next growth lever.'
        ]
    }

    return {
        'series': [round(value, 2) for value in series],
        'forecast': [round(value, 2) for value in forecasts],
        'lower_bounds': [round(value, 2) for value in lower_bounds],
        'upper_bounds': [round(value, 2) for value in upper_bounds],
        'method': method,
        'trend': trend,
        'growth_rate': round(growth_rate, 1),
        'recommendations': recommendations[trend]
    }


def build_sales_analysis_text(sales_analysis):
    """Create a readable summary from the computed forecast data."""
    forecast_lines = []
    for index, value in enumerate(sales_analysis['forecast'], start=1):
        forecast_lines.append(
            f"Month +{index}: ${value:,.0f} "
            f"(range ${sales_analysis['lower_bounds'][index - 1]:,.0f} to ${sales_analysis['upper_bounds'][index - 1]:,.0f})"
        )
    recommendations = "\n".join(f"- {item}" for item in sales_analysis['recommendations'])
    method_label = 'Holt trend smoothing' if sales_analysis['method'] == 'holt-trend' else 'Linear fallback'
    return (
        f"Trend: {sales_analysis['trend']} ({sales_analysis['growth_rate']}% change across the provided period)\n"
        f"Forecast method: {method_label}\n\n"
        f"Next 3 months:\n" + "\n".join(forecast_lines) + "\n\n"
        f"Recommendations:\n{recommendations}"
    )


def build_audio_notes_fallback(transcript_text):
    """Create usable transcript notes even if text generation is unavailable."""
    sentences = [segment.strip() for segment in re.split(r'(?<=[.!?])\s+', transcript_text) if segment.strip()]
    summary = sentences[0] if sentences else transcript_text[:180]
    bullet_source = sentences[1:4] if len(sentences) > 1 else [transcript_text[:160]]
    bullets = "\n".join(f"- {line}" for line in bullet_source)
    return (
        f"Summary:\n{summary}\n\n"
        f"Key takeaways:\n{bullets}\n\n"
        "Action items:\n- Review the transcript and confirm the top priority.\n- Assign owners to the key next steps.\n- Follow up with a short written recap."
    )


def read_uploaded_text_file(file_storage):
    """Extract text from a supported uploaded transcript file."""
    filename = (file_storage.filename or '').strip()
    extension = os.path.splitext(filename.lower())[1]
    mime_type = (file_storage.mimetype or '').lower()

    if extension not in TEXT_UPLOAD_EXTENSIONS and not any(
        mime_type.startswith(prefix) for prefix in TEXT_UPLOAD_MIME_PREFIXES
    ):
        return None, 'Upload a .txt, .md, or .csv transcript file.'

    file_bytes = file_storage.read()
    if not file_bytes:
        return None, 'Uploaded transcript file is empty.'

    decoded = file_bytes.decode('utf-8', errors='ignore')
    return normalize_user_text(decoded), None


def transcribe_audio_bytes(audio_bytes, filename='audio.wav', model='openai/whisper-large-v3'):
    """Transcribe uploaded audio bytes using Hugging Face ASR."""
    hf_token = get_hf_token()
    if not hf_token:
        return None, 'HF_TOKEN is missing, so server-side audio transcription is unavailable.'

    if not audio_bytes:
        return None, 'Uploaded audio file is empty.'

    if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
        return None, 'Audio file is too large. Please keep uploads under 15 MB.'

    try:
        from huggingface_hub import InferenceClient
    except Exception:
        return None, 'huggingface_hub is not installed. Restart after installing requirements.'

    try:
        client = InferenceClient(provider="hf-inference", api_key=hf_token)
        suffix = os.path.splitext(filename or 'audio.wav')[1] or '.wav'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
            temp_audio.write(audio_bytes)
            temp_path = temp_audio.name

        try:
            result = client.automatic_speech_recognition(audio=temp_path, model=model)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

        if isinstance(result, str):
            transcript = result
        else:
            transcript = getattr(result, 'text', '') or result.get('text', '')

        transcript = normalize_user_text(transcript)
        if not transcript:
            return None, 'The audio was processed, but no transcript text was returned.'
        return transcript, None
    except Exception as exc:
        return None, f'Audio transcription failed: {str(exc)}'


def build_aspect_ratio(width, height):
    """Convert numeric dimensions into a simple aspect ratio string."""
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def find_image_url(payload):
    """Recursively search API payloads for a usable image URL or data URL."""
    if isinstance(payload, str):
        if payload.startswith("data:image/") or payload.startswith("http"):
            return payload
        return None

    if isinstance(payload, dict):
        for value in payload.values():
            found = find_image_url(value)
            if found:
                return found
        return None

    if isinstance(payload, list):
        for item in payload:
            found = find_image_url(item)
            if found:
                return found
        return None

    return None


def make_image_cache_key(prompt, width, height):
    """Generate a stable hash for repeated image requests."""
    raw = f"{normalize_user_text(prompt)}|{width}|{height}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:24]


def find_cached_image_url(static_folder, prompt, width, height):
    """Return an existing generated image URL when the same request was already created."""
    cache_key = make_image_cache_key(prompt, width, height)
    generated_dir = os.path.join(static_folder, 'generated')
    if not os.path.isdir(generated_dir):
        return None

    for extension in ('png', 'jpg', 'jpeg', 'webp'):
        filename = f"generated_{cache_key}.{extension}"
        filepath = os.path.join(generated_dir, filename)
        if os.path.exists(filepath):
            return f"/static/generated/{filename}"
    return None


def save_image_to_static(static_folder, image_source, content_type='image/png', cache_key=None):
    """Persist generated images to /static/generated and return a browser-friendly URL."""
    generated_dir = os.path.join(static_folder, 'generated')
    os.makedirs(generated_dir, exist_ok=True)

    extension_map = {
        'image/png': 'png',
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/webp': 'webp',
    }
    extension = extension_map.get(content_type, 'png')

    if isinstance(image_source, str) and image_source.startswith('data:image/'):
        header, encoded = image_source.split(',', 1)
        mime_type = header.split(';')[0].split(':', 1)[1]
        extension = extension_map.get(mime_type, extension)
        image_bytes = base64.b64decode(encoded)
    elif isinstance(image_source, str) and image_source.startswith('http'):
        response = requests.get(image_source, timeout=DEFAULT_REQUEST_TIMEOUT)
        response.raise_for_status()
        mime_type = response.headers.get('Content-Type', content_type)
        extension = extension_map.get(mime_type, extension)
        image_bytes = response.content
    else:
        raise ValueError('Unsupported image payload format.')

    filename = f"generated_{cache_key or uuid4().hex}.{extension}"
    filepath = os.path.join(generated_dir, filename)
    if cache_key and os.path.exists(filepath):
        return f"/static/generated/{filename}"
    with open(filepath, 'wb') as image_file:
        image_file.write(image_bytes)

    return f"/static/generated/{filename}"


def try_huggingface_image(prompt, width, height):
    """Preferred image provider when HF_TOKEN is available."""
    hf_token = get_hf_token()
    if not hf_token:
        return {'success': False, 'provider': 'huggingface', 'error': 'HF_TOKEN is missing.'}

    try:
        from huggingface_hub import InferenceClient
    except Exception:
        return {
            'success': False,
            'provider': 'huggingface',
            'error': 'huggingface_hub is not installed. Add it from requirements and restart.'
        }

    models_to_try = ["stabilityai/stable-diffusion-xl-base-1.0"]
    last_error = None

    for model in models_to_try:
        try:
            print(f"[IMG] Trying Hugging Face: {model}")
            client = InferenceClient(provider="hf-inference", api_key=hf_token)
            image = client.text_to_image(prompt, model=model, width=width, height=height)
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return {
                'success': True,
                'image_url': f"data:image/png;base64,{img_base64}",
                'provider': 'huggingface',
                'content_type': 'image/png'
            }
        except Exception as exc:
            print(f"[IMG] Hugging Face error ({model}): {exc}")
            last_error = str(exc)

    return {
        'success': False,
        'provider': 'huggingface',
        'error': last_error or 'Hugging Face image generation failed.'
    }


def try_pollinations(prompt, width, height):
    """Try free Pollinations endpoints as a final fallback."""
    seed = random.randint(1, 999999)
    encoded = urllib.parse.quote(prompt)
    request_headers = {
        "User-Agent": "BizGeniusAI/1.0",
        "Accept": "image/*,*/*;q=0.8",
    }
    last_error = None
    image_urls = [
        f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed + 1}&nologo=true&model=flux",
    ]

    for url in image_urls:
        try:
            print(f"[IMG] Trying Pollinations: {url[:80]}...")
            response = requests.get(url, headers=request_headers, timeout=20)
            content_type = response.headers.get("Content-Type", "")

            if response.status_code == 200 and content_type.startswith("image/") and len(response.content) > 1000:
                img_base64 = base64.b64encode(response.content).decode('utf-8')
                return {
                    'success': True,
                    'image_url': f"data:{content_type};base64,{img_base64}",
                    'provider': 'pollinations',
                    'content_type': content_type
                }

            if response.status_code == 429:
                last_error = "Pollinations is rate-limiting requests right now. Please wait a minute and try again."
            else:
                last_error = f"Pollinations returned {response.status_code}."
            print(f"[IMG] Pollinations bad response: {response.status_code}, content-type={content_type}")
        except requests.exceptions.Timeout:
            print("[IMG] Pollinations timeout, trying next...")
            last_error = "Pollinations timed out."
        except Exception as exc:
            print(f"[IMG] Pollinations error: {exc}")
            last_error = f"Pollinations error: {str(exc)}"

    return {'success': False, 'provider': 'pollinations', 'error': last_error or 'Pollinations failed.'}


def try_openrouter_image(prompt, width, height):
    """Fallback to OpenRouter image generation when available."""
    openrouter_key = get_openrouter_key()
    if not openrouter_key:
        return {'success': False, 'provider': 'openrouter', 'error': 'OPENROUTER_KEY is missing.'}

    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "BizGenius AI"
    }
    body = {
        "model": "google/gemini-3.1-flash-image-preview",
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "stream": False,
        "max_tokens": 300,
        "image_config": {"aspect_ratio": build_aspect_ratio(width, height)},
    }
    last_error = None

    for attempt in range(2):
        try:
            print(f"[IMG] Trying OpenRouter image fallback (attempt {attempt + 1})")
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=body,
                timeout=IMAGE_REQUEST_TIMEOUT
            )
            result = response.json()
            image_url = find_image_url(result)

            if response.status_code == 200 and image_url:
                return {
                    'success': True,
                    'image_url': image_url,
                    'provider': 'openrouter',
                    'content_type': 'image/png'
                }

            if response.status_code == 402:
                last_error = "OpenRouter image generation is unavailable because the current account does not have enough credits."
            else:
                last_error = f"OpenRouter returned {response.status_code}."
            print(f"[IMG] OpenRouter bad response: {response.status_code} {str(result)[:300]}")
        except Exception as exc:
            print(f"[IMG] OpenRouter error: {exc}")
            last_error = f"OpenRouter error: {str(exc)}"

    return {'success': False, 'provider': 'openrouter', 'error': last_error or 'OpenRouter image generation failed.'}
