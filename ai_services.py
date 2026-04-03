import base64
import math
import os
import random
import urllib.parse
from io import BytesIO
from uuid import uuid4

import requests


DEFAULT_REQUEST_TIMEOUT = 60
IMAGE_REQUEST_TIMEOUT = 120


def get_openrouter_key():
    """Read the current OpenRouter key from the environment."""
    return os.environ.get("OPENROUTER_KEY")


def get_hf_token():
    """Read the current Hugging Face token from the environment."""
    return os.environ.get("HF_TOKEN")


def require_text(data, field_name, label=None, max_length=4000):
    """Validate and normalize a required text field."""
    value = (data.get(field_name) or '').strip()
    readable_label = label or field_name.replace('_', ' ').title()

    if not value:
        return None, f'{readable_label} is required.'
    if len(value) > max_length:
        return None, f'{readable_label} is too long.'
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
    if polarity > 0.1:
        return "Positive", "#4CAF50"
    if polarity < -0.1:
        return "Negative", "#f44336"
    return "Neutral", "#FF9800"


def ask_ai(prompt):
    """Send prompt to AI and get response."""
    try:
        openrouter_key = get_openrouter_key()
        if not openrouter_key:
            return "AI is not configured. Add OPENROUTER_KEY to the environment."

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "BizGenius AI"
        }
        models_to_try = [
            "google/gemma-3-27b-it:free",
            "deepseek/deepseek-chat-v3-0324:free",
            "qwen/qwen3-8b:free",
            "meta-llama/llama-3.3-8b-instruct:free",
            "mistralai/mistral-small-3.1-24b-instruct:free",
            "google/gemma-3-4b-it:free",
        ]

        for model in models_to_try:
            print(f"[AI] Trying: {model}")
            response = requests.post(
                url,
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
                timeout=DEFAULT_REQUEST_TIMEOUT
            )
            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                print(f"[AI] Success with: {model}")
                return result['choices'][0]['message']['content']

            if 'error' in result:
                print(f"[AI] Failed {model}: {result['error'].get('message', '')}")

        return "AI is temporarily busy. Please try again in a minute."
    except requests.exceptions.Timeout:
        return "Request timed out. Please try again."
    except Exception as exc:
        return f"Error: {str(exc)}"


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


def save_image_to_static(static_folder, image_source, content_type='image/png'):
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

    filename = f"generated_{uuid4().hex}.{extension}"
    filepath = os.path.join(generated_dir, filename)
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
