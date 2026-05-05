from database import db
from datetime import datetime


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    cds_api_key = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    requests = db.relationship('Request', backref='user', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'has_api_key': bool(self.cds_api_key),
            'created_at': self.created_at.isoformat()
        }


class Request(db.Model):
    __tablename__ = 'requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    place_name = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.String(20), nullable=False)
    end_date = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Pending, Processing, Completed, Failed
    nc_path = db.Column(db.String(500), nullable=True)
    csv_path = db.Column(db.String(500), nullable=True)
    summary_csv_path = db.Column(db.String(500), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'place_name': self.place_name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'status': self.status,
            'has_nc': bool(self.nc_path),
            'has_csv': bool(self.csv_path),
            'has_summary': bool(self.summary_csv_path),
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat()
        }