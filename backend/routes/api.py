from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from database import get_db
from utils.qr_code import parse_qr_data
from datetime import datetime

api_bp = Blueprint('api', __name__)


@api_bp.route('/check-in', methods=['POST'])
@login_required
def check_in():
    """Process QR code check-in."""
    data = request.get_json()
    qr_data = data.get('qr_data', '')

    parsed = parse_qr_data(qr_data)
    if not parsed:
        return jsonify({'success': False, 'message': 'Invalid QR code'}), 400

    db = get_db()
    member = db.execute('SELECT * FROM members WHERE id = ?', (parsed['member_id'],)).fetchone()
    if not member:
        db.close()
        return jsonify({'success': False, 'message': 'Member not found'}), 404

    if member['gym_id'] != parsed['gym_id']:
        db.close()
        return jsonify({'success': False, 'message': 'Member does not belong to this gym'}), 403

    # Check if already checked in today without checkout
    existing = db.execute('''
        SELECT id FROM attendance
        WHERE member_id = ? AND gym_id = ? AND date(check_in_time) = date('now') AND check_out_time IS NULL
    ''', (parsed['member_id'], parsed['gym_id'])).fetchone()

    if existing:
        # Check out
        db.execute('UPDATE attendance SET check_out_time = CURRENT_TIMESTAMP WHERE id = ?', (existing['id'],))
        db.commit()

        user = db.execute('SELECT full_name FROM users WHERE id = ?', (member['user_id'],)).fetchone()
        db.close()
        return jsonify({
            'success': True,
            'action': 'checkout',
            'message': f'{user["full_name"]} checked out successfully!',
            'member_name': user['full_name']
        })
    else:
        # Check in
        db.execute('''
            INSERT INTO attendance (member_id, gym_id, check_in_method)
            VALUES (?, ?, 'qr_code')
        ''', (parsed['member_id'], parsed['gym_id']))
        db.commit()

        user = db.execute('SELECT full_name FROM users WHERE id = ?', (member['user_id'],)).fetchone()
        db.close()
        return jsonify({
            'success': True,
            'action': 'checkin',
            'message': f'{user["full_name"]} checked in successfully!',
            'member_name': user['full_name']
        })


@api_bp.route('/stats')
@login_required
def stats():
    """Return dashboard statistics as JSON."""
    db = get_db()

    data = {
        'total_gyms': db.execute('SELECT COUNT(*) as c FROM gyms WHERE is_approved = 1').fetchone()['c'],
        'total_members': db.execute('SELECT COUNT(*) as c FROM members').fetchone()['c'],
        'total_trainers': db.execute('SELECT COUNT(*) as c FROM trainers WHERE is_approved = 1').fetchone()['c'],
        'total_classes': db.execute('SELECT COUNT(*) as c FROM classes WHERE is_active = 1').fetchone()['c'],
    }

    db.close()
    return jsonify(data)


@api_bp.route('/notifications')
@login_required
def notifications():
    """Get unread notifications for current user."""
    db = get_db()
    notifs = db.execute('''
        SELECT * FROM notifications WHERE user_id = ? AND is_read = 0
        ORDER BY created_at DESC LIMIT 20
    ''', (current_user.id,)).fetchall()
    db.close()

    return jsonify([{
        'id': n['id'],
        'title': n['title'],
        'message': n['message'],
        'link': n['link'],
        'created_at': n['created_at']
    } for n in notifs])


@api_bp.route('/notifications/read', methods=['POST'])
@login_required
def mark_read():
    """Mark notification(s) as read."""
    data = request.get_json()
    notification_id = data.get('id')

    db = get_db()
    if notification_id:
        db.execute('UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
                   (notification_id, current_user.id))
    else:
        # Mark all as read
        db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (current_user.id,))
    db.commit()
    db.close()

    return jsonify({'success': True})
