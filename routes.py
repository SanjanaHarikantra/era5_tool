from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import User, Request as DataRequest
from services.era5_service import process_era5_request, convert_nc_to_csv, infer_nc_defaults
import threading
import os
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename

routes_bp = Blueprint('routes', __name__, url_prefix='/api')


@routes_bp.route('/me', methods=['GET'])
@jwt_required()
def get_me():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return jsonify({'user': user.to_dict()}), 200


@routes_bp.route('/save-api-key', methods=['POST'])
@jwt_required()
def save_api_key():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    api_key = data.get('cds_api_key', '').strip()
    if not api_key:
        return jsonify({'error': 'API key is required'}), 400

    user.cds_api_key = api_key
    db.session.commit()

    return jsonify({'message': 'CDS API key saved successfully!'}), 200


@routes_bp.route('/request-data', methods=['POST'])
@jwt_required()
def request_data():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    if not user.cds_api_key:
        return jsonify({'error': 'Please save your CDS API key in Profile first'}), 400

    data = request.get_json()

    # Validate inputs
    place_name = data.get('place_name', '').strip()
    start_date = data.get('start_date', '').strip()
    end_date = data.get('end_date', '').strip()

    try:
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid latitude or longitude'}), 400

    if not place_name or not start_date or not end_date:
        return jsonify({'error': 'All fields are required'}), 400

    if not (-90 <= latitude <= 90):
        return jsonify({'error': 'Latitude must be between -90 and 90'}), 400

    if not (-180 <= longitude <= 180):
        return jsonify({'error': 'Longitude must be between -180 and 180'}), 400

    if start_date >= end_date:
        return jsonify({'error': 'End date must be after start date'}), 400

    variables = data.get('variables') or [
        '100m_u_component_of_wind',
        '100m_v_component_of_wind'
    ]
    if not isinstance(variables, list) or not variables:
        return jsonify({'error': 'At least one ERA5 variable is required'}), 400

    try:
        buffer = float(data.get('buffer', 0.1))
    except (TypeError, ValueError):
        return jsonify({'error': 'Buffer must be a valid number'}), 400

    if buffer <= 0:
        return jsonify({'error': 'Buffer must be greater than 0'}), 400

    # Create request record
    req = DataRequest(
        user_id=user_id,
        place_name=place_name,
        latitude=latitude,
        longitude=longitude,
        start_date=start_date,
        end_date=end_date,
        status='Pending'
    )
    db.session.add(req)
    db.session.commit()

    # Process in background thread
    thread = threading.Thread(
        target=process_era5_request,
        args=(req.id, user.cds_api_key, variables, buffer)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'message': 'Data request submitted successfully! Processing in background.',
        'request_id': req.id
    }), 202


@routes_bp.route('/history', methods=['GET'])
@jwt_required()
def get_history():
    user_id = int(get_jwt_identity())
    requests = DataRequest.query.filter_by(user_id=user_id)\
        .order_by(DataRequest.created_at.desc()).all()
    return jsonify({'requests': [r.to_dict() for r in requests]}), 200


@routes_bp.route('/request-status/<int:request_id>', methods=['GET'])
@jwt_required()
def get_request_status(request_id):
    user_id = int(get_jwt_identity())
    req = DataRequest.query.filter_by(id=request_id, user_id=user_id).first_or_404()
    return jsonify({'request': req.to_dict()}), 200


@routes_bp.route('/download/<int:request_id>/<file_type>', methods=['GET'])
@jwt_required()
def download_file(request_id, file_type):
    user_id = int(get_jwt_identity())
    req = DataRequest.query.filter_by(id=request_id, user_id=user_id).first_or_404()

    file_map = {
        'nc': req.nc_path,
        'csv': req.csv_path,
        'summary': req.summary_csv_path
    }

    file_path = file_map.get(file_type)
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'File not found or not ready yet'}), 404

    return send_file(file_path, as_attachment=True)


@routes_bp.route('/download-files', methods=['GET'])
@jwt_required()
def list_download_files():
    user_id = int(get_jwt_identity())
    include_uploaded = request.args.get('include_uploaded') == '1'
    requests = DataRequest.query.filter_by(user_id=user_id)\
        .order_by(DataRequest.created_at.desc()).all()

    files = []
    for req in requests:
        candidates = [
            ('nc', req.nc_path),
            ('csv', req.csv_path),
            ('summary', req.summary_csv_path),
        ]
        for file_type, file_path in candidates:
            if not file_path or not os.path.exists(file_path):
                continue
            p = Path(file_path)
            files.append({
                'request_id': req.id,
                'file_type': file_type,
                'file_name': p.name,
                'file_path': str(p),
                'place_name': req.place_name,
                'size_bytes': p.stat().st_size,
                'source': 'request',
            })

    if include_uploaded:
        upload_dir = Path('downloads') / f"user_{user_id}" / "uploaded_nc"
        if upload_dir.exists():
            for p in sorted(upload_dir.glob('*'), key=lambda x: x.stat().st_mtime, reverse=True):
                if not p.is_file():
                    continue
                suffix = p.suffix.lower()
                if suffix not in {'.nc', '.csv'}:
                    continue
                files.append({
                    'request_id': None,
                    'file_type': suffix.lstrip('.'),
                    'file_name': p.name,
                    'file_path': str(p),
                    'place_name': 'Uploaded File',
                    'size_bytes': p.stat().st_size,
                    'source': 'uploaded',
                })

    return jsonify({'files': files}), 200


@routes_bp.route('/rename-download/<int:request_id>/<file_type>', methods=['POST'])
@jwt_required()
def rename_download(request_id, file_type):
    user_id = int(get_jwt_identity())
    req = DataRequest.query.filter_by(id=request_id, user_id=user_id).first_or_404()
    payload = request.get_json(silent=True) or {}
    new_name = (payload.get('new_name') or '').strip()

    file_map = {
        'nc': req.nc_path,
        'csv': req.csv_path,
        'summary': req.summary_csv_path,
    }
    file_path = file_map.get(file_type)
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    if not new_name:
        return jsonify({'error': 'New name is required'}), 400

    old_path = Path(file_path)
    safe_name = "".join(ch if (ch.isalnum() or ch in ('-', '_', '.')) else "_" for ch in new_name)
    safe_name = safe_name.strip("._")
    if not safe_name:
        return jsonify({'error': 'Invalid file name'}), 400
    if not safe_name.lower().endswith(old_path.suffix.lower()):
        safe_name = f"{safe_name}{old_path.suffix}"

    new_path = old_path.with_name(safe_name)
    if new_path.exists():
        return jsonify({'error': 'A file with this name already exists'}), 400

    old_path.rename(new_path)

    if file_type == 'nc':
        req.nc_path = str(new_path)
    elif file_type == 'csv':
        req.csv_path = str(new_path)
    elif file_type == 'summary':
        req.summary_csv_path = str(new_path)
    else:
        return jsonify({'error': 'Invalid file type'}), 400
    db.session.commit()

    return jsonify({'message': 'File renamed successfully', 'file_name': new_path.name}), 200


@routes_bp.route('/convert-nc/<int:request_id>', methods=['POST'])
@jwt_required()
def convert_nc(request_id):
    user_id = int(get_jwt_identity())
    req = DataRequest.query.filter_by(id=request_id, user_id=user_id).first_or_404()

    if not req.nc_path or not os.path.exists(req.nc_path):
        return jsonify({'error': 'NetCDF file not found'}), 404

    payload = request.get_json(silent=True) or {}
    custom_name = (payload.get('csv_name') or '').strip()

    nc_path = Path(req.nc_path)
    if custom_name:
        safe_name = "".join(ch if (ch.isalnum() or ch in ('-', '_', '.')) else "_" for ch in custom_name)
        safe_name = safe_name.strip("._")
        if not safe_name:
            return jsonify({'error': 'Invalid CSV file name'}), 400
        if not safe_name.lower().endswith('.csv'):
            safe_name = f"{safe_name}.csv"
        csv_path = nc_path.with_name(safe_name)
    else:
        csv_path = nc_path.with_name(f"{nc_path.stem}_converted.csv")

    try:
        summary = convert_nc_to_csv(
            nc_path=str(nc_path),
            csv_path=str(csv_path),
            place_name=req.place_name,
            latitude=req.latitude,
            longitude=req.longitude,
            start_date=req.start_date,
            end_date=req.end_date,
        )
        summary_path = csv_path.with_name(f"{csv_path.stem}_monthly_summary.csv")
        summary.to_csv(summary_path, index=False)
    except Exception as exc:
        req.error_message = f"CSV conversion failed: {exc}"
        db.session.commit()
        return jsonify({'error': req.error_message}), 500

    req.csv_path = str(csv_path)
    req.summary_csv_path = str(summary_path)
    req.status = 'Completed'
    req.error_message = None
    db.session.commit()

    return jsonify({
        'message': 'NC converted to CSV successfully',
        'csv_file': csv_path.name,
        'summary_file': summary_path.name
    }), 200


@routes_bp.route('/convert-uploaded-nc', methods=['POST'])
@jwt_required()
def convert_uploaded_nc():
    user_id = int(get_jwt_identity())

    uploaded_file = request.files.get('nc_file')
    place_name = 'Uploaded_Location'
    output_name = (request.form.get('output_name') or '').strip()

    if not uploaded_file:
        return jsonify({'error': 'Please choose a .nc file'}), 400
    if not uploaded_file.filename.lower().endswith('.nc'):
        return jsonify({'error': 'Only .nc files are supported'}), 400

    safe_place = "".join(c if c.isalnum() else "_" for c in place_name).strip("_") or "uploaded"
    upload_dir = Path('downloads') / f"user_{user_id}" / "uploaded_nc"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

    filename = secure_filename(uploaded_file.filename)
    base_name = Path(filename).stem
    nc_path = upload_dir / f"{base_name}_{ts}.nc"
    csv_base = "".join(ch if (ch.isalnum() or ch in ('-', '_', '.')) else "_" for ch in output_name).strip("._") if output_name else f"{base_name}_{ts}_converted"
    if csv_base.lower().endswith('.csv'):
        csv_base = csv_base[:-4]
    csv_path = upload_dir / f"{csv_base}.csv"
    summary_path = upload_dir / f"{csv_base}_monthly_summary.csv"

    try:
        uploaded_file.save(str(nc_path))
        defaults = infer_nc_defaults(str(nc_path))
        summary = convert_nc_to_csv(
            nc_path=str(nc_path),
            csv_path=str(csv_path),
            place_name=safe_place,
            latitude=defaults["latitude"],
            longitude=defaults["longitude"],
            start_date=defaults["start_date"],
            end_date=defaults["end_date"],
        )
        summary.to_csv(summary_path, index=False)
    except Exception as exc:
        return jsonify({'error': f'CSV conversion failed: {exc}'}), 500

    return jsonify({
        'message': 'Uploaded NC converted successfully',
        'nc_file': nc_path.name,
        'csv_file': csv_path.name,
        'summary_file': summary_path.name,
        'folder': str(upload_dir)
    }), 200


@routes_bp.route('/download-uploaded/<path:filename>', methods=['GET'])
@jwt_required()
def download_uploaded_file(filename):
    user_id = int(get_jwt_identity())
    upload_dir = Path('downloads') / f"user_{user_id}" / "uploaded_nc"
    file_path = upload_dir / Path(filename).name

    if not file_path.exists() or not file_path.is_file():
        return jsonify({'error': 'File not found'}), 404

    return send_file(str(file_path), as_attachment=True)