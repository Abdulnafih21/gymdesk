from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import get_db
from utils.decorators import trainer_required

trainer_bp = Blueprint('trainer', __name__)


def _get_trainer(db):
    """Get the trainer record for the current user."""
    return db.execute('SELECT * FROM trainers WHERE user_id = ?', (current_user.id,)).fetchone()


@trainer_bp.route('/dashboard')
@login_required
@trainer_required
def dashboard():
    db = get_db()
    trainer = _get_trainer(db)

    if not trainer:
        flash('Trainer profile not found.', 'error')
        db.close()
        return redirect(url_for('public.landing'))

    if not trainer['is_approved']:
        db.close()
        return render_template('trainer/pending.html', trainer=trainer)

    gym = db.execute('SELECT * FROM gyms WHERE id = ?', (trainer['gym_id'],)).fetchone()

    # Stats
    stats = {
        'total_classes': db.execute('SELECT COUNT(*) as c FROM classes WHERE trainer_id = ? AND is_active = 1',
                                    (trainer['id'],)).fetchone()['c'],
        'total_members': db.execute('''
            SELECT COUNT(DISTINCT cb.member_id) as c FROM class_bookings cb
            JOIN classes c ON cb.class_id = c.id
            WHERE c.trainer_id = ? AND cb.status = 'booked'
        ''', (trainer['id'],)).fetchone()['c'],
        'workout_plans': db.execute('SELECT COUNT(*) as c FROM workout_plans WHERE trainer_id = ?',
                                    (trainer['id'],)).fetchone()['c'],
    }

    # My classes
    my_classes = db.execute('''
        SELECT c.*,
               (SELECT COUNT(*) FROM class_bookings cb WHERE cb.class_id = c.id AND cb.status = 'booked') as booked_count
        FROM classes c WHERE c.trainer_id = ? AND c.is_active = 1
        ORDER BY c.day_of_week, c.start_time
    ''', (trainer['id'],)).fetchall()

    db.close()

    return render_template('trainer/dashboard.html', trainer=trainer, gym=gym,
                           stats=stats, my_classes=my_classes)


@trainer_bp.route('/classes')
@login_required
@trainer_required
def classes():
    db = get_db()
    trainer = _get_trainer(db)

    if not trainer or not trainer['is_approved']:
        flash('Your account is pending approval.', 'warning')
        db.close()
        return redirect(url_for('trainer.dashboard'))

    classes_list = db.execute('''
        SELECT c.*,
               (SELECT COUNT(*) FROM class_bookings cb WHERE cb.class_id = c.id AND cb.status = 'booked') as booked_count
        FROM classes c WHERE c.trainer_id = ?
        ORDER BY c.day_of_week, c.start_time
    ''', (trainer['id'],)).fetchall()

    db.close()
    return render_template('trainer/classes.html', classes=classes_list, trainer=trainer)


@trainer_bp.route('/members')
@login_required
@trainer_required
def members():
    db = get_db()
    trainer = _get_trainer(db)

    if not trainer or not trainer['is_approved']:
        flash('Your account is pending approval.', 'warning')
        db.close()
        return redirect(url_for('trainer.dashboard'))

    # Members who booked my classes or have my workout plans
    members_list = db.execute('''
        SELECT DISTINCT u.full_name, u.email, u.phone, m.id as member_id,
               m.fitness_goal, m.weight_kg, m.height_cm
        FROM members m
        JOIN users u ON m.user_id = u.id
        WHERE m.id IN (
            SELECT DISTINCT cb.member_id FROM class_bookings cb
            JOIN classes c ON cb.class_id = c.id
            WHERE c.trainer_id = ?
            UNION
            SELECT DISTINCT wp.member_id FROM workout_plans wp
            WHERE wp.trainer_id = ? AND wp.member_id IS NOT NULL
        )
        ORDER BY u.full_name
    ''', (trainer['id'], trainer['id'])).fetchall()

    db.close()
    return render_template('trainer/members.html', members=members_list, trainer=trainer)


@trainer_bp.route('/workouts')
@login_required
@trainer_required
def workouts():
    db = get_db()
    trainer = _get_trainer(db)

    if not trainer or not trainer['is_approved']:
        flash('Your account is pending approval.', 'warning')
        db.close()
        return redirect(url_for('trainer.dashboard'))

    plans = db.execute('''
        SELECT wp.*, u.full_name as member_name
        FROM workout_plans wp
        LEFT JOIN members m ON wp.member_id = m.id
        LEFT JOIN users u ON m.user_id = u.id
        WHERE wp.trainer_id = ?
        ORDER BY wp.created_at DESC
    ''', (trainer['id'],)).fetchall()

    # Get all gym members for assignment
    gym_members = db.execute('''
        SELECT m.id, u.full_name FROM members m
        JOIN users u ON m.user_id = u.id
        WHERE m.gym_id = ?
        ORDER BY u.full_name
    ''', (trainer['gym_id'],)).fetchall()

    db.close()
    return render_template('trainer/workouts.html', plans=plans,
                           trainer=trainer, gym_members=gym_members)


@trainer_bp.route('/workouts/add', methods=['POST'])
@login_required
@trainer_required
def add_workout():
    db = get_db()
    trainer = _get_trainer(db)

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    member_id = request.form.get('member_id', '')

    if not title:
        flash('Workout plan title is required.', 'error')
        db.close()
        return redirect(url_for('trainer.workouts'))

    cursor = db.execute('''
        INSERT INTO workout_plans (trainer_id, member_id, gym_id, title, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (trainer['id'], int(member_id) if member_id else None,
          trainer['gym_id'], title, description))
    plan_id = cursor.lastrowid

    # Add exercises
    exercise_names = request.form.getlist('exercise_name[]')
    exercise_sets = request.form.getlist('exercise_sets[]')
    exercise_reps = request.form.getlist('exercise_reps[]')
    exercise_days = request.form.getlist('exercise_day[]')
    exercise_notes = request.form.getlist('exercise_notes[]')

    for i in range(len(exercise_names)):
        if exercise_names[i].strip():
            db.execute('''
                INSERT INTO exercises (workout_plan_id, name, sets, reps, day_of_week, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (plan_id, exercise_names[i].strip(),
                  int(exercise_sets[i]) if i < len(exercise_sets) and exercise_sets[i] else None,
                  int(exercise_reps[i]) if i < len(exercise_reps) and exercise_reps[i] else None,
                  exercise_days[i] if i < len(exercise_days) else None,
                  exercise_notes[i].strip() if i < len(exercise_notes) else None))

    # Notify member if assigned
    if member_id:
        member_user = db.execute('''
            SELECT user_id FROM members WHERE id = ?
        ''', (int(member_id),)).fetchone()
        if member_user:
            db.execute('''
                INSERT INTO notifications (user_id, title, message, link)
                VALUES (?, 'New Workout Plan', ?, '/member/workouts')
            ''', (member_user['user_id'],
                  f'{current_user.full_name} assigned you a new workout plan: {title}'))

    db.commit()
    db.close()
    flash('Workout plan created!', 'success')
    return redirect(url_for('trainer.workouts'))


# ── Trainer Schedule (Session Availability) ────────────────
@trainer_bp.route('/schedule', methods=['GET', 'POST'])
@login_required
@trainer_required
def schedule():
    db = get_db()
    trainer = _get_trainer(db)

    if not trainer or not trainer['is_approved']:
        flash('Your account is pending approval.', 'warning')
        db.close()
        return redirect(url_for('trainer.dashboard'))

    if request.method == 'POST':
        # Clear existing sessions
        db.execute('DELETE FROM trainer_sessions WHERE trainer_id = ?', (trainer['id'],))

        # Add selected sessions
        session_ids = request.form.getlist('session_ids')
        for sid in session_ids:
            db.execute('INSERT OR IGNORE INTO trainer_sessions (trainer_id, session_id) VALUES (?, ?)',
                       (trainer['id'], int(sid)))

        # Update max capacity
        max_cap = request.form.get('max_capacity', '20')
        db.execute('UPDATE trainers SET max_capacity = ? WHERE id = ?',
                   (int(max_cap) if max_cap else 20, trainer['id']))

        db.commit()
        flash('Schedule updated!', 'success')
        trainer = _get_trainer(db)

    # Get all sessions for the gym
    sessions = db.execute('SELECT * FROM slot_sessions WHERE gym_id = ? AND is_active = 1 ORDER BY start_time',
                          (trainer['gym_id'],)).fetchall()

    # Currently selected sessions
    my_sessions = db.execute('SELECT session_id FROM trainer_sessions WHERE trainer_id = ?',
                             (trainer['id'],)).fetchall()
    my_session_ids = {s['session_id'] for s in my_sessions}

    # Assigned members count
    assigned_count = db.execute('SELECT COUNT(*) as c FROM member_trainer WHERE trainer_id = ?',
                                (trainer['id'],)).fetchone()['c']

    db.close()
    return render_template('trainer/schedule.html', trainer=trainer, sessions=sessions,
                           my_session_ids=my_session_ids, assigned_count=assigned_count)


# ── Trainer Slot Bookings View ─────────────────────────────
@trainer_bp.route('/slots')
@login_required
@trainer_required
def slots():
    db = get_db()
    trainer = _get_trainer(db)

    if not trainer or not trainer['is_approved']:
        flash('Your account is pending approval.', 'warning')
        db.close()
        return redirect(url_for('trainer.dashboard'))

    # Upcoming slot bookings assigned to this trainer
    bookings = db.execute('''
        SELECT sb.*, ss.name as session_name, ss.start_time, ss.end_time,
               u.full_name as member_name
        FROM slot_bookings sb
        JOIN slot_sessions ss ON sb.session_id = ss.id
        JOIN members m ON sb.member_id = m.id
        JOIN users u ON m.user_id = u.id
        WHERE sb.trainer_id = ? AND sb.booking_date >= date('now') AND sb.status = 'booked'
        ORDER BY sb.booking_date, ss.start_time
    ''', (trainer['id'],)).fetchall()

    db.close()
    return render_template('trainer/slots.html', trainer=trainer, bookings=bookings)


# ── Notifications ──────────────────────────────────────────
@trainer_bp.route('/notifications')
@login_required
@trainer_required
def notifications():
    db = get_db()
    notifs = db.execute('''
        SELECT * FROM notifications WHERE user_id = ?
        ORDER BY created_at DESC LIMIT 50
    ''', (current_user.id,)).fetchall()

    db.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0',
               (current_user.id,))
    db.commit()
    db.close()
    return render_template('trainer/notifications.html', notifications=notifs)


# ── Diet Plans ─────────────────────────────────────────────
@trainer_bp.route('/diet-plans')
@login_required
@trainer_required
def diet_plans():
    db = get_db()
    trainer = _get_trainer(db)

    if not trainer or not trainer['is_approved']:
        flash('Your account is pending approval.', 'warning')
        db.close()
        return redirect(url_for('trainer.dashboard'))

    plans = db.execute('''
        SELECT dp.*, u.full_name as member_name
        FROM diet_plans dp
        LEFT JOIN members m ON dp.member_id = m.id
        LEFT JOIN users u ON m.user_id = u.id
        WHERE dp.trainer_id = ?
        ORDER BY dp.created_at DESC
    ''', (trainer['id'],)).fetchall()

    # Get assigned members for the dropdown
    assigned_members = db.execute('''
        SELECT m.id, u.full_name
        FROM member_trainer mt
        JOIN members m ON mt.member_id = m.id
        JOIN users u ON m.user_id = u.id
        WHERE mt.trainer_id = ?
        ORDER BY u.full_name
    ''', (trainer['id'],)).fetchall()

    db.close()
    return render_template('trainer/diet_plans.html', diet_plans=plans,
                           trainer=trainer, assigned_members=assigned_members)


@trainer_bp.route('/diet-plans/add', methods=['POST'])
@login_required
@trainer_required
def add_diet_plan():
    db = get_db()
    trainer = _get_trainer(db)

    title = request.form.get('title', '').strip()
    member_id = request.form.get('member_id', '')
    description = request.form.get('description', '').strip()
    breakfast = request.form.get('breakfast', '').strip()
    mid_morning = request.form.get('mid_morning', '').strip()
    lunch = request.form.get('lunch', '').strip()
    afternoon_snack = request.form.get('afternoon_snack', '').strip()
    dinner = request.form.get('dinner', '').strip()
    pre_workout = request.form.get('pre_workout', '').strip()
    post_workout = request.form.get('post_workout', '').strip()
    notes = request.form.get('notes', '').strip()

    if not title:
        flash('Diet plan title is required.', 'error')
        db.close()
        return redirect(url_for('trainer.diet_plans'))

    db.execute('''
        INSERT INTO diet_plans (trainer_id, member_id, gym_id, title, description,
                                breakfast, mid_morning, lunch, afternoon_snack,
                                dinner, pre_workout, post_workout, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (trainer['id'], int(member_id) if member_id else None,
          trainer['gym_id'], title, description or None,
          breakfast or None, mid_morning or None, lunch or None,
          afternoon_snack or None, dinner or None,
          pre_workout or None, post_workout or None, notes or None))

    # Notify the member if assigned
    if member_id:
        member_user = db.execute('SELECT user_id FROM members WHERE id = ?',
                                 (int(member_id),)).fetchone()
        if member_user:
            db.execute('''
                INSERT INTO notifications (user_id, title, message, link)
                VALUES (?, 'New Diet Plan 🥗', ?, '/member/workouts')
            ''', (member_user['user_id'],
                  f'{current_user.full_name} assigned you a new diet plan: {title}'))

    db.commit()
    db.close()
    flash('Diet plan created!', 'success')
    return redirect(url_for('trainer.diet_plans'))


@trainer_bp.route('/diet-plans/<int:plan_id>/delete', methods=['POST'])
@login_required
@trainer_required
def delete_diet_plan(plan_id):
    db = get_db()
    trainer = _get_trainer(db)

    plan = db.execute('SELECT * FROM diet_plans WHERE id = ? AND trainer_id = ?',
                      (plan_id, trainer['id'])).fetchone()
    if not plan:
        flash('Diet plan not found.', 'error')
        db.close()
        return redirect(url_for('trainer.diet_plans'))

    db.execute('DELETE FROM diet_plans WHERE id = ?', (plan_id,))
    db.commit()
    db.close()
    flash('Diet plan deleted.', 'success')
    return redirect(url_for('trainer.diet_plans'))

