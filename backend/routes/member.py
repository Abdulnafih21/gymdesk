import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from database import get_db
from utils.decorators import member_required
from utils.qr_code import generate_member_qr
from datetime import date, timedelta, datetime
from werkzeug.utils import secure_filename

member_bp = Blueprint('member', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_member(db):
    """Get the member record for the current user."""
    return db.execute('SELECT * FROM members WHERE user_id = ?', (current_user.id,)).fetchone()


def _get_active_subscription(db, member_id):
    """Get the current active subscription for a member, auto-expire if needed."""
    # First, auto-expire any subscriptions past their end_date
    db.execute("""
        UPDATE member_subscriptions SET status = 'expired'
        WHERE member_id = ? AND status = 'active' AND end_date < date('now')
    """, (member_id,))
    db.commit()

    return db.execute('''
        SELECT ms.*, mp.name as plan_name, mp.duration_days, mp.plan_type
        FROM member_subscriptions ms
        JOIN membership_plans mp ON ms.plan_id = mp.id
        WHERE ms.member_id = ? AND ms.status = 'active' AND ms.end_date >= date('now')
        ORDER BY ms.end_date DESC LIMIT 1
    ''', (member_id,)).fetchone()


def _check_reminders(db, member_id, user_id):
    """Create renewal reminders if subscription is about to expire."""
    sub = db.execute('''
        SELECT ms.*, mp.name as plan_name
        FROM member_subscriptions ms
        JOIN membership_plans mp ON ms.plan_id = mp.id
        WHERE ms.member_id = ? AND ms.status = 'active' AND ms.end_date >= date('now')
        ORDER BY ms.end_date DESC LIMIT 1
    ''', (member_id,)).fetchone()
    if not sub:
        return

    end = datetime.strptime(sub['end_date'], '%Y-%m-%d').date() if isinstance(sub['end_date'], str) else sub['end_date']
    remaining = (end - date.today()).days

    if remaining <= 3 and remaining >= 0:
        # Check if we already sent a reminder today
        existing = db.execute('''
            SELECT id FROM notifications
            WHERE user_id = ? AND title = 'Membership Expiring Soon'
            AND date(created_at) = date('now')
        ''', (user_id,)).fetchone()
        if not existing:
            db.execute('''
                INSERT INTO notifications (user_id, title, message, link)
                VALUES (?, 'Membership Expiring Soon',
                        ?, '/member/payments')
            ''', (user_id, f'Your {sub["plan_name"]} plan expires in {remaining} day{"s" if remaining != 1 else ""}. Please renew to continue gym access.'))
            db.commit()


@member_bp.route('/dashboard')
@login_required
@member_required
def dashboard():
    db = get_db()
    member = _get_member(db)
    if not member:
        flash('Member profile not found.', 'error')
        db.close()
        return redirect(url_for('public.landing'))

    gym = db.execute('SELECT * FROM gyms WHERE id = ?', (member['gym_id'],)).fetchone()

    # Active subscription with auto-expire
    active_sub = _get_active_subscription(db, member['id'])

    # Remaining days
    remaining_days = None
    if active_sub:
        end = datetime.strptime(active_sub['end_date'], '%Y-%m-%d').date() if isinstance(active_sub['end_date'], str) else active_sub['end_date']
        remaining_days = (end - date.today()).days

    # Check and create reminders
    _check_reminders(db, member['id'], current_user.id)

    # Check for pending payments
    pending_payments = db.execute('''
        SELECT COUNT(*) as c FROM payments
        WHERE member_id = ? AND status = 'pending'
    ''', (member['id'],)).fetchone()['c']

    # Upcoming classes (booked)
    upcoming_classes = db.execute('''
        SELECT cb.*, c.name as class_name, c.day_of_week, c.start_time, c.end_time,
               u.full_name as trainer_name
        FROM class_bookings cb
        JOIN classes c ON cb.class_id = c.id
        LEFT JOIN trainers t ON c.trainer_id = t.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE cb.member_id = ? AND cb.status = 'booked'
        ORDER BY cb.booking_date DESC LIMIT 5
    ''', (member['id'],)).fetchall()

    # Recent attendance
    recent_attendance = db.execute('''
        SELECT * FROM attendance WHERE member_id = ?
        ORDER BY check_in_time DESC LIMIT 10
    ''', (member['id'],)).fetchall()

    # Attendance streak
    attendance_count = db.execute('''
        SELECT COUNT(DISTINCT date(check_in_time)) as days
        FROM attendance WHERE member_id = ? AND check_in_time >= date('now', '-30 days')
    ''', (member['id'],)).fetchone()['days']

    # Workout plans
    workout_plans = db.execute('''
        SELECT wp.*, u.full_name as trainer_name
        FROM workout_plans wp
        JOIN trainers t ON wp.trainer_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE wp.member_id = ?
        ORDER BY wp.created_at DESC LIMIT 3
    ''', (member['id'],)).fetchall()

    # Notifications
    notifications = db.execute('''
        SELECT * FROM notifications WHERE user_id = ? AND is_read = 0
        ORDER BY created_at DESC LIMIT 5
    ''', (current_user.id,)).fetchall()

    db.close()

    return render_template('member/dashboard.html',
                           member=member, gym=gym, active_sub=active_sub,
                           remaining_days=remaining_days,
                           pending_payments=pending_payments,
                           upcoming_classes=upcoming_classes,
                           recent_attendance=recent_attendance,
                           attendance_count=attendance_count,
                           workout_plans=workout_plans,
                           notifications=notifications)


@member_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@member_required
def profile():
    db = get_db()
    member = _get_member(db)

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        date_of_birth = request.form.get('date_of_birth', '')
        gender = request.form.get('gender', '')
        emergency_contact = request.form.get('emergency_contact', '').strip()
        emergency_phone = request.form.get('emergency_phone', '').strip()
        blood_group = request.form.get('blood_group', '')
        weight = request.form.get('weight', '')
        height = request.form.get('height', '')
        fitness_goal = request.form.get('fitness_goal', '').strip()

        db.execute('UPDATE users SET full_name = ?, phone = ? WHERE id = ?',
                   (full_name, phone, current_user.id))
        db.execute('''
            UPDATE members SET date_of_birth=?, gender=?, emergency_contact=?,
                               emergency_phone=?, blood_group=?, weight_kg=?,
                               height_cm=?, fitness_goal=?
            WHERE id = ?
        ''', (date_of_birth or None, gender or None,
              emergency_contact or None, emergency_phone or None,
              blood_group or None,
              float(weight) if weight else None,
              float(height) if height else None,
              fitness_goal or None, member['id']))
        db.commit()
        flash('Profile updated successfully!', 'success')
        member = _get_member(db)

    user = db.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
    gym = db.execute('SELECT * FROM gyms WHERE id = ?', (member['gym_id'],)).fetchone()
    db.close()

    return render_template('member/profile.html', member=member, user=user, gym=gym)


@member_bp.route('/classes')
@login_required
@member_required
def classes():
    db = get_db()
    member = _get_member(db)

    classes_list = db.execute('''
        SELECT c.*, u.full_name as trainer_name,
               (SELECT COUNT(*) FROM class_bookings cb WHERE cb.class_id = c.id AND cb.status = 'booked') as booked_count
        FROM classes c
        LEFT JOIN trainers t ON c.trainer_id = t.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE c.gym_id = ? AND c.is_active = 1
        ORDER BY c.day_of_week, c.start_time
    ''', (member['gym_id'],)).fetchall()

    my_bookings = db.execute('''
        SELECT class_id FROM class_bookings
        WHERE member_id = ? AND status = 'booked'
    ''', (member['id'],)).fetchall()
    booked_ids = {b['class_id'] for b in my_bookings}

    db.close()

    return render_template('member/classes.html', classes=classes_list,
                           member=member, booked_ids=booked_ids)


@member_bp.route('/classes/<int:class_id>/book', methods=['POST'])
@login_required
@member_required
def book_class(class_id):
    db = get_db()
    member = _get_member(db)

    cls = db.execute('SELECT * FROM classes WHERE id = ?', (class_id,)).fetchone()
    if not cls or cls['gym_id'] != member['gym_id']:
        flash('Class not found.', 'error')
        db.close()
        return redirect(url_for('member.classes'))

    booked = db.execute('SELECT COUNT(*) as c FROM class_bookings WHERE class_id = ? AND status = "booked"',
                        (class_id,)).fetchone()['c']
    if booked >= cls['capacity']:
        flash('This class is full.', 'warning')
        db.close()
        return redirect(url_for('member.classes'))

    existing = db.execute('''
        SELECT id FROM class_bookings
        WHERE class_id = ? AND member_id = ? AND status = 'booked'
    ''', (class_id, member['id'])).fetchone()
    if existing:
        flash('You are already booked for this class.', 'info')
        db.close()
        return redirect(url_for('member.classes'))

    db.execute('''
        INSERT INTO class_bookings (class_id, member_id, booking_date, status)
        VALUES (?, ?, date('now'), 'booked')
    ''', (class_id, member['id']))
    db.commit()
    db.close()
    flash(f'Successfully booked {cls["name"]}!', 'success')
    return redirect(url_for('member.classes'))


@member_bp.route('/classes/<int:booking_id>/cancel', methods=['POST'])
@login_required
@member_required
def cancel_booking(booking_id):
    db = get_db()
    db.execute("UPDATE class_bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    db.commit()
    db.close()
    flash('Booking cancelled.', 'info')
    return redirect(url_for('member.classes'))


@member_bp.route('/workouts')
@login_required
@member_required
def workouts():
    db = get_db()
    member = _get_member(db)

    plans = db.execute('''
        SELECT wp.*, u.full_name as trainer_name
        FROM workout_plans wp
        JOIN trainers t ON wp.trainer_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE wp.member_id = ?
        ORDER BY wp.created_at DESC
    ''', (member['id'],)).fetchall()

    plans_with_exercises = []
    for plan in plans:
        exercises = db.execute('''
            SELECT * FROM exercises WHERE workout_plan_id = ?
            ORDER BY day_of_week, id
        ''', (plan['id'],)).fetchall()
        plans_with_exercises.append({'plan': plan, 'exercises': exercises})

    db.close()
    return render_template('member/workouts.html', plans=plans_with_exercises, member=member)


# ── Payment Submission ────────────────────────────────────
@member_bp.route('/payments')
@login_required
@member_required
def payments():
    db = get_db()
    member = _get_member(db)

    payments_list = db.execute('''
        SELECT p.*, mp.name as plan_name
        FROM payments p
        LEFT JOIN membership_plans mp ON p.plan_id = mp.id
        WHERE p.member_id = ?
        ORDER BY p.created_at DESC
    ''', (member['id'],)).fetchall()

    subscriptions = db.execute('''
        SELECT ms.*, mp.name as plan_name, mp.duration_days
        FROM member_subscriptions ms
        JOIN membership_plans mp ON ms.plan_id = mp.id
        WHERE ms.member_id = ?
        ORDER BY ms.created_at DESC
    ''', (member['id'],)).fetchall()

    # Available plans for the member's gym
    plans = db.execute('''
        SELECT * FROM membership_plans
        WHERE gym_id = ? AND is_active = 1
        ORDER BY price ASC
    ''', (member['gym_id'],)).fetchall()

    active_sub = _get_active_subscription(db, member['id'])

    db.close()
    return render_template('member/payments.html', payments=payments_list,
                           subscriptions=subscriptions, member=member,
                           plans=plans, active_sub=active_sub)


@member_bp.route('/payments/submit', methods=['POST'])
@login_required
@member_required
def submit_payment():
    db = get_db()
    member = _get_member(db)

    plan_id = request.form.get('plan_id', '')
    amount = request.form.get('amount', '')
    transaction_id = request.form.get('transaction_id', '').strip()
    transaction_date = request.form.get('transaction_date', '')
    payment_method = request.form.get('payment_method', 'upi')

    if not plan_id or not amount or not transaction_id:
        flash('Please fill all required fields.', 'error')
        db.close()
        return redirect(url_for('member.payments'))

    # Handle screenshot upload
    screenshot_path = None
    if 'screenshot' in request.files:
        file = request.files['screenshot']
        if file and file.filename and _allowed_file(file.filename):
            filename = secure_filename(f"pay_{member['id']}_{int(datetime.now().timestamp())}_{file.filename}")
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'payments')
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))
            screenshot_path = f"payments/{filename}"

    # Get plan info
    plan = db.execute('SELECT * FROM membership_plans WHERE id = ?', (plan_id,)).fetchone()
    payment_type = plan['plan_type'] if plan else 'subscription'

    db.execute('''
        INSERT INTO payments (member_id, gym_id, plan_id, amount, payment_type,
                              payment_method, reference_id, transaction_screenshot,
                              payment_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    ''', (member['id'], member['gym_id'], int(plan_id), float(amount),
          payment_type, payment_method, transaction_id, screenshot_path,
          transaction_date or date.today().isoformat()))

    db.commit()
    db.close()
    flash('Payment submitted! It will be verified by the admin.', 'success')
    return redirect(url_for('member.payments'))


# ── QR Check-in (Conditional) ─────────────────────────────
@member_bp.route('/qr')
@login_required
@member_required
def qr_checkin():
    db = get_db()
    member = _get_member(db)
    gym = db.execute('SELECT * FROM gyms WHERE id = ?', (member['gym_id'],)).fetchone()

    active_sub = _get_active_subscription(db, member['id'])

    # Check for pending payments
    pending_payment = db.execute('''
        SELECT COUNT(*) as c FROM payments
        WHERE member_id = ? AND status = 'pending'
    ''', (member['id'],)).fetchone()['c']

    db.close()

    qr_image = None
    if active_sub:
        qr_image = generate_member_qr(member['id'], member['gym_id'])

    return render_template('member/qr_checkin.html', member=member,
                           gym=gym, qr_image=qr_image,
                           active_sub=active_sub,
                           pending_payment=pending_payment)


# ── Slot Booking (Calendar Based) ─────────────────────────
@member_bp.route('/slots')
@login_required
@member_required
def slots():
    db = get_db()
    member = _get_member(db)

    # Get available sessions for this gym
    sessions = db.execute('''
        SELECT * FROM slot_sessions WHERE gym_id = ? AND is_active = 1
        ORDER BY start_time
    ''', (member['gym_id'],)).fetchall()

    # Get member's assigned trainer
    assigned = db.execute('''
        SELECT mt.trainer_id, u.full_name as trainer_name, t.specialization
        FROM member_trainer mt
        JOIN trainers t ON mt.trainer_id = t.id
        JOIN users u ON t.user_id = u.id
        WHERE mt.member_id = ?
    ''', (member['id'],)).fetchone()

    # Get all approved trainers in the gym for change-trainer dropdown
    gym_trainers = db.execute('''
        SELECT t.id, u.full_name, t.specialization, t.max_capacity,
               (SELECT COUNT(*) FROM member_trainer mt2 WHERE mt2.trainer_id = t.id) as current_members
        FROM trainers t JOIN users u ON t.user_id = u.id
        WHERE t.gym_id = ? AND t.is_approved = 1
        ORDER BY u.full_name
    ''', (member['gym_id'],)).fetchall()

    # Upcoming bookings
    bookings = db.execute('''
        SELECT sb.*, ss.name as session_name, ss.start_time, ss.end_time,
               u.full_name as trainer_name
        FROM slot_bookings sb
        JOIN slot_sessions ss ON sb.session_id = ss.id
        LEFT JOIN trainers t ON sb.trainer_id = t.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE sb.member_id = ? AND sb.booking_date >= date('now') AND sb.status = 'booked'
        ORDER BY sb.booking_date, ss.start_time
    ''', (member['id'],)).fetchall()

    # Past bookings (last 10)
    past_bookings = db.execute('''
        SELECT sb.*, ss.name as session_name, ss.start_time, ss.end_time,
               u.full_name as trainer_name
        FROM slot_bookings sb
        JOIN slot_sessions ss ON sb.session_id = ss.id
        LEFT JOIN trainers t ON sb.trainer_id = t.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE sb.member_id = ? AND sb.booking_date < date('now')
        ORDER BY sb.booking_date DESC LIMIT 10
    ''', (member['id'],)).fetchall()

    db.close()
    return render_template('member/slots.html', member=member, sessions=sessions,
                           assigned_trainer=assigned, gym_trainers=gym_trainers,
                           bookings=bookings, past_bookings=past_bookings)


@member_bp.route('/slots/book', methods=['POST'])
@login_required
@member_required
def book_slots():
    db = get_db()
    member = _get_member(db)

    session_id = request.form.get('session_id', '')
    dates_str = request.form.get('dates', '')  # comma-separated dates

    if not session_id or not dates_str:
        flash('Please select a session and at least one date.', 'error')
        db.close()
        return redirect(url_for('member.slots'))

    session = db.execute('SELECT * FROM slot_sessions WHERE id = ? AND gym_id = ?',
                         (int(session_id), member['gym_id'])).fetchone()
    if not session:
        flash('Invalid session.', 'error')
        db.close()
        return redirect(url_for('member.slots'))

    # Get assigned trainer
    assigned = db.execute('SELECT trainer_id FROM member_trainer WHERE member_id = ?',
                          (member['id'],)).fetchone()
    trainer_id = assigned['trainer_id'] if assigned else None

    # Check trainer availability for this session
    if trainer_id:
        trainer_available = db.execute('''
            SELECT id FROM trainer_sessions
            WHERE trainer_id = ? AND session_id = ?
        ''', (trainer_id, int(session_id))).fetchone()

        if not trainer_available:
            # Get trainer name and available sessions
            trainer_info = db.execute('''
                SELECT u.full_name FROM trainers t JOIN users u ON t.user_id = u.id WHERE t.id = ?
            ''', (trainer_id,)).fetchone()
            avail = db.execute('''
                SELECT ss.name FROM trainer_sessions ts
                JOIN slot_sessions ss ON ts.session_id = ss.id
                WHERE ts.trainer_id = ?
            ''', (trainer_id,)).fetchall()
            avail_names = ', '.join([a['name'] for a in avail]) if avail else 'None'
            flash(f'Your assigned trainer ({trainer_info["full_name"]}) is not available for the {session["name"]} session. '
                  f'Their available sessions: {avail_names}. Please change your session or trainer.', 'warning')
            db.close()
            return redirect(url_for('member.slots'))

    dates = [d.strip() for d in dates_str.split(',') if d.strip()]
    booked_count = 0

    for d in dates:
        # ── 2-slot-per-day limit ──
        daily_bookings = db.execute('''
            SELECT COUNT(*) as c FROM slot_bookings
            WHERE member_id = ? AND booking_date = ? AND status = 'booked'
        ''', (member['id'], d)).fetchone()['c']
        if daily_bookings >= 2:
            flash(f'You already have 2 slots booked on {d}. Maximum 2 sessions per day.', 'warning')
            continue

        # Check capacity
        current = db.execute('''
            SELECT COUNT(*) as c FROM slot_bookings
            WHERE session_id = ? AND booking_date = ? AND status = 'booked'
        ''', (int(session_id), d)).fetchone()['c']

        if current >= session['capacity']:
            flash(f'{session["name"]} session is full on {d}. Choose another session.', 'warning')
            continue

        # Check duplicate
        existing = db.execute('''
            SELECT id FROM slot_bookings
            WHERE member_id = ? AND session_id = ? AND booking_date = ? AND status = 'booked'
        ''', (member['id'], int(session_id), d)).fetchone()
        if existing:
            continue

        db.execute('''
            INSERT INTO slot_bookings (member_id, gym_id, session_id, trainer_id, booking_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (member['id'], member['gym_id'], int(session_id), trainer_id, d))
        booked_count += 1

    if booked_count > 0:
        # Notification
        db.execute('''
            INSERT INTO notifications (user_id, title, message, link)
            VALUES (?, 'Slot Booked ✅', ?, '/member/slots')
        ''', (current_user.id,
              f'{booked_count} slot(s) booked for {session["name"]} session.'))
        db.commit()
        flash(f'Successfully booked {booked_count} slot(s) for {session["name"]}!', 'success')
    else:
        flash('No new slots were booked.', 'info')

    db.close()
    return redirect(url_for('member.slots'))


@member_bp.route('/slots/<int:booking_id>/cancel', methods=['POST'])
@login_required
@member_required
def cancel_slot(booking_id):
    db = get_db()
    db.execute("UPDATE slot_bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    db.commit()
    db.close()
    flash('Slot booking cancelled.', 'info')
    return redirect(url_for('member.slots'))


# ── Change Trainer ────────────────────────────────────────
@member_bp.route('/change-trainer', methods=['POST'])
@login_required
@member_required
def change_trainer():
    db = get_db()
    member = _get_member(db)
    new_trainer_id = request.form.get('trainer_id', '')

    if not new_trainer_id:
        flash('Please select a trainer.', 'error')
        db.close()
        return redirect(url_for('member.slots'))

    trainer = db.execute('''
        SELECT t.*, u.full_name FROM trainers t JOIN users u ON t.user_id = u.id
        WHERE t.id = ? AND t.gym_id = ? AND t.is_approved = 1
    ''', (int(new_trainer_id), member['gym_id'])).fetchone()

    if not trainer:
        flash('Invalid trainer.', 'error')
        db.close()
        return redirect(url_for('member.slots'))

    # Check capacity
    current_count = db.execute('SELECT COUNT(*) as c FROM member_trainer WHERE trainer_id = ?',
                               (int(new_trainer_id),)).fetchone()['c']
    if current_count >= trainer['max_capacity']:
        flash(f'Trainer {trainer["full_name"]} has reached maximum capacity ({trainer["max_capacity"]} members).', 'warning')
        db.close()
        return redirect(url_for('member.slots'))

    # Replace or insert
    existing = db.execute('SELECT id FROM member_trainer WHERE member_id = ?', (member['id'],)).fetchone()
    if existing:
        db.execute('UPDATE member_trainer SET trainer_id = ?, assigned_at = CURRENT_TIMESTAMP WHERE member_id = ?',
                   (int(new_trainer_id), member['id']))
    else:
        db.execute('INSERT INTO member_trainer (member_id, trainer_id) VALUES (?, ?)',
                   (member['id'], int(new_trainer_id)))

    # Notification
    db.execute('''
        INSERT INTO notifications (user_id, title, message, link)
        VALUES (?, 'Trainer Updated', ?, '/member/slots')
    ''', (current_user.id, f'Your trainer has been changed to {trainer["full_name"]}.'))

    db.commit()
    db.close()
    flash(f'Trainer changed to {trainer["full_name"]}!', 'success')
    return redirect(url_for('member.slots'))


# ── Notifications ────────────────────────────────────────
@member_bp.route('/notifications')
@login_required
@member_required
def notifications():
    db = get_db()
    notifs = db.execute('''
        SELECT * FROM notifications WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 50
    ''', (current_user.id,)).fetchall()

    # Mark all as read
    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0',
               (current_user.id,))
    db.commit()
    db.close()
    return render_template('member/notifications.html', notifications=notifs)
