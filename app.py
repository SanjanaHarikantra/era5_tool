from flask import Flask, jsonify, send_file, request as flask_request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from flask_cors import CORS
from database import db, bcrypt, jwt
import os

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = 'era5-wind-tool-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'era5-jwt-secret-2024'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False

db.init_app(app)
bcrypt.init_app(app)
jwt.init_app(app)

# Import models and routes AFTER db init
from models import User, Request as DataRequest
from auth import auth_bp
from routes import routes_bp

app.register_blueprint(auth_bp)
app.register_blueprint(routes_bp)

# Serve frontend pages
from flask import render_template

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html')

@app.route('/profile')
def profile_page():
    return render_template('profile.html')

@app.route('/request-page')
def request_page():
    return render_template('request.html')

@app.route('/history')
def history_page():
    return render_template('history.html')

@app.route('/convert-csv')
def convert_csv_page():
    return render_template('convert_csv.html')

if __name__ == '__main__':
    with app.app_context():
        os.makedirs('downloads', exist_ok=True)
        db.create_all()
        print("✅ Database initialized")
    app.run(debug=True, port=5000)