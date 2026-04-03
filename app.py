from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from textblob import TextBlob
import requests
import base64
import os
import math
from io import BytesIO
from uuid import uuid4

load_dotenv()   #this loads .env file
app = Flask(__name__)

# ============================================
# YOUR API KEY
# ============================================
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")
HF_TOKEN = os.environ.get("HF_TOKEN")


def ask_ai(prompt):
    """Send prompt to AI and get response."""
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
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
            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}]
            }

            response = requests.post(url, headers=headers, json=data, timeout=60)
            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                print(f"[AI] Success with: {model}")
                return result['choices'][0]['message']['content']

            if 'error' in result:
                print(f"[AI] Failed {model}: {result['error'].get('message', '')}")
                continue

        return "AI is temporarily busy. Please try again in a minute."

    except requests.exceptions.Timeout:
        return "Request timed out. Please try again."
    except Exception as e:
        return f"Error: {str(e)}"


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


def save_image_to_static(image_source, content_type='image/png'):
    """Persist generated images to /static/generated and return a browser-friendly URL."""
    generated_dir = os.path.join(app.static_folder, 'generated')
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
        response = requests.get(image_source, timeout=60)
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
    if not HF_TOKEN:
        return {'success': False, 'provider': 'huggingface', 'error': 'HF_TOKEN is missing.'}

    try:
        from huggingface_hub import InferenceClient
    except Exception:
        return {
            'success': False,
            'provider': 'huggingface',
            'error': 'huggingface_hub is not installed. Add it from requirements and restart.'
        }

    models_to_try = [
        "stabilityai/stable-diffusion-xl-base-1.0",
    ]
    last_error = None

    for model in models_to_try:
        try:
            print(f"[IMG] Trying Hugging Face: {model}")
            client = InferenceClient(provider="hf-inference", api_key=HF_TOKEN)
            image = client.text_to_image(
                prompt,
                model=model,
                width=width,
                height=height,
            )
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return {
                'success': True,
                'image_url': f"data:image/png;base64,{img_base64}",
                'provider': 'huggingface',
                'content_type': 'image/png'
            }
        except Exception as e:
            print(f"[IMG] Hugging Face error ({model}): {e}")
            last_error = str(e)

    return {
        'success': False,
        'provider': 'huggingface',
        'error': last_error or 'Hugging Face image generation failed.'
    }


def try_pollinations(prompt, width, height):
    """Try free Pollinations endpoints first."""
    import urllib.parse
    import random

    seed = random.randint(1, 999999)
    encoded = urllib.parse.quote(prompt)
    request_headers = {
        "User-Agent": "BizGeniusAI/1.0",
        "Accept": "image/*,*/*;q=0.8",
    }
    last_error = None

    image_urls = [
        f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed+1}&nologo=true&model=flux",
    ]

    for url in image_urls:
        try:
            print(f"[IMG] Trying Pollinations: {url[:80]}...")
            response = requests.get(url, headers=request_headers, timeout=20)
            content_type = response.headers.get("Content-Type", "")

            if (
                response.status_code == 200
                and content_type.startswith("image/")
                and len(response.content) > 1000
            ):
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
        except Exception as e:
            print(f"[IMG] Pollinations error: {e}")
            last_error = f"Pollinations error: {str(e)}"

    return {'success': False, 'provider': 'pollinations', 'error': last_error or 'Pollinations failed.'}


def try_openrouter_image(prompt, width, height):
    """Fallback to OpenRouter image generation when available."""
    if not OPENROUTER_KEY:
        return {'success': False, 'provider': 'openrouter', 'error': 'OPENROUTER_KEY is missing.'}

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
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
                timeout=120
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
        except Exception as e:
            print(f"[IMG] OpenRouter error: {e}")
            last_error = f"OpenRouter error: {str(e)}"

    return {'success': False, 'provider': 'openrouter', 'error': last_error or 'OpenRouter image generation failed.'}


# ============================================
# HOME PAGE
# ============================================
@app.route('/')
def home():
    return render_template('index.html')


# ============================================
# CONTENT WRITER
# ============================================
@app.route('/content-writer')
def content_writer():
    return render_template('content_writer.html')


@app.route('/api/generate-content', methods=['POST'])
def generate_content():
    try:
        data = request.json
        content_type = data.get('content_type')
        topic = data.get('topic')
        prompt = f"""You are a professional business content writer.
Write a {content_type} about: {topic}
Make it professional, engaging and ready to use.
Do not include any extra explanation, just the content."""
        result = ask_ai(prompt)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================
# CHATBOT
# ============================================
@app.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message')
        prompt = f"""You are BizGenius AI, a helpful business advisor chatbot.
Give practical, actionable business advice.
Be concise but thorough. Use bullet points when helpful.
User asks: {user_message}"""
        result = ask_ai(prompt)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================
# SENTIMENT ANALYZER
# ============================================
@app.route('/sentiment')
def sentiment():
    return render_template('sentiment.html')


@app.route('/api/analyze-sentiment', methods=['POST'])
def analyze_sentiment():
    try:
        data = request.json
        text = data.get('text')
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity

        if polarity > 0.1:
            sentiment_label = "Positive"
            color = "#4CAF50"
        elif polarity < -0.1:
            sentiment_label = "Negative"
            color = "#f44336"
        else:
            sentiment_label = "Neutral"
            color = "#FF9800"

        prompt = f"""Analyze this customer review sentiment in detail:
"{text}"
Provide:
1. Overall Mood
2. Key Positive Points
3. Key Negative Points
4. Suggestions for the business
Keep it concise."""
        ai_analysis = ask_ai(prompt)

        return jsonify({
            'success': True,
            'polarity': round(polarity, 2),
            'subjectivity': round(subjectivity, 2),
            'label': sentiment_label,
            'color': color,
            'ai_analysis': ai_analysis
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================
# IMAGE GENERATOR - PROMPT
# ============================================
@app.route('/image-generator')
def image_generator():
    return render_template('image_generator.html')


@app.route('/api/generate-image-prompt', methods=['POST'])
def generate_image_prompt():
    try:
        data = request.json
        description = data.get('description')
        prompt = f"""You are a professional graphic designer.
Create a detailed image generation prompt for: {description}
Include: style, colors, composition, lighting, mood.
Give ONLY the prompt text, nothing else."""
        result = ask_ai(prompt)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================
# REAL IMAGE GENERATION (FREE!)
# ============================================
@app.route('/api/generate-real-image', methods=['POST'])
def generate_real_image():
    try:
        data = request.json
        prompt = (data.get('prompt') or '').strip()
        width = int(data.get('width', 512))
        height = int(data.get('height', 512))

        if not prompt:
            return jsonify({'success': False, 'error': 'Please provide an image prompt.'}), 400

        errors = []

        huggingface_result = try_huggingface_image(prompt, width, height)
        if huggingface_result.get('success'):
            huggingface_result['image_url'] = save_image_to_static(
                huggingface_result['image_url'],
                huggingface_result.get('content_type', 'image/png')
            )
            return jsonify(huggingface_result)
        errors.append(huggingface_result.get('error'))

        openrouter_result = try_openrouter_image(prompt, width, height)
        if openrouter_result.get('success'):
            openrouter_result['image_url'] = save_image_to_static(
                openrouter_result['image_url'],
                openrouter_result.get('content_type', 'image/png')
            )
            return jsonify(openrouter_result)
        errors.append(openrouter_result.get('error'))

        pollinations_result = try_pollinations(prompt, width, height)
        if pollinations_result.get('success'):
            pollinations_result['image_url'] = save_image_to_static(
                pollinations_result['image_url'],
                pollinations_result.get('content_type', 'image/png')
            )
            return jsonify(pollinations_result)
        errors.append(pollinations_result.get('error'))

        return jsonify({
            'success': False,
            'error': "Image generation failed. " + " ".join(error for error in errors if error)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================
# AUDIO TOOLS
# ============================================
@app.route('/audio-tools')
def audio_tools():
    return render_template('audio_tools.html')


# ============================================
# SALES PREDICTOR
# ============================================
@app.route('/sales-predictor')
def sales_predictor():
    return render_template('sales_predictor.html')


@app.route('/api/predict-sales', methods=['POST'])
def predict_sales():
    try:
        data = request.json
        sales_data = data.get('sales_data')
        prompt = f"""You are an expert business analyst.
Based on this monthly sales data (in dollars): {sales_data}

Provide:
1. **Trend Analysis** - Growing, declining, or stable?
2. **Predicted Sales** for next 3 months with numbers
3. **Key Insights** - Patterns you see
4. **Recommendations** - 3-5 strategies

Be specific with numbers. Format with headings."""
        result = ask_ai(prompt)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================
# RUN
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 50)
    print("  BizGenius AI is running!")
    print(f"  Open: http://localhost:{port}")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=port)
