from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        db = get_db()
        user_row = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        db.close()

        if user_row and check_password_hash(user_row['password_hash'], password):
            if not user_row['is_active']:
                flash('Your account has been deactivated. Contact support.', 'error')
                return render_template('auth/login.html')

            from app import User
            user = User(user_row)
            login_user(user, remember=True)
            flash(f'Welcome back, {user.full_name}!', 'success')

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return _redirect_by_role(user.role)
        else:
            flash('Invalid email or password.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/register/gym-admin', methods=['GET', 'POST'])
def register_gym_admin():
    if current_user.is_authenticated:
        return redirect(url_for('public.landing'))

    if request.method == 'POST':
        # User fields
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Gym fields
        gym_name = request.form.get('gym_name', '').strip()
        gym_address = request.form.get('gym_address', '').strip()
        gym_city = request.form.get('gym_city', '').strip()
        gym_state = request.form.get('gym_state', '').strip()
        gym_pincode = request.form.get('gym_pincode', '').strip()
        gym_phone = request.form.get('gym_phone', '').strip()
        gym_email = request.form.get('gym_email', '').strip().lower()
        gym_type = request.form.get('gym_type', 'general')
        gym_description = request.form.get('gym_description', '').strip()
        opening_time = request.form.get('opening_time', '06:00')
        closing_time = request.form.get('closing_time', '22:00')

        # Validation
        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not email:
            errors.append('Email is required.')
        if not password:
            errors.append('Password is required.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        if not gym_name:
            errors.append('Gym name is required.')

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            errors.append('An account with this email already exists.')

        if errors:
            for err in errors:
                flash(err, 'error')
            db.close()
            return render_template('auth/register_gym_admin.html')

        try:
            # Create user
            cursor = db.execute('''
                INSERT INTO users (email, password_hash, role, full_name, phone)
                VALUES (?, ?, 'gym_admin', ?, ?)
            ''', (email, generate_password_hash(password), full_name, phone))
            user_id = cursor.lastrowid

            # Create gym
            db.execute('''
                INSERT INTO gyms (name, address, city, state, pincode, phone, email,
                                  description, gym_type, owner_id, is_approved, opening_time, closing_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ''', (gym_name, gym_address, gym_city, gym_state, gym_pincode,
                  gym_phone, gym_email, gym_description, gym_type, user_id,
                  opening_time, closing_time))

            db.commit()
            flash('Gym registered successfully! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
        finally:
            db.close()

    return render_template('auth/register_gym_admin.html')


@auth_bp.route('/register/member', methods=['GET', 'POST'])
def register_member():
    if current_user.is_authenticated:
        return redirect(url_for('public.landing'))

    db = get_db()
    gyms = db.execute('SELECT id, name, city FROM gyms WHERE is_approved = 1 ORDER BY name').fetchall()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        gym_id = request.form.get('gym_id', '')
        date_of_birth = request.form.get('date_of_birth', '')
        gender = request.form.get('gender', '')
        emergency_contact = request.form.get('emergency_contact', '').strip()
        emergency_phone = request.form.get('emergency_phone', '').strip()
        blood_group = request.form.get('blood_group', '')
        weight = request.form.get('weight', '')
        height = request.form.get('height', '')
        fitness_goal = request.form.get('fitness_goal', '').strip()

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not email:
            errors.append('Email is required.')
        if not password:
            errors.append('Password is required.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        if not gym_id:
            errors.append('Please select a gym.')

        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            errors.append('An account with this email already exists.')

        if errors:
            for err in errors:
                flash(err, 'error')
            db.close()
            return render_template('auth/register_member.html', gyms=gyms)

        try:
            cursor = db.execute('''
                INSERT INTO users (email, password_hash, role, full_name, phone)
                VALUES (?, ?, 'member', ?, ?)
            ''', (email, generate_password_hash(password), full_name, phone))
            user_id = cursor.lastrowid

            db.execute('''
                INSERT INTO members (user_id, gym_id, date_of_birth, gender, emergency_contact,
                                     emergency_phone, blood_group, weight_kg, height_cm, fitness_goal)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, int(gym_id), date_of_birth or None, gender or None,
                  emergency_contact or None, emergency_phone or None,
                  blood_group or None,
                  float(weight) if weight else None,
                  float(height) if height else None,
                  fitness_goal or None))
            member_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

            # Auto-assign trainer with least members (who has capacity)
            best_trainer = db.execute('''
                SELECT t.id, u.full_name, t.max_capacity,
                       (SELECT COUNT(*) FROM member_trainer mt WHERE mt.trainer_id = t.id) as current_members
                FROM trainers t
                JOIN users u ON t.user_id = u.id
                WHERE t.gym_id = ? AND t.is_approved = 1
                HAVING current_members < t.max_capacity
                ORDER BY current_members ASC LIMIT 1
            ''', (int(gym_id),)).fetchone()

            if best_trainer:
                db.execute('INSERT INTO member_trainer (member_id, trainer_id) VALUES (?, ?)',
                           (member_id, best_trainer['id']))
                # Notify member about trainer assignment
                db.execute('''
                    INSERT INTO notifications (user_id, title, message, link)
                    VALUES (?, 'Trainer Assigned 🏋️', ?, '/member/slots')
                ''', (user_id, f'You have been assigned to trainer {best_trainer["full_name"]}. You can change your trainer from the Book Slot page.'))

            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
        finally:
            db.close()
    else:
        db.close()

    return render_template('auth/register_member.html', gyms=gyms)


@auth_bp.route('/register/trainer', methods=['GET', 'POST'])
def register_trainer():
    if current_user.is_authenticated:
        return redirect(url_for('public.landing'))

    db = get_db()
    gyms = db.execute('SELECT id, name, city FROM gyms WHERE is_approved = 1 ORDER BY name').fetchall()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        gym_id = request.form.get('gym_id', '')
        specialization = request.form.get('specialization', '').strip()
        certification = request.form.get('certification', '').strip()
        experience_years = request.form.get('experience_years', '0')
        bio = request.form.get('bio', '').strip()

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not email:
            errors.append('Email is required.')
        if not password:
            errors.append('Password is required.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        if not gym_id:
            errors.append('Please select a gym.')

        existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            errors.append('An account with this email already exists.')

        if errors:
            for err in errors:
                flash(err, 'error')
            db.close()
            return render_template('auth/register_trainer.html', gyms=gyms)

        try:
            cursor = db.execute('''
                INSERT INTO users (email, password_hash, role, full_name, phone)
                VALUES (?, ?, 'trainer', ?, ?)
            ''', (email, generate_password_hash(password), full_name, phone))
            user_id = cursor.lastrowid

            db.execute('''
                INSERT INTO trainers (user_id, gym_id, specialization, certification,
                                      experience_years, bio, is_approved)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            ''', (user_id, int(gym_id), specialization or None, certification or None,
                  int(experience_years) if experience_years else 0, bio or None))

            db.commit()
            flash('Registration submitted! Your gym admin will review and approve your account.', 'info')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
        finally:
            db.close()
    else:
        db.close()

    return render_template('auth/register_trainer.html', gyms=gyms)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('public.landing'))


def _redirect_by_role(role):
    """Redirect user to their appropriate dashboard."""
    if role == 'system_admin':
        return redirect(url_for('sysadmin.dashboard'))
    elif role == 'gym_admin':
        return redirect(url_for('admin.dashboard'))
    elif role == 'trainer':
        return redirect(url_for('trainer.dashboard'))
    elif role == 'member':
        return redirect(url_for('member.dashboard'))
    return redirect(url_for('public.landing'))
