from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from database import db, bcrypt
from models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/api')


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    # Validate input
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not name or not email or not password:
        return jsonify({'error': 'Name, email and password are required'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    if '@' not in email:
        return jsonify({'error': 'Invalid email address'}), 400

    # Check if email exists
    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({'error': 'Email already registered'}), 409

    # Hash password and create user
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    user = User(name=name, email=email, password=hashed_pw)
    db.session.add(user)
    db.session.commit()

    return jsonify({'message': 'Registration successful! Please login.'}), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password, password):
        return jsonify({'error': 'Invalid email or password'}), 401

    token = create_access_token(identity=str(user.id))

    return jsonify({
        'token': token,
        'user': user.to_dict(),
        'message': f'Welcome back, {user.name}!'
    }), 200