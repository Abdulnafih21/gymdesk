from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from database import get_db
from functools import wraps

sysadmin_bp = Blueprint('sysadmin', __name__)


def system_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'system_admin':
            from flask import flash, redirect, url_for
            flash('System administrator access required.', 'error')
            return redirect(url_for('public.landing'))
        return f(*args, **kwargs)
    return decorated


@sysadmin_bp.route('/dashboard')
@login_required
@system_admin_required
def dashboard():
    db = get_db()

    stats = {
        'total_gyms': db.execute('SELECT COUNT(*) as c FROM gyms').fetchone()['c'],
        'total_members': db.execute('SELECT COUNT(*) as c FROM members').fetchone()['c'],
        'total_trainers': db.execute('SELECT COUNT(*) as c FROM trainers WHERE is_approved=1').fetchone()['c'],
        'total_revenue': db.execute("SELECT COALESCE(SUM(amount),0) as c FROM payments WHERE status='completed'").fetchone()['c'],
        'pending_trainers': db.execute('SELECT COUNT(*) as c FROM trainers WHERE is_approved=0').fetchone()['c'],
        'active_subscriptions': db.execute("SELECT COUNT(*) as c FROM member_subscriptions WHERE status='active' AND end_date >= date('now')").fetchone()['c'],
        'pending_payments': db.execute("SELECT COUNT(*) as c FROM payments WHERE status='pending'").fetchone()['c'],
        'total_classes': db.execute("SELECT COUNT(*) as c FROM classes WHERE is_active=1").fetchone()['c'],
    }

    # All gyms with member/trainer/revenue counts
    gyms = db.execute('''
        SELECT g.*,
               u.full_name as owner_name, u.email as owner_email,
               (SELECT COUNT(*) FROM members m WHERE m.gym_id = g.id) as member_count,
               (SELECT COUNT(*) FROM trainers t WHERE t.gym_id = g.id AND t.is_approved=1) as trainer_count,
               (SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.gym_id = g.id AND p.status='completed') as revenue
        FROM gyms g
        JOIN users u ON g.owner_id = u.id
        ORDER BY g.created_at DESC
    ''').fetchall()

    # Recent payments across all gyms
    recent_payments = db.execute('''
        SELECT p.*, u.full_name as member_name, g.name as gym_name
        FROM payments p
        JOIN members m ON p.member_id = m.id
        JOIN users u ON m.user_id = u.id
        JOIN gyms g ON p.gym_id = g.id
        WHERE p.status = 'completed'
        ORDER BY p.created_at DESC LIMIT 10
    ''').fetchall()

    db.close()
    return render_template('sysadmin/dashboard.html', stats=stats, gyms=gyms,
                           recent_payments=recent_payments)


@sysadmin_bp.route('/gyms')
@login_required
@system_admin_required
def gyms():
    db = get_db()

    gyms_list = db.execute('''
        SELECT g.*,
               u.full_name as owner_name, u.email as owner_email, u.phone as owner_phone,
               (SELECT COUNT(*) FROM members m WHERE m.gym_id = g.id) as member_count,
               (SELECT COUNT(*) FROM trainers t WHERE t.gym_id = g.id AND t.is_approved=1) as trainer_count,
               (SELECT COUNT(*) FROM trainers t WHERE t.gym_id = g.id AND t.is_approved=0) as pending_trainers,
               (SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.gym_id = g.id AND p.status='completed') as total_revenue,
               (SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.gym_id = g.id AND p.status='completed'
                AND strftime('%Y-%m', p.payment_date) = strftime('%Y-%m', 'now')) as monthly_revenue,
               (SELECT COUNT(*) FROM member_subscriptions ms
                JOIN members mb ON ms.member_id = mb.id
                WHERE mb.gym_id = g.id AND ms.status='active' AND ms.end_date >= date('now')) as active_subscriptions
        FROM gyms g
        JOIN users u ON g.owner_id = u.id
        ORDER BY g.name
    ''').fetchall()

    db.close()
    return render_template('sysadmin/gyms.html', gyms=gyms_list)


@sysadmin_bp.route('/gyms/<int:gym_id>')
@login_required
@system_admin_required
def gym_detail(gym_id):
    db = get_db()

    gym = db.execute('''
        SELECT g.*, u.full_name as owner_name, u.email as owner_email, u.phone as owner_phone
        FROM gyms g JOIN users u ON g.owner_id = u.id
        WHERE g.id = ?
    ''', (gym_id,)).fetchone()

    if not gym:
        from flask import flash, redirect, url_for
        flash('Gym not found.', 'error')
        db.close()
        return redirect(url_for('sysadmin.gyms'))

    # Members
    members = db.execute('''
        SELECT m.*, u.full_name, u.email, u.phone, u.created_at as user_created,
               ms.status as sub_status, ms.end_date as sub_end,
               mp.name as plan_name
        FROM members m
        JOIN users u ON m.user_id = u.id
        LEFT JOIN member_subscriptions ms ON ms.member_id = m.id AND ms.status = 'active'
        LEFT JOIN membership_plans mp ON ms.plan_id = mp.id
        WHERE m.gym_id = ?
        ORDER BY m.joined_at DESC
    ''', (gym_id,)).fetchall()

    # Trainers
    trainers = db.execute('''
        SELECT t.*, u.full_name, u.email, u.phone,
               (SELECT COUNT(*) FROM member_trainer mt WHERE mt.trainer_id = t.id) as assigned_members
        FROM trainers t
        JOIN users u ON t.user_id = u.id
        WHERE t.gym_id = ?
        ORDER BY t.is_approved DESC, u.full_name
    ''', (gym_id,)).fetchall()

    # Plans
    plans = db.execute('SELECT * FROM membership_plans WHERE gym_id = ? ORDER BY price', (gym_id,)).fetchall()

    # Revenue stats
    revenue = {
        'total': db.execute("SELECT COALESCE(SUM(amount),0) as c FROM payments WHERE gym_id=? AND status='completed'", (gym_id,)).fetchone()['c'],
        'monthly': db.execute("SELECT COALESCE(SUM(amount),0) as c FROM payments WHERE gym_id=? AND status='completed' AND strftime('%Y-%m', payment_date)=strftime('%Y-%m','now')", (gym_id,)).fetchone()['c'],
        'today': db.execute("SELECT COALESCE(SUM(amount),0) as c FROM payments WHERE gym_id=? AND status='completed' AND payment_date=date('now')", (gym_id,)).fetchone()['c'],
    }

    # Recent payments
    payments = db.execute('''
        SELECT p.*, u.full_name as member_name, mp.name as plan_name
        FROM payments p
        JOIN members m ON p.member_id = m.id
        JOIN users u ON m.user_id = u.id
        LEFT JOIN membership_plans mp ON p.plan_id = mp.id
        WHERE p.gym_id = ?
        ORDER BY p.created_at DESC LIMIT 20
    ''', (gym_id,)).fetchall()

    db.close()
    return render_template('sysadmin/gym_detail.html', gym=gym, members=members,
                           trainers=trainers, plans=plans, revenue=revenue,
                           payments=payments)


@sysadmin_bp.route('/admins')
@login_required
@system_admin_required
def admins():
    db = get_db()

    admins_list = db.execute('''
        SELECT u.id, u.full_name, u.email, u.phone, u.created_at,
               g.name as gym_name, g.city as gym_city,
               (SELECT COUNT(*) FROM members m WHERE m.gym_id = g.id) as member_count,
               (SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.gym_id = g.id AND p.status='completed') as total_revenue
        FROM users u
        LEFT JOIN gyms g ON g.owner_id = u.id
        WHERE u.role = 'gym_admin'
        ORDER BY u.full_name
    ''').fetchall()

    db.close()
    return render_template('sysadmin/admins.html', admins=admins_list)


@sysadmin_bp.route('/reports')
@login_required
@system_admin_required
def reports():
    db = get_db()

    # Get all gyms for the dropdown
    gyms = db.execute('SELECT id, name FROM gyms ORDER BY name').fetchall()

    # Gym filter from query string
    selected_gym = request.args.get('gym_id', 'all')
    gym_id = int(selected_gym) if selected_gym and selected_gym != 'all' else None

    # Build filter fragments
    pay_filter = ('AND p.gym_id = ?', (gym_id,)) if gym_id else ('', ())
    mem_filter = ('WHERE gym_id = ?', (gym_id,)) if gym_id else ('', ())
    att_filter = ('AND gym_id = ?', (gym_id,)) if gym_id else ('', ())
    ss_filter  = ('WHERE ss.gym_id = ?', (gym_id,)) if gym_id else ('', ())
    tr_filter  = ('WHERE t.gym_id = ? AND', (gym_id,)) if gym_id else ('WHERE', ())
    mp_filter  = ('WHERE mp.gym_id = ?', (gym_id,)) if gym_id else ('', ())

    # Monthly revenue (last 12 months)
    monthly_revenue = db.execute(f'''
        SELECT strftime('%Y-%m', payment_date) as month, SUM(amount) as total
        FROM payments p WHERE p.status = 'completed' {pay_filter[0]}
        GROUP BY month ORDER BY month DESC LIMIT 12
    ''', pay_filter[1]).fetchall()

    # Revenue by gym (only show when "All Gyms")
    revenue_by_gym = []
    if not gym_id:
        revenue_by_gym = db.execute('''
            SELECT g.name, COALESCE(SUM(p.amount),0) as total
            FROM gyms g
            LEFT JOIN payments p ON p.gym_id = g.id AND p.status = 'completed'
            GROUP BY g.id ORDER BY total DESC
        ''').fetchall()

    # Membership breakdown
    membership_stats = db.execute(f'''
        SELECT membership_status, COUNT(*) as count FROM members {mem_filter[0]} GROUP BY membership_status
    ''', mem_filter[1]).fetchall()

    # Attendance trends (last 30 days)
    attendance_trend = db.execute(f'''
        SELECT date(check_in_time) as day, COUNT(*) as count
        FROM attendance WHERE check_in_time >= date('now', '-30 days') {att_filter[0]}
        GROUP BY day ORDER BY day
    ''', att_filter[1]).fetchall()

    # Booking stats by session
    booking_stats = db.execute(f'''
        SELECT ss.name as session_name, COUNT(sb.id) as count
        FROM slot_sessions ss
        LEFT JOIN slot_bookings sb ON sb.session_id = ss.id AND sb.status = 'booked'
        {ss_filter[0]}
        GROUP BY ss.id ORDER BY count DESC
    ''', ss_filter[1]).fetchall()

    # Trainer workload
    trainer_workload = db.execute(f'''
        SELECT u.full_name as name, t.max_capacity as capacity,
               (SELECT COUNT(*) FROM member_trainer mt WHERE mt.trainer_id = t.id) as members
        FROM trainers t JOIN users u ON t.user_id = u.id
        {tr_filter[0]} t.is_approved = 1
        ORDER BY members DESC
    ''', tr_filter[1]).fetchall()

    # Plan popularity with price
    plan_stats = db.execute(f'''
        SELECT mp.name, g.name as gym_name, mp.price, COUNT(ms.id) as subscriber_count
        FROM membership_plans mp
        JOIN gyms g ON mp.gym_id = g.id
        LEFT JOIN member_subscriptions ms ON mp.id = ms.plan_id
        {mp_filter[0]}
        GROUP BY mp.id ORDER BY subscriber_count DESC
    ''', mp_filter[1]).fetchall()

    db.close()
    return render_template('sysadmin/reports.html',
                           gyms=gyms, selected_gym=selected_gym,
                           monthly_revenue=list(reversed(monthly_revenue)),
                           revenue_by_gym=revenue_by_gym,
                           membership_stats=membership_stats,
                           attendance_trend=attendance_trend,
                           booking_stats=booking_stats,
                           trainer_workload=trainer_workload,
                           plan_stats=plan_stats)

