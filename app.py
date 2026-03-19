from flask import Flask, render_template, request, jsonify
from textblob import TextBlob
import requests
import base64
import os


app = Flask(__name__)

# ============================================
# YOUR API KEY
# ============================================
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")

if not OPENROUTER_KEY:
    raise ValueError("OPENROUTER_KEY is not set")


def ask_ai(prompt):
    """Send prompt to AI and get response."""
    try:
        if not OPENROUTER_KEY:
            return "Error: API key not configured. Please set OPENROUTER_KEY environment variable."

        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://bizgenius-ai.onrender.com",
            "X-Title": "BizGenius AI"
        }

        models_to_try = [
            "google/gemma-3-27b-it:free",
            "google/gemma-3-4b-it:free",
            "deepseek/deepseek-chat-v3-0324:free",
            "qwen/qwen3-8b:free",
            "meta-llama/llama-3.3-8b-instruct:free",
            "mistralai/mistral-small-3.1-24b-instruct:free",
        ]

        for model in models_to_try:
            print(f"[AI] Trying: {model}")

            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}]
            }

            try:
                response = requests.post(url, headers=headers, json=data, timeout=60)
                result = response.json()

                print(f"[AI] Response status: {response.status_code}")

                if 'choices' in result and len(result['choices']) > 0:
                    answer = result['choices'][0]['message']['content']
                    print(f"[AI] Success with: {model}")
                    return answer

                if 'error' in result:
                    error_msg = result['error'].get('message', 'Unknown')
                    print(f"[AI] Error from {model}: {error_msg}")
                    continue

            except requests.exceptions.Timeout:
                print(f"[AI] Timeout for {model}")
                continue
            except Exception as e:
                print(f"[AI] Exception for {model}: {str(e)}")
                continue

        return "AI is temporarily busy. Please try again in a minute."

    except Exception as e:
        print(f"[AI] Fatal error: {str(e)}")
        return f"Error: {str(e)}"
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
            sentiment_label = "Positive 😊"
            color = "#4CAF50"
        elif polarity < -0.1:
            sentiment_label = "Negative 😞"
            color = "#f44336"
        else:
            sentiment_label = "Neutral 😐"
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
        prompt = data.get('prompt', '')
        width = data.get('width', 512)
        height = data.get('height', 512)

        import urllib.parse
        import random

        seed = random.randint(1, 999999)
        encoded = urllib.parse.quote(prompt)

        image_urls = [
            f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed}&nologo=true",
            f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&seed={seed+1}&nologo=true&model=flux",
        ]

        for url in image_urls:
            try:
                print(f"[IMG] Trying: {url[:80]}...")
                response = requests.get(url, timeout=90)

                if response.status_code == 200 and len(response.content) > 1000:
                    img_base64 = base64.b64encode(response.content).decode('utf-8')
                    img_data_url = f"data:image/png;base64,{img_base64}"
                    print(f"[IMG] Success! Size: {len(response.content)} bytes")
                    return jsonify({'success': True, 'image_url': img_data_url})
                else:
                    print(f"[IMG] Bad response: {response.status_code}")
                    continue
            except requests.exceptions.Timeout:
                print("[IMG] Timeout, trying next...")
                continue
            except Exception as e:
                print(f"[IMG] Error: {e}")
                continue

        return jsonify({
            'success': False,
            'error': 'Image generation timed out. Try a shorter description.'
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
