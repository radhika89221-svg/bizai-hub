from flask import Blueprint, render_template


pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def home():
    return render_template('index.html')


@pages_bp.route('/content-writer')
def content_writer():
    return render_template('content_writer.html')


@pages_bp.route('/chatbot')
def chatbot():
    return render_template('chatbot.html')


@pages_bp.route('/sentiment')
def sentiment():
    return render_template('sentiment.html')


@pages_bp.route('/image-generator')
def image_generator():
    return render_template('image_generator.html')


@pages_bp.route('/audio-tools')
def audio_tools():
    return render_template('audio_tools.html')


@pages_bp.route('/sales-predictor')
def sales_predictor():
    return render_template('sales_predictor.html')
