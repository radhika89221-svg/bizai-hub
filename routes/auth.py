from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db, limiter
from models import HistoryEntry, User


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per hour')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Welcome back.', 'success')
            next_url = request.args.get('next')
            return redirect(next_url or url_for('auth.dashboard'))

        flash('Invalid email or password.', 'error')

    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per hour')
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not name or not email or not password:
            flash('Name, email, and password are required.', 'error')
        elif password != confirm_password:
            flash('Passwords do not match.', 'error')
        elif len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
        elif User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Account created successfully.', 'success')
            return redirect(url_for('auth.dashboard'))

    return render_template('register.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('pages.home'))


@auth_bp.route('/dashboard')
@login_required
def dashboard():
    current_user.refresh_daily_quota()
    db.session.commit()
    recent_history = (
        HistoryEntry.query
        .filter_by(user_id=current_user.id)
        .order_by(HistoryEntry.id.desc())
        .limit(8)
        .all()
    )
    return render_template('dashboard.html', recent_history=recent_history)
