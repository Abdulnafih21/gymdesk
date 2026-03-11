from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
from utils.decorators import gym_admin_required

admin_bp = Blueprint('admin', __name__)


def _get_admin_gym(db):
    """Get the gym owned by the current admin user."""
    if current_user.role == 'system_admin':
        return None  # System admin sees all
    gym = db.execute('SELECT * FROM gyms WHERE owner_id = ?', (current_user.id,)).fetchone()
    return gym


@admin_bp.route('/dashboard')
@login_required
@gym_admin_required
def dashboard():
    db = get_db()
    gym = _get_admin_gym(db)

    if current_user.role == 'system_admin':
        # System admin sees global stats
        stats = {
            'total_gyms': db.execute('SELECT COUNT(*) as c FROM gyms').fetchone()['c'],
            'total_members': db.execute('SELECT COUNT(*) as c FROM members').fetchone()['c'],
            'total_trainers': db.execute('SELECT COUNT(*) as c FROM trainers').fetchone()['c'],
            'total_revenue': db.execute('SELECT COALESCE(SUM(amount),0) as c FROM payments WHERE status="completed"').fetchone()['c'],
            'pending_trainers': db.execute('SELECT COUNT(*) as c FROM trainers WHERE is_approved = 0').fetchone()['c'],
            'active_classes': db.execute('SELECT COUNT(*) as c FROM classes WHERE is_active = 1').fetchone()['c'],
        }
        recent_members = db.execute('''
            SELECT u.full_name, u.email, g.name as gym_name, m.joined_at
            FROM members m JOIN users u ON m.user_id = u.id JOIN gyms g ON m.gym_id = g.id
            ORDER BY m.joined_at DESC LIMIT 10
        ''').fetchall()
        recent_payments = db.execute('''
            SELECT p.*, u.full_name as member_name, g.name as gym_name
            FROM payments p
            JOIN members m ON p.member_id = m.id
            JOIN users u ON m.user_id = u.id
            JOIN gyms g ON p.gym_id = g.id
            ORDER BY p.created_at DESC LIMIT 10
        ''').fetchall()
        gym_name = 'System Administration'
    else:
        if not gym:
            flash('No gym found for your account.', 'error')
            db.close()
            return redirect(url_for('public.landing'))

        stats = {
            'total_members': db.execute('SELECT COUNT(*) as c FROM members WHERE gym_id = ?', (gym['id'],)).fetchone()['c'],
            'total_trainers': db.execute('SELECT COUNT(*) as c FROM trainers WHERE gym_id = ? AND is_approved = 1', (gym['id'],)).fetchone()['c'],
            'pending_trainers': db.execute('SELECT COUNT(*) as c FROM trainers WHERE gym_id = ? AND is_approved = 0', (gym['id'],)).fetchone()['c'],
            'active_plans': db.execute('SELECT COUNT(*) as c FROM membership_plans WHERE gym_id = ? AND is_active = 1', (gym['id'],)).fetchone()['c'],
            'total_revenue': db.execute('SELECT COALESCE(SUM(amount),0) as c FROM payments WHERE gym_id = ? AND status="completed"', (gym['id'],)).fetchone()['c'],
            'active_classes': db.execute('SELECT COUNT(*) as c FROM classes WHERE gym_id = ? AND is_active = 1', (gym['id'],)).fetchone()['c'],
            'todays_checkins': db.execute("SELECT COUNT(*) as c FROM attendance WHERE gym_id = ? AND date(check_in_time) = date('now')", (gym['id'],)).fetchone()['c'],
            'active_subscriptions': db.execute('''
                SELECT COUNT(*) as c FROM member_subscriptions ms
                JOIN members m ON ms.member_id = m.id
                WHERE m.gym_id = ? AND ms.status = 'active' AND ms.end_date >= date('now')
            ''', (gym['id'],)).fetchone()['c'],
        }
        recent_members = db.execute('''
            SELECT u.full_name, u.email, m.joined_at, m.membership_status
            FROM members m JOIN users u ON m.user_id = u.id
            WHERE m.gym_id = ? ORDER BY m.joined_at DESC LIMIT 10
        ''', (gym['id'],)).fetchall()
        recent_payments = db.execute('''
            SELECT p.*, u.full_name as member_name
            FROM payments p
            JOIN members m ON p.member_id = m.id
            JOIN users u ON m.user_id = u.id
            WHERE p.gym_id = ? ORDER BY p.created_at DESC LIMIT 10
        ''', (gym['id'],)).fetchall()
        gym_name = gym['name']

    # Monthly revenue data for chart (last 6 months)
    monthly_revenue = db.execute('''
        SELECT strftime('%Y-%m', payment_date) as month, SUM(amount) as total
        FROM payments WHERE status = 'completed'
        ''' + (' AND gym_id = ?' if gym else '') + '''
        GROUP BY month ORDER BY month DESC LIMIT 6
    ''', (gym['id'],) if gym else ()).fetchall()
    monthly_revenue = list(reversed(monthly_revenue))

    db.close()

    return render_template('admin/dashboard.html',
                           stats=stats, gym=gym, gym_name=gym_name,
                           recent_members=recent_members,
                           recent_payments=recent_payments,
                           monthly_revenue=monthly_revenue)


@admin_bp.route('/members')
@login_required
@gym_admin_required
def members():
    db = get_db()
    gym = _get_admin_gym(db)
    search = request.args.get('search', '').strip()

    query = '''
        SELECT m.*, u.full_name, u.email, u.phone, u.created_at as user_created
        FROM members m JOIN users u ON m.user_id = u.id
    '''
    params = []
    if gym:
        query += ' WHERE m.gym_id = ?'
        params.append(gym['id'])
    if search:
        query += ' AND ' if gym else ' WHERE '
        query += "(u.full_name LIKE ? OR u.email LIKE ? OR u.phone LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    query += ' ORDER BY m.joined_at DESC'

    members_list = db.execute(query, params).fetchall()
    db.close()

    return render_template('admin/members.html', members=members_list,
                           gym=gym, search=search)


@admin_bp.route('/trainers')
@login_required
@gym_admin_required
def trainers():
    db = get_db()
    gym = _get_admin_gym(db)

    query = '''
        SELECT t.*, u.full_name, u.email, u.phone
        FROM trainers t JOIN users u ON t.user_id = u.id
    '''
    params = []
    if gym:
        query += ' WHERE t.gym_id = ?'
        params.append(gym['id'])
    query += ' ORDER BY t.is_approved ASC, t.created_at DESC'

    trainers_list = db.execute(query, params).fetchall()
    db.close()

    return render_template('admin/trainers.html', trainers=trainers_list, gym=gym)


@admin_bp.route('/trainers/<int:trainer_id>/approve', methods=['POST'])
@login_required
@gym_admin_required
def approve_trainer(trainer_id):
    db = get_db()
    gym = _get_admin_gym(db)

    trainer = db.execute('SELECT * FROM trainers WHERE id = ?', (trainer_id,)).fetchone()
    if not trainer:
        flash('Trainer not found.', 'error')
        db.close()
        return redirect(url_for('admin.trainers'))

    if gym and trainer['gym_id'] != gym['id']:
        flash('Unauthorized action.', 'error')
        db.close()
        return redirect(url_for('admin.trainers'))

    db.execute('UPDATE trainers SET is_approved = 1, approved_by = ? WHERE id = ?',
               (current_user.id, trainer_id))

    # Create notification for trainer
    db.execute('''
        INSERT INTO notifications (user_id, title, message, link)
        VALUES (?, 'Trainer Approved', 'Your trainer registration has been approved! You can now access your dashboard.', '/trainer/dashboard')
    ''', (trainer['user_id'],))

    db.commit()
    db.close()
    flash('Trainer approved successfully!', 'success')
    return redirect(url_for('admin.trainers'))


@admin_bp.route('/trainers/<int:trainer_id>/reject', methods=['POST'])
@login_required
@gym_admin_required
def reject_trainer(trainer_id):
    db = get_db()
    gym = _get_admin_gym(db)

    trainer = db.execute('SELECT * FROM trainers WHERE id = ?', (trainer_id,)).fetchone()
    if not trainer:
        flash('Trainer not found.', 'error')
        db.close()
        return redirect(url_for('admin.trainers'))

    if gym and trainer['gym_id'] != gym['id']:
        flash('Unauthorized action.', 'error')
        db.close()
        return redirect(url_for('admin.trainers'))

    # Delete trainer record and user
    user_id = trainer['user_id']
    db.execute('DELETE FROM trainers WHERE id = ?', (trainer_id,))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    db.close()
    flash('Trainer rejected and removed.', 'info')
    return redirect(url_for('admin.trainers'))


@admin_bp.route('/plans')
@login_required
@gym_admin_required
def plans():
    db = get_db()
    gym = _get_admin_gym(db)

    if gym:
        plans_list = db.execute('SELECT * FROM membership_plans WHERE gym_id = ? ORDER BY created_at DESC',
                                (gym['id'],)).fetchall()
    else:
        plans_list = db.execute('''
            SELECT mp.*, g.name as gym_name FROM membership_plans mp
            JOIN gyms g ON mp.gym_id = g.id ORDER BY mp.created_at DESC
        ''').fetchall()

    db.close()
    return render_template('admin/plans.html', plans=plans_list, gym=gym)


@admin_bp.route('/plans/add', methods=['POST'])
@login_required
@gym_admin_required
def add_plan():
    db = get_db()
    gym = _get_admin_gym(db)
    if not gym:
        flash('No gym found.', 'error')
        db.close()
        return redirect(url_for('admin.plans'))

    name = request.form.get('name', '').strip()
    duration_days = request.form.get('duration_days', '30')
    price = request.form.get('price', '0')
    description = request.form.get('description', '').strip()

    if not name:
        flash('Plan name is required.', 'error')
        db.close()
        return redirect(url_for('admin.plans'))

    db.execute('''
        INSERT INTO membership_plans (gym_id, name, duration_days, price, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (gym['id'], name, int(duration_days), float(price), description))
    db.commit()
    db.close()
    flash('Plan created successfully!', 'success')
    return redirect(url_for('admin.plans'))


@admin_bp.route('/plans/<int:plan_id>/toggle', methods=['POST'])
@login_required
@gym_admin_required
def toggle_plan(plan_id):
    db = get_db()
    db.execute('UPDATE membership_plans SET is_active = NOT is_active WHERE id = ?', (plan_id,))
    db.commit()
    db.close()
    flash('Plan status updated.', 'success')
    return redirect(url_for('admin.plans'))


@admin_bp.route('/plans/<int:plan_id>/edit', methods=['POST'])
@login_required
@gym_admin_required
def edit_plan(plan_id):
    db = get_db()
    name = request.form.get('name', '').strip()
    duration_days = request.form.get('duration_days', '30')
    price = request.form.get('price', '0')
    description = request.form.get('description', '').strip()
    plan_type = request.form.get('plan_type', 'monthly')

    if not name:
        flash('Plan name is required.', 'error')
        db.close()
        return redirect(url_for('admin.plans'))

    db.execute('''
        UPDATE membership_plans SET name=?, duration_days=?, price=?, description=?, plan_type=?
        WHERE id=?
    ''', (name, int(duration_days), float(price), description, plan_type, plan_id))
    db.commit()
    db.close()
    flash('Plan updated!', 'success')
    return redirect(url_for('admin.plans'))


# ── Session Slot Management ────────────────────────────────
@admin_bp.route('/sessions', methods=['GET', 'POST'])
@login_required
@gym_admin_required
def sessions():
    db = get_db()
    gym = _get_admin_gym(db)
    if not gym:
        flash('No gym found.', 'error')
        db.close()
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        start_time = request.form.get('start_time', '')
        end_time = request.form.get('end_time', '')
        capacity = request.form.get('capacity', '40')

        if not name or not start_time or not end_time:
            flash('Session name, start time and end time are required.', 'error')
        else:
            db.execute('''
                INSERT INTO slot_sessions (gym_id, name, start_time, end_time, capacity)
                VALUES (?, ?, ?, ?, ?)
            ''', (gym['id'], name, start_time, end_time, int(capacity)))
            db.commit()
            flash('Session slot created!', 'success')

    sessions_list = db.execute('''
        SELECT ss.*,
               (SELECT COUNT(*) FROM slot_bookings sb
                WHERE sb.session_id = ss.id AND sb.booking_date >= date('now') AND sb.status = 'booked') as upcoming_bookings
        FROM slot_sessions ss WHERE ss.gym_id = ?
        ORDER BY ss.start_time
    ''', (gym['id'],)).fetchall()

    db.close()
    return render_template('admin/sessions.html', sessions=sessions_list, gym=gym)


@admin_bp.route('/sessions/<int:session_id>/toggle', methods=['POST'])
@login_required
@gym_admin_required
def toggle_session(session_id):
    db = get_db()
    db.execute('UPDATE slot_sessions SET is_active = NOT is_active WHERE id = ?', (session_id,))
    db.commit()
    db.close()
    flash('Session status updated.', 'success')
    return redirect(url_for('admin.sessions'))


@admin_bp.route('/sessions/<int:session_id>/edit', methods=['POST'])
@login_required
@gym_admin_required
def edit_session(session_id):
    db = get_db()
    name = request.form.get('name', '').strip()
    start_time = request.form.get('start_time', '')
    end_time = request.form.get('end_time', '')
    capacity = request.form.get('capacity', '40')

    if not name or not start_time or not end_time:
        flash('All fields are required.', 'error')
        db.close()
        return redirect(url_for('admin.sessions'))

    db.execute('''
        UPDATE slot_sessions SET name=?, start_time=?, end_time=?, capacity=? WHERE id=?
    ''', (name, start_time, end_time, int(capacity), session_id))
    db.commit()
    db.close()
    flash('Session updated!', 'success')
    return redirect(url_for('admin.sessions'))


@admin_bp.route('/sessions/<int:session_id>/delete', methods=['POST'])
@login_required
@gym_admin_required
def delete_session(session_id):
    db = get_db()
    # Check for existing bookings
    bookings = db.execute("SELECT COUNT(*) as c FROM slot_bookings WHERE session_id = ? AND status = 'booked' AND booking_date >= date('now')",
                          (session_id,)).fetchone()['c']
    if bookings > 0:
        flash(f'Cannot delete: {bookings} upcoming booking(s) exist. Deactivate instead.', 'warning')
    else:
        db.execute('DELETE FROM trainer_sessions WHERE session_id = ?', (session_id,))
        db.execute('DELETE FROM slot_bookings WHERE session_id = ?', (session_id,))
        db.execute('DELETE FROM slot_sessions WHERE id = ?', (session_id,))
        db.commit()
        flash('Session deleted.', 'success')
    db.close()
    return redirect(url_for('admin.sessions'))


@admin_bp.route('/plans/<int:plan_id>/delete', methods=['POST'])
@login_required
@gym_admin_required
def delete_plan(plan_id):
    db = get_db()
    subs = db.execute("SELECT COUNT(*) as c FROM member_subscriptions WHERE plan_id = ? AND status = 'active'",
                      (plan_id,)).fetchone()['c']
    if subs > 0:
        flash(f'Cannot delete: {subs} active subscription(s) on this plan. Deactivate instead.', 'warning')
    else:
        db.execute('DELETE FROM membership_plans WHERE id = ?', (plan_id,))
        db.commit()
        flash('Plan deleted.', 'success')
    db.close()
    return redirect(url_for('admin.plans'))


@admin_bp.route('/classes')
@login_required
@gym_admin_required
def classes():
    db = get_db()
    gym = _get_admin_gym(db)

    if gym:
        classes_list = db.execute('''
            SELECT c.*, u.full_name as trainer_name
            FROM classes c
            LEFT JOIN trainers t ON c.trainer_id = t.id
            LEFT JOIN users u ON t.user_id = u.id
            WHERE c.gym_id = ? ORDER BY c.day_of_week, c.start_time
        ''', (gym['id'],)).fetchall()
        trainers_list = db.execute('''
            SELECT t.id, u.full_name FROM trainers t JOIN users u ON t.user_id = u.id
            WHERE t.gym_id = ? AND t.is_approved = 1
        ''', (gym['id'],)).fetchall()
    else:
        classes_list = db.execute('''
            SELECT c.*, u.full_name as trainer_name, g.name as gym_name
            FROM classes c
            LEFT JOIN trainers t ON c.trainer_id = t.id
            LEFT JOIN users u ON t.user_id = u.id
            JOIN gyms g ON c.gym_id = g.id
            ORDER BY c.day_of_week, c.start_time
        ''').fetchall()
        trainers_list = []

    db.close()
    return render_template('admin/classes.html', classes=classes_list,
                           trainers=trainers_list, gym=gym)


@admin_bp.route('/classes/add', methods=['POST'])
@login_required
@gym_admin_required
def add_class():
    db = get_db()
    gym = _get_admin_gym(db)
    if not gym:
        flash('No gym found.', 'error')
        db.close()
        return redirect(url_for('admin.classes'))

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    class_type = request.form.get('class_type', 'group')
    capacity = request.form.get('capacity', '20')
    trainer_id = request.form.get('trainer_id', '')
    day_of_week = request.form.get('day_of_week', '')
    start_time = request.form.get('start_time', '')
    end_time = request.form.get('end_time', '')

    if not name or not day_of_week or not start_time or not end_time:
        flash('Please fill all required fields.', 'error')
        db.close()
        return redirect(url_for('admin.classes'))

    db.execute('''
        INSERT INTO classes (gym_id, trainer_id, name, description, class_type,
                             capacity, day_of_week, start_time, end_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (gym['id'], int(trainer_id) if trainer_id else None,
          name, description, class_type, int(capacity), day_of_week,
          start_time, end_time))
    db.commit()
    db.close()
    flash('Class scheduled successfully!', 'success')
    return redirect(url_for('admin.classes'))


@admin_bp.route('/attendance')
@login_required
@gym_admin_required
def attendance():
    db = get_db()
    gym = _get_admin_gym(db)
    date_filter = request.args.get('date', '')

    query = '''
        SELECT a.*, u.full_name as member_name
        FROM attendance a
        JOIN members m ON a.member_id = m.id
        JOIN users u ON m.user_id = u.id
    '''
    params = []
    if gym:
        query += ' WHERE a.gym_id = ?'
        params.append(gym['id'])
    if date_filter:
        query += ' AND ' if gym else ' WHERE '
        query += "date(a.check_in_time) = ?"
        params.append(date_filter)

    query += ' ORDER BY a.check_in_time DESC LIMIT 100'
    records = db.execute(query, params).fetchall()
    db.close()

    return render_template('admin/attendance.html', records=records,
                           gym=gym, date_filter=date_filter)


@admin_bp.route('/payments')
@login_required
@gym_admin_required
def payments():
    db = get_db()
    gym = _get_admin_gym(db)
    tab = request.args.get('tab', 'pending')

    base_where = 'WHERE p.gym_id = ?' if gym else ''
    params = [gym['id']] if gym else []

    # Pending payments
    pending_q = f'''
        SELECT p.*, u.full_name as member_name, mp.name as plan_name, mp.duration_days
        FROM payments p
        JOIN members m ON p.member_id = m.id
        JOIN users u ON m.user_id = u.id
        LEFT JOIN membership_plans mp ON p.plan_id = mp.id
        {base_where + " AND p.status = 'pending'" if base_where else "WHERE p.status = 'pending'"}
        ORDER BY p.created_at DESC
    '''
    pending_payments = db.execute(pending_q, params).fetchall()

    # All payments
    all_q = f'''
        SELECT p.*, u.full_name as member_name, mp.name as plan_name
        FROM payments p
        JOIN members m ON p.member_id = m.id
        JOIN users u ON m.user_id = u.id
        LEFT JOIN membership_plans mp ON p.plan_id = mp.id
        {base_where}
        ORDER BY p.created_at DESC LIMIT 100
    '''
    all_payments = db.execute(all_q, params).fetchall()

    # Revenue summary
    gym_filter = "AND gym_id = ?" if gym else ""
    rev_params = [gym['id']] if gym else []

    today_revenue = db.execute(f'''
        SELECT COALESCE(SUM(amount), 0) as total FROM payments
        WHERE status = 'completed' AND payment_date = date('now') {gym_filter}
    ''', rev_params).fetchone()['total']

    today_admission = db.execute(f'''
        SELECT COALESCE(SUM(amount), 0) as total FROM payments
        WHERE status = 'completed' AND payment_date = date('now')
        AND payment_type = 'admission' {gym_filter}
    ''', rev_params).fetchone()['total']

    monthly_revenue = db.execute(f'''
        SELECT COALESCE(SUM(amount), 0) as total FROM payments
        WHERE status = 'completed'
        AND strftime('%Y-%m', payment_date) = strftime('%Y-%m', 'now') {gym_filter}
    ''', rev_params).fetchone()['total']

    total_active = db.execute(f'''
        SELECT COUNT(*) as c FROM member_subscriptions ms
        JOIN members m ON ms.member_id = m.id
        WHERE ms.status = 'active' AND ms.end_date >= date('now')
        {("AND m.gym_id = ?" if gym else "")}
    ''', rev_params).fetchone()['c']

    db.close()

    return render_template('admin/payments.html', gym=gym, tab=tab,
                           pending_payments=pending_payments,
                           all_payments=all_payments,
                           today_revenue=today_revenue,
                           today_admission=today_admission,
                           monthly_revenue=monthly_revenue,
                           total_active=total_active)


@admin_bp.route('/payments/<int:payment_id>/approve', methods=['POST'])
@login_required
@gym_admin_required
def approve_payment(payment_id):
    db = get_db()
    gym = _get_admin_gym(db)

    payment = db.execute('SELECT * FROM payments WHERE id = ?', (payment_id,)).fetchone()
    if not payment:
        flash('Payment not found.', 'error')
        db.close()
        return redirect(url_for('admin.payments'))

    if gym and payment['gym_id'] != gym['id']:
        flash('Unauthorized.', 'error')
        db.close()
        return redirect(url_for('admin.payments'))

    if payment['status'] != 'pending':
        flash('This payment has already been processed.', 'info')
        db.close()
        return redirect(url_for('admin.payments'))

    # Mark payment as completed
    admin_notes = request.form.get('admin_notes', '').strip() or 'Approved'
    db.execute("UPDATE payments SET status = 'completed', admin_notes = ? WHERE id = ?",
               (admin_notes, payment_id))

    # Create subscription if plan_id exists and plan is not admission-type
    if payment['plan_id']:
        plan = db.execute('SELECT * FROM membership_plans WHERE id = ?', (payment['plan_id'],)).fetchone()
        if plan and plan['plan_type'] != 'admission':
            from datetime import date, timedelta
            start = date.today()
            end = start + timedelta(days=plan['duration_days'])

            # Expire any existing active subscription first
            db.execute("""
                UPDATE member_subscriptions SET status = 'expired'
                WHERE member_id = ? AND status = 'active'
            """, (payment['member_id'],))

            db.execute('''
                INSERT INTO member_subscriptions (member_id, plan_id, start_date, end_date, amount_paid, payment_method, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
            ''', (payment['member_id'], payment['plan_id'], start.isoformat(), end.isoformat(),
                  payment['amount'], payment['payment_method']))

            # Activate membership
            db.execute("UPDATE members SET membership_status = 'active' WHERE id = ?",
                       (payment['member_id'],))

    # Send notification to member
    member = db.execute('SELECT user_id FROM members WHERE id = ?', (payment['member_id'],)).fetchone()
    if member:
        db.execute('''
            INSERT INTO notifications (user_id, title, message, link)
            VALUES (?, 'Payment Approved ✅', 'Your payment of ₹{:.2f} has been approved. Your membership is now active!', '/member/payments')
        '''.format(payment['amount']), (member['user_id'],))

    db.commit()
    db.close()
    flash('Payment approved and membership activated!', 'success')
    return redirect(url_for('admin.payments'))


@admin_bp.route('/payments/<int:payment_id>/reject', methods=['POST'])
@login_required
@gym_admin_required
def reject_payment(payment_id):
    db = get_db()
    gym = _get_admin_gym(db)

    payment = db.execute('SELECT * FROM payments WHERE id = ?', (payment_id,)).fetchone()
    if not payment:
        flash('Payment not found.', 'error')
        db.close()
        return redirect(url_for('admin.payments'))

    if gym and payment['gym_id'] != gym['id']:
        flash('Unauthorized.', 'error')
        db.close()
        return redirect(url_for('admin.payments'))

    admin_notes = request.form.get('admin_notes', '').strip() or 'Payment rejected. Please upload correct transaction details.'
    db.execute("UPDATE payments SET status = 'failed', admin_notes = ? WHERE id = ?",
               (admin_notes, payment_id))

    # Send notification
    member = db.execute('SELECT user_id FROM members WHERE id = ?', (payment['member_id'],)).fetchone()
    if member:
        db.execute('''
            INSERT INTO notifications (user_id, title, message, link)
            VALUES (?, 'Payment Rejected ❌', ?, '/member/payments')
        ''', (member['user_id'], admin_notes))

    db.commit()
    db.close()
    flash('Payment rejected.', 'info')
    return redirect(url_for('admin.payments'))


@admin_bp.route('/reports')
@login_required
@gym_admin_required
def reports():
    db = get_db()
    gym = _get_admin_gym(db)

    # Monthly revenue (last 12 months)
    monthly_revenue = db.execute('''
        SELECT strftime('%Y-%m', payment_date) as month, SUM(amount) as total
        FROM payments WHERE status = 'completed'
        ''' + ('AND gym_id = ?' if gym else '') + '''
        GROUP BY month ORDER BY month DESC LIMIT 12
    ''', (gym['id'],) if gym else ()).fetchall()

    # Membership breakdown
    membership_stats = db.execute('''
        SELECT membership_status, COUNT(*) as count
        FROM members
        ''' + ('WHERE gym_id = ?' if gym else '') + '''
        GROUP BY membership_status
    ''', (gym['id'],) if gym else ()).fetchall()

    # Attendance trends (last 30 days)
    attendance_trend = db.execute('''
        SELECT date(check_in_time) as day, COUNT(*) as count
        FROM attendance WHERE check_in_time >= date('now', '-30 days')
        ''' + ('AND gym_id = ?' if gym else '') + '''
        GROUP BY day ORDER BY day
    ''', (gym['id'],) if gym else ()).fetchall()

    # Plan popularity
    plan_stats = db.execute('''
        SELECT mp.name, COUNT(ms.id) as subscriber_count
        FROM membership_plans mp
        LEFT JOIN member_subscriptions ms ON mp.id = ms.plan_id
        ''' + ('WHERE mp.gym_id = ?' if gym else '') + '''
        GROUP BY mp.id ORDER BY subscriber_count DESC
    ''', (gym['id'],) if gym else ()).fetchall()

    db.close()

    return render_template('admin/reports.html', gym=gym,
                           monthly_revenue=list(reversed(monthly_revenue)),
                           membership_stats=membership_stats,
                           attendance_trend=attendance_trend,
                           plan_stats=plan_stats)


@admin_bp.route('/leads')
@login_required
@gym_admin_required
def leads():
    db = get_db()
    gym = _get_admin_gym(db)

    if gym:
        leads_list = db.execute('SELECT * FROM leads WHERE gym_id = ? ORDER BY created_at DESC',
                                (gym['id'],)).fetchall()
    else:
        leads_list = db.execute('''
            SELECT l.*, g.name as gym_name FROM leads l
            JOIN gyms g ON l.gym_id = g.id ORDER BY l.created_at DESC
        ''').fetchall()

    db.close()
    return render_template('admin/leads.html', leads=leads_list, gym=gym)


@admin_bp.route('/leads/add', methods=['POST'])
@login_required
@gym_admin_required
def add_lead():
    db = get_db()
    gym = _get_admin_gym(db)
    if not gym:
        flash('No gym found.', 'error')
        db.close()
        return redirect(url_for('admin.leads'))

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    source = request.form.get('source', 'walk-in')
    notes = request.form.get('notes', '').strip()

    db.execute('''
        INSERT INTO leads (gym_id, name, email, phone, source, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (gym['id'], name, email, phone, source, notes))
    db.commit()
    db.close()
    flash('Lead added successfully!', 'success')
    return redirect(url_for('admin.leads'))


@admin_bp.route('/leads/<int:lead_id>/status', methods=['POST'])
@login_required
@gym_admin_required
def update_lead_status(lead_id):
    db = get_db()
    new_status = request.form.get('status', 'new')
    db.execute('UPDATE leads SET status = ?, followed_up_at = CURRENT_TIMESTAMP WHERE id = ?',
               (new_status, lead_id))
    db.commit()
    db.close()
    flash('Lead status updated.', 'success')
    return redirect(url_for('admin.leads'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@gym_admin_required
def settings():
    db = get_db()
    gym = _get_admin_gym(db)

    if not gym:
        flash('No gym found.', 'error')
        db.close()
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        pincode = request.form.get('pincode', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        description = request.form.get('description', '').strip()
        opening_time = request.form.get('opening_time', '06:00')
        closing_time = request.form.get('closing_time', '22:00')

        db.execute('''
            UPDATE gyms SET name=?, address=?, city=?, state=?, pincode=?,
                            phone=?, email=?, description=?, opening_time=?, closing_time=?
            WHERE id = ?
        ''', (name, address, city, state, pincode, phone, email,
              description, opening_time, closing_time, gym['id']))
        db.commit()
        flash('Gym settings updated!', 'success')
        # Re-fetch
        gym = db.execute('SELECT * FROM gyms WHERE id = ?', (gym['id'],)).fetchone()

    db.close()
    return render_template('admin/settings.html', gym=gym)
