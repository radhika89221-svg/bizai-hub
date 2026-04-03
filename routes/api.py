from threading import Thread
import json

from flask import Blueprint, Response, current_app, request
from flask_login import current_user

from ai_services import (
    analyze_sales_series,
    analyze_sentiment_signals,
    ask_ai,
    build_chat_fallback,
    build_chat_prompt,
    build_content_fallback,
    build_content_prompt,
    build_audio_notes_fallback,
    build_sales_analysis_text,
    build_sentiment_fallback,
    build_sentiment_prompt,
    detect_prompt_injection,
    find_cached_image_url,
    get_chat_models,
    get_content_models,
    make_image_cache_key,
    normalize_chat_response,
    normalize_content_response,
    parse_optional_text,
    parse_sales_input,
    parse_image_dimensions,
    read_uploaded_text_file,
    require_text,
    save_image_to_static,
    transcribe_audio_bytes,
    try_huggingface_image,
    try_openrouter_image,
    try_pollinations,
)
from auth_utils import api_login_required, consume_quota, consume_quota_for_user, require_quota
from extensions import db, limiter
from history_store import clear_history_entries, fetch_history_entries, save_history_entry, save_history_entry_for_user
from logging_utils import log_event
from models import HistoryEntry, ImageJob
from response_utils import json_error, json_success, parse_json_request


api_bp = Blueprint('api', __name__)


@api_bp.route('/api/health', methods=['GET'])
def health_check():
    try:
        # this executes a small AI path call through OpenRouter and returns status
        result = ask_ai('Health check.', fallback_text=None)
        if not result:
            return json_error('Health check failed: OpenRouter returned no response.', 503)
        return json_success(status='healthy', openrouter='reachable', sample=result)
    except Exception as exc:
        return json_error('Health check failed: ' + str(exc), 500)


def update_image_job(job_id, **fields):
    """Persist job progress updates from the background worker."""
    job = ImageJob.query.get(job_id)
    if not job:
        return None

    for key, value in fields.items():
        setattr(job, key, value)
    db.session.commit()
    return job


def run_image_job(app, job_id):
    """Generate the requested image in a background thread."""
    with app.app_context():
        job = ImageJob.query.get(job_id)
        if not job:
            return

        prompt = job.prompt
        width = job.width
        height = job.height
        static_folder = app.static_folder
        cache_key = make_image_cache_key(prompt, width, height)
        errors = []

        try:
            update_image_job(job_id, status='processing', progress_pct=20, status_message='Checking image providers...')
            cached_image_url = find_cached_image_url(static_folder, prompt, width, height)
            if cached_image_url:
                update_image_job(
                    job_id,
                    status='completed',
                    progress_pct=100,
                    status_message='Loaded from cache.',
                    image_url=cached_image_url,
                    provider='cache'
                )
                save_history_entry_for_user(
                    job.user_id,
                    'image-generator',
                    prompt,
                    cached_image_url,
                    {'provider': 'cache', 'width': width, 'height': height, 'cached': True}
                )
                log_event('image_job_completed', job_id=job_id, provider='cache', cached=True)
                return

            update_image_job(job_id, progress_pct=35, status_message='Trying Hugging Face...')
            huggingface_result = try_huggingface_image(prompt, width, height)
            if huggingface_result.get('success'):
                image_url = save_image_to_static(
                    static_folder,
                    huggingface_result['image_url'],
                    huggingface_result.get('content_type', 'image/png'),
                    cache_key=cache_key
                )
                update_image_job(
                    job_id,
                    status='completed',
                    progress_pct=100,
                    status_message='Image ready.',
                    image_url=image_url,
                    provider=huggingface_result.get('provider')
                )
                save_history_entry_for_user(
                    job.user_id,
                    'image-generator',
                    prompt,
                    image_url,
                    {'provider': huggingface_result.get('provider'), 'width': width, 'height': height}
                )
                consume_quota_for_user(job.user_id)
                log_event('image_job_completed', job_id=job_id, provider=huggingface_result.get('provider'))
                return
            errors.append(huggingface_result.get('error'))

            update_image_job(job_id, progress_pct=65, status_message='Trying OpenRouter fallback...')
            openrouter_result = try_openrouter_image(prompt, width, height)
            if openrouter_result.get('success'):
                image_url = save_image_to_static(
                    static_folder,
                    openrouter_result['image_url'],
                    openrouter_result.get('content_type', 'image/png'),
                    cache_key=cache_key
                )
                update_image_job(
                    job_id,
                    status='completed',
                    progress_pct=100,
                    status_message='Image ready.',
                    image_url=image_url,
                    provider=openrouter_result.get('provider')
                )
                save_history_entry_for_user(
                    job.user_id,
                    'image-generator',
                    prompt,
                    image_url,
                    {'provider': openrouter_result.get('provider'), 'width': width, 'height': height}
                )
                consume_quota_for_user(job.user_id)
                log_event('image_job_completed', job_id=job_id, provider=openrouter_result.get('provider'))
                return
            errors.append(openrouter_result.get('error'))

            update_image_job(job_id, progress_pct=85, status_message='Trying final image fallback...')
            pollinations_result = try_pollinations(prompt, width, height)
            if pollinations_result.get('success'):
                image_url = save_image_to_static(
                    static_folder,
                    pollinations_result['image_url'],
                    pollinations_result.get('content_type', 'image/png'),
                    cache_key=cache_key
                )
                update_image_job(
                    job_id,
                    status='completed',
                    progress_pct=100,
                    status_message='Image ready.',
                    image_url=image_url,
                    provider=pollinations_result.get('provider')
                )
                save_history_entry_for_user(
                    job.user_id,
                    'image-generator',
                    prompt,
                    image_url,
                    {'provider': pollinations_result.get('provider'), 'width': width, 'height': height}
                )
                consume_quota_for_user(job.user_id)
                log_event('image_job_completed', job_id=job_id, provider=pollinations_result.get('provider'))
                return
            errors.append(pollinations_result.get('error'))

            update_image_job(
                job_id,
                status='failed',
                progress_pct=100,
                status_message='Image generation failed.',
                error_message=" ".join(error for error in errors if error) or 'Image generation failed.'
            )
            log_event('image_job_failed', job_id=job_id, error=job.error_message)
        except Exception as exc:
            update_image_job(
                job_id,
                status='failed',
                progress_pct=100,
                status_message='Image generation failed.',
                error_message=str(exc)
            )
            log_event('image_job_exception', job_id=job_id, error=str(exc))


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

        topic, error_message = require_text(data, 'topic', 'Topic', 400)
        if error_message:
            return json_error(error_message)

        details, error_message = parse_optional_text(data, 'details', 1200)
        if error_message:
            return json_error(error_message)

        previous_output, error_message = parse_optional_text(data, 'previous_output', 6000)
        if error_message:
            return json_error(error_message)

        variation_mode = (data.get('variation_mode') or 'fresh').strip().lower()
        if variation_mode not in {'fresh', 'variation', 'rewrite'}:
            variation_mode = 'fresh'

        injection_error = detect_prompt_injection(topic) or detect_prompt_injection(details)
        if injection_error:
            return json_error(injection_error)

        topic_key = f"{content_type}|{topic}".lower()
        history = fetch_history_entries('content-writer', 30)
        version_number = (
            sum(1 for item in history if (item.get('meta', {}).get('topic_key') == topic_key))
            + 1
        )

        prompt = build_content_prompt(content_type, topic, details, variation_mode, previous_output)
        result = ask_ai(
            prompt,
            models=get_content_models(),
            fallback_text=build_content_fallback(content_type, topic, details, variation_mode),
            max_tokens=420
        )
        result = normalize_content_response(result)
        save_history_entry(
            'content-writer',
            topic,
            result,
            {
                'content_type': content_type,
                'details': details,
                'variation_mode': variation_mode,
                'version_number': version_number,
                'topic_key': topic_key
            }
        )
        consume_quota()
        return json_success(result=result, version_number=version_number)
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

        injection_error = detect_prompt_injection(user_message)
        if injection_error:
            return json_error(injection_error)

        history = fetch_history_entries('chatbot', 6)
        prompt = build_chat_prompt(user_message, history)
        result = ask_ai(
            prompt,
            models=get_chat_models(),
            fallback_text=build_chat_fallback(user_message, history),
            max_tokens=320
        )
        result = normalize_chat_response(result)
        save_history_entry('chatbot', user_message, result)
        consume_quota()
        return json_success(result=result, context_messages_used=min(len(history), 4))
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

        sentiment = analyze_sentiment_signals(text)
        ai_analysis = ask_ai(
            build_sentiment_prompt(text, sentiment),
            fallback_text=build_sentiment_fallback(text, sentiment)
        )
        save_history_entry(
            'sentiment',
            text,
            ai_analysis,
            sentiment
        )
        consume_quota()

        return json_success(
            polarity=sentiment['polarity'],
            subjectivity=sentiment['subjectivity'],
            label=sentiment['label'],
            color=sentiment['color'],
            confidence=sentiment['confidence'],
            top_keywords=sentiment['top_keywords'],
            emotion=sentiment['emotion'],
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


@api_bp.route('/api/image-jobs', methods=['POST'])
@api_login_required
@limiter.limit('12 per hour')
@limiter.limit('4 per 10 minutes')
def create_image_job():
    try:
        data, error_response = parse_json_request()
        if error_response:
            return error_response

        prompt, error_message = require_text(data, 'prompt', 'Prompt', 2500)
        if error_message:
            return json_error(error_message)

        width, height, dimension_error = parse_image_dimensions(data)
        if dimension_error:
            return json_error(dimension_error)

        static_folder = current_app.static_folder
        cached_image_url = find_cached_image_url(static_folder, prompt, width, height)
        if cached_image_url:
            job = ImageJob(
                user_id=current_user.id,
                prompt=prompt,
                width=width,
                height=height,
                status='completed',
                progress_pct=100,
                status_message='Loaded from cache.',
                image_url=cached_image_url,
                provider='cache'
            )
            db.session.add(job)
            db.session.commit()
            save_history_entry(
                'image-generator',
                prompt,
                cached_image_url,
                {'provider': 'cache', 'width': width, 'height': height, 'cached': True}
            )
            return json_success(
                job_id=job.id,
                status=job.status,
                progress_pct=job.progress_pct,
                image_url=job.image_url,
                provider=job.provider,
                cached=True
            )

        quota_error = require_quota()
        if quota_error:
            return quota_error

        job = ImageJob(
            user_id=current_user.id,
            prompt=prompt,
            width=width,
            height=height,
            status='queued',
            progress_pct=5,
            status_message='Job queued.'
        )
        db.session.add(job)
        db.session.commit()

        app_object = current_app._get_current_object()
        Thread(target=run_image_job, args=(app_object, job.id), daemon=True).start()

        return json_success(
            job_id=job.id,
            status=job.status,
            progress_pct=job.progress_pct,
            status_message=job.status_message
        )
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/image-jobs/<int:job_id>')
@api_login_required
def get_image_job(job_id):
    try:
        job = ImageJob.query.filter_by(id=job_id, user_id=current_user.id).first()
        if not job:
            return json_error('Image job not found.', 404)

        return json_success(
            job_id=job.id,
            status=job.status,
            progress_pct=job.progress_pct,
            status_message=job.status_message,
            image_url=job.image_url,
            provider=job.provider,
            error=job.error_message
        )
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/generate-real-image', methods=['POST'])
@api_login_required
@limiter.limit('12 per hour')
@limiter.limit('4 per 10 minutes')
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
        cache_key = make_image_cache_key(prompt, width, height)
        cached_image_url = find_cached_image_url(static_folder, prompt, width, height)
        if cached_image_url:
            save_history_entry(
                'image-generator',
                prompt,
                cached_image_url,
                {'provider': 'cache', 'width': width, 'height': height, 'cached': True}
            )
            return json_success(
                image_url=cached_image_url,
                provider='cache',
                cached=True
            )

        huggingface_result = try_huggingface_image(prompt, width, height)
        if huggingface_result.get('success'):
            huggingface_result['image_url'] = save_image_to_static(
                static_folder,
                huggingface_result['image_url'],
                huggingface_result.get('content_type', 'image/png'),
                cache_key=cache_key
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
                openrouter_result.get('content_type', 'image/png'),
                cache_key=cache_key
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
                pollinations_result.get('content_type', 'image/png'),
                cache_key=cache_key
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


@api_bp.route('/api/audio-tools/podcast-script', methods=['POST'])
@api_login_required
@limiter.limit('20 per hour')
def generate_podcast_script():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        topic, error_message = require_text(data, 'topic', 'Podcast topic', 2000)
        if error_message:
            return json_error(error_message)

        prompt = f"""You are an expert podcast writer for business creators.
Write a polished 2-minute podcast script about: {topic}

Structure the response with:
1. Hook / intro
2. Main talking points with smooth transitions
3. A clear closing and call to action

Keep it conversational, confident, and ready to read aloud."""
        result = ask_ai(prompt, fallback_text=build_audio_notes_fallback(topic))
        save_history_entry(
            'audio-tools',
            topic,
            result,
            {'kind': 'podcast-script'}
        )
        consume_quota()
        return json_success(result=result)
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/audio-tools/presentation-notes', methods=['POST'])
@api_login_required
@limiter.limit('20 per hour')
def generate_presentation_notes():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        topic, error_message = require_text(data, 'topic', 'Presentation topic', 2000)
        if error_message:
            return json_error(error_message)

        prompt = f"""You are a business presentation coach.
Create speaker notes for a presentation about: {topic}

Include:
1. Strong opening line
2. 4 to 5 key speaking points with useful detail
3. Smooth transitions between sections
4. Memorable closing statement

Make the notes practical, natural, and easy to present live."""
        result = ask_ai(prompt, fallback_text=build_audio_notes_fallback(topic))
        save_history_entry(
            'audio-tools',
            topic,
            result,
            {'kind': 'presentation-notes'}
        )
        consume_quota()
        return json_success(result=result)
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/audio-tools/transcript-insights', methods=['POST'])
@api_login_required
@limiter.limit('20 per hour')
def generate_transcript_insights():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        data, error_response = parse_json_request()
        if error_response:
            return error_response

        transcript, error_message = require_text(data, 'transcript', 'Transcript', 4000)
        if error_message:
            return json_error(error_message)

        prompt = f"""You are a sharp meeting and audio assistant.
Turn this spoken transcript into clean business-ready notes:

{transcript}

Provide:
1. Cleaned summary
2. Key takeaways
3. Action items

Keep it concise and practical."""
        result = ask_ai(prompt, fallback_text=build_audio_notes_fallback(transcript))
        save_history_entry(
            'audio-tools',
            transcript,
            result,
            {'kind': 'transcript-insights'}
        )
        consume_quota()
        return json_success(result=result)
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/audio-tools/upload', methods=['POST'])
@api_login_required
@limiter.limit('20 per hour')
def process_audio_upload():
    try:
        quota_error = require_quota()
        if quota_error:
            return quota_error

        transcript_text = ''
        upload_kind = 'uploaded-transcript'
        uploaded_file = request.files.get('transcript_file') or request.files.get('audio_file')

        if uploaded_file and uploaded_file.filename:
            mime_type = (uploaded_file.mimetype or '').lower()
            if mime_type.startswith('audio/'):
                audio_bytes = uploaded_file.read()
                transcript_text, transcription_error = transcribe_audio_bytes(
                    audio_bytes,
                    filename=uploaded_file.filename
                )
                if transcription_error:
                    transcript_hint = (request.form.get('transcript_hint') or '').strip()
                    if transcript_hint:
                        transcript_text = transcript_hint
                        upload_kind = 'audio-upload-with-transcript'
                    else:
                        return json_error(transcription_error, 400)
                else:
                    upload_kind = 'audio-upload-transcribed'
            else:
                transcript_text, file_error = read_uploaded_text_file(uploaded_file)
                if file_error:
                    return json_error(file_error)
        else:
            transcript_text, error_message = require_text(
                {'transcript_text': request.form.get('transcript_text')},
                'transcript_text',
                'Transcript text',
                5000
            )
            if error_message:
                return json_error(error_message)
            upload_kind = 'pasted-transcript'

        transcript_text = transcript_text.strip()
        if not transcript_text:
            return json_error('Transcript text is required.')

        prompt = f"""You are a sharp meeting and audio assistant.
Turn this uploaded transcript into clear, business-ready notes:

{transcript_text}

Provide:
1. Summary
2. Key takeaways
3. Action items
4. Suggested next step

Keep it concise and useful."""
        result = ask_ai(prompt, fallback_text=build_audio_notes_fallback(transcript_text))
        save_history_entry(
            'audio-tools',
            transcript_text,
            result,
            {'kind': upload_kind}
        )
        consume_quota()
        return json_success(result=result, kind=upload_kind)
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
            'sales-predictor',
            'audio-tools'
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
            'sales-predictor',
            'audio-tools'
        }
        if tool_name not in allowed_tools:
            return json_error('Unknown history tool.', 404)

        clear_history_entries(tool_name)
        return json_success(message='History cleared.')
    except Exception as exc:
        return json_error(str(exc), 500)


@api_bp.route('/api/history/export')
@api_login_required
def export_history():
    try:
        export_format = (request.args.get('format') or 'txt').strip().lower()
        tool = (request.args.get('tool') or '').strip()
        history = fetch_history_entries(tool, 30) if tool else [
            {
                'tool': item.tool,
                'input_text': item.input_text,
                'output_text': item.output_text,
                'meta': item.meta_json or {},
                'created_at': item.created_at.isoformat(timespec='seconds')
            }
            for item in (
                HistoryEntry.query
                .filter_by(user_id=current_user.id)
                .order_by(HistoryEntry.id.desc())
                .limit(50)
                .all()
            )
        ]

        if export_format == 'json':
            payload = json.dumps({'items': history}, ensure_ascii=True, indent=2)
            return Response(
                payload,
                mimetype='application/json',
                headers={'Content-Disposition': 'attachment; filename=bizgenius-history.json'}
            )

        lines = []
        for item in history:
            lines.append(f"Tool: {item.get('tool')}")
            lines.append(f"When: {item.get('created_at')}")
            lines.append(f"Input: {item.get('input_text')}")
            lines.append(f"Output: {item.get('output_text')}")
            lines.append('')
        payload = "\n".join(lines) if lines else 'No saved history yet.'
        return Response(
            payload,
            mimetype='text/plain',
            headers={'Content-Disposition': 'attachment; filename=bizgenius-history.txt'}
        )
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

        sales_data_text, error_message = parse_optional_text(data, 'sales_data', 1200)
        if error_message:
            return json_error(error_message)

        csv_data, error_message = parse_optional_text(data, 'csv_data', 12000)
        if error_message:
            return json_error(error_message)

        sales_series, parse_error = parse_sales_input(sales_data_text, csv_data)
        if parse_error:
            return json_error(parse_error)

        sales_analysis = analyze_sales_series(sales_series)
        result = build_sales_analysis_text(sales_analysis)
        save_history_entry(
            'sales-predictor',
            ", ".join(str(int(value)) if value.is_integer() else str(round(value, 2)) for value in sales_series),
            result,
            {
                'trend': sales_analysis['trend'],
                'method': sales_analysis['method'],
                'forecast': sales_analysis['forecast']
            }
        )
        consume_quota()
        return json_success(
            result=result,
            sales_series=sales_analysis['series'],
            forecast=sales_analysis['forecast'],
            lower_bounds=sales_analysis['lower_bounds'],
            upper_bounds=sales_analysis['upper_bounds'],
            trend=sales_analysis['trend'],
            method=sales_analysis['method'],
            growth_rate=sales_analysis['growth_rate'],
            recommendations=sales_analysis['recommendations']
        )
    except Exception as exc:
        return json_error(str(exc), 500)
