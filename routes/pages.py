from flask import Blueprint, render_template
from flask_login import login_required


pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def home():
    return render_template('index.html')


@pages_bp.route('/getting-started')
def getting_started():
    return render_template('getting_started.html')


@pages_bp.route('/faq')
def faq():
    return render_template('faq.html')


@pages_bp.route('/content-writer')
@login_required
def content_writer():
    return render_template('content_writer.html')


@pages_bp.route('/chatbot')
@login_required
def chatbot():
    return render_template('chatbot.html')


@pages_bp.route('/sentiment')
@login_required
def sentiment():
    return render_template('sentiment.html')


@pages_bp.route('/image-generator')
@login_required
def image_generator():
    return render_template('image_generator.html')


@pages_bp.route('/audio-tools')
@login_required
def audio_tools():
    return render_template('audio_tools.html')


@pages_bp.route('/sales-predictor')
@login_required
def sales_predictor():
    return render_template('sales_predictor.html')
