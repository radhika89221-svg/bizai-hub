from flask import Blueprint, current_app, request
from textblob import TextBlob

from ai_services import (
    ask_ai,
    parse_image_dimensions,
    require_text,
    save_image_to_static,
    sentiment_metadata,
    try_huggingface_image,
    try_openrouter_image,
    try_pollinations,
)
from auth_utils import api_login_required, consume_quota, require_quota
from extensions import limiter
from history_store import clear_history_entries, fetch_history_entries, save_history_entry
from response_utils import json_error, json_success, parse_json_request


api_bp = Blueprint('api', __name__)


@api_bp.route('/api/generate-content', methods=['POST'])
@api_login_required
@limiter.limit('30 per hour')
def generate_content():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        content_type, error_message = require_text(data, 'content_type', 'Content type', 120)
        if error_message:
            return json_error(error_message)

        topic, error_message = require_text(data, 'topic', 'Topic', 2000)
        if error_message:
            return json_error(error_message)

        prompt = f"""You are a professional business content writer.
Write a {content_type} about: {topic}
Make it professional, engaging and ready to use.
Do not include any extra explanation, just the content."""
        result = ask_ai(prompt)
        save_history_entry(
            'content-writer',
            topic,
            result,
            {'content_type': content_type}
        )
        consume_quota()
        return json_success(result=result)
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/chat', methods=['POST'])
@api_login_required
@limiter.limit('60 per hour')
def chat():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        user_message, error_message = require_text(data, 'message', 'Message', 3000)
        if error_message:
            return json_error(error_message)

        prompt = f"""You are BizGenius AI, a helpful business advisor chatbot.
Give practical, actionable business advice.
Be concise but thorough. Use bullet points when helpful.
User asks: {user_message}"""
        result = ask_ai(prompt)
        save_history_entry('chatbot', user_message, result)
        consume_quota()
        return json_success(result=result)
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/analyze-sentiment', methods=['POST'])
@api_login_required
@limiter.limit('30 per hour')
def analyze_sentiment():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        text, error_message = require_text(data, 'text', 'Text', 5000)
        if error_message:
            return json_error(error_message)

        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        subjectivity = blob.sentiment.subjectivity
        sentiment_label, color = sentiment_metadata(polarity)

        prompt = f"""Analyze this customer review sentiment in detail:
"{text}"
Provide:
1. Overall Mood
2. Key Positive Points
3. Key Negative Points
4. Suggestions for the business
Keep it concise."""
        ai_analysis = ask_ai(prompt)
        save_history_entry(
            'sentiment',
            text,
            ai_analysis,
            {
                'label': sentiment_label,
                'polarity': round(polarity, 2),
                'subjectivity': round(subjectivity, 2)
            }
        )
        consume_quota()

        return json_success(
            polarity=round(polarity, 2),
            subjectivity=round(subjectivity, 2),
            label=sentiment_label,
            color=color,
            ai_analysis=ai_analysis
        )
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/generate-image-prompt', methods=['POST'])
@api_login_required
@limiter.limit('20 per hour')
def generate_image_prompt():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        description, error_message = require_text(data, 'description', 'Description', 2500)
        if error_message:
            return json_error(error_message)

        prompt = f"""You are a professional graphic designer.
Create a detailed image generation prompt for: {description}
Include: style, colors, composition, lighting, mood.
Give ONLY the prompt text, nothing else."""
        result = ask_ai(prompt)
        save_history_entry('image-prompts', description, result)
        consume_quota()
        return json_success(result=result)
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/generate-real-image', methods=['POST'])
@api_login_required
@limiter.limit('12 per hour')
def generate_real_image():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        prompt, error_message = require_text(data, 'prompt', 'Prompt', 2500)
        if error_message:
            return json_error(error_message)

        width, height, dimension_error = parse_image_dimensions(data)
        if dimension_error:
            return json_error(dimension_error)

        errors = []
        static_folder = current_app.static_folder

        huggingface_result = try_huggingface_image(prompt, width, height)
        if huggingface_result.get('success'):
            huggingface_result['image_url'] = save_image_to_static(
                static_folder,
                huggingface_result['image_url'],
                huggingface_result.get('content_type', 'image/png')
            )
            save_history_entry(
                'image-generator',
                prompt,
                huggingface_result['image_url'],
                {'provider': huggingface_result.get('provider'), 'width': width, 'height': height}
            )
            consume_quota()
            return json_success(**{k: v for k, v in huggingface_result.items() if k != 'success'})
        errors.append(huggingface_result.get('error'))

        openrouter_result = try_openrouter_image(prompt, width, height)
        if openrouter_result.get('success'):
            openrouter_result['image_url'] = save_image_to_static(
                static_folder,
                openrouter_result['image_url'],
                openrouter_result.get('content_type', 'image/png')
            )
            save_history_entry(
                'image-generator',
                prompt,
                openrouter_result['image_url'],
                {'provider': openrouter_result.get('provider'), 'width': width, 'height': height}
            )
            consume_quota()
            return json_success(**{k: v for k, v in openrouter_result.items() if k != 'success'})
        errors.append(openrouter_result.get('error'))

        pollinations_result = try_pollinations(prompt, width, height)
        if pollinations_result.get('success'):
            pollinations_result['image_url'] = save_image_to_static(
                static_folder,
                pollinations_result['image_url'],
                pollinations_result.get('content_type', 'image/png')
            )
            save_history_entry(
                'image-generator',
                prompt,
                pollinations_result['image_url'],
                {'provider': pollinations_result.get('provider'), 'width': width, 'height': height}
            )
            consume_quota()
            return json_success(**{k: v for k, v in pollinations_result.items() if k != 'success'})
        errors.append(pollinations_result.get('error'))

        return json_error("Image generation failed. " + " ".join(error for error in errors if error), 503)
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/history/<tool_name>')
@api_login_required
def get_tool_history(tool_name):
    try:
        allowed_tools = {
            'content-writer',
            'image-generator',
            'image-prompts',
            'chatbot',
            'sentiment',
            'sales-predictor'
        }
        if tool_name not in allowed_tools:
            return json_error('Unknown history tool.', 404)

        limit = request.args.get('limit', 10)
        history = fetch_history_entries(tool_name, limit)
        return json_success(items=history)
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/history/<tool_name>/clear', methods=['POST'])
@api_login_required
def clear_tool_history(tool_name):
    try:
        allowed_tools = {
            'content-writer',
            'image-generator',
            'image-prompts',
            'chatbot',
            'sentiment',
            'sales-predictor'
        }
        if tool_name not in allowed_tools:
            return json_error('Unknown history tool.', 404)

        clear_history_entries(tool_name)
        return json_success(message='History cleared.')
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/predict-sales', methods=['POST'])
@api_login_required
@limiter.limit('20 per hour')
def predict_sales():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        sales_data, error_message = require_text(data, 'sales_data', 'Sales data', 500)
        if error_message:
            return json_error(error_message)

        prompt = f"""You are an expert business analyst.
Based on this monthly sales data (in dollars): {sales_data}

Provide:
1. **Trend Analysis** - Growing, declining, or stable?
2. **Predicted Sales** for next 3 months with numbers
3. **Key Insights** - Patterns you see
4. **Recommendations** - 3-5 strategies

Be specific with numbers. Format with headings."""
        result = ask_ai(prompt)
        save_history_entry('sales-predictor', sales_data, result)
        consume_quota()
        return json_success(result=result)
    except Exception as exc:
        return json_error(str(exc), 500)
