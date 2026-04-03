from datetime import date

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(20), nullable=False, default='free')
    daily_quota = db.Column(db.Integer, nullable=False, default=20)
    daily_used = db.Column(db.Integer, nullable=False, default=0)
    quota_reset_on = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

    history_entries = db.relationship(
        'HistoryEntry',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def refresh_daily_quota(self):
        today = date.today()
        if self.quota_reset_on != today:
            self.daily_used = 0
            self.quota_reset_on = today
            self.daily_quota = 500 if self.plan == 'paid' else 20

    def quota_remaining(self):
        self.refresh_daily_quota()
        return max(self.daily_quota - self.daily_used, 0)


class HistoryEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    tool = db.Column(db.String(80), nullable=False, index=True)
    input_text = db.Column(db.Text, nullable=False)
    output_text = db.Column(db.Text, nullable=True)
    meta_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


class ImageJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    prompt = db.Column(db.Text, nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='queued', index=True)
    progress_pct = db.Column(db.Integer, nullable=False, default=0)
    status_message = db.Column(db.String(255), nullable=True)
    image_url = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(80), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False
    )
