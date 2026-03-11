import sqlite3
import os
from werkzeug.security import generate_password_hash
from config import Config


def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables and seed initial data."""
    conn = get_db()
    cursor = conn.cursor()

    # ── Users ──────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('system_admin','gym_admin','trainer','member')),
            full_name TEXT NOT NULL,
            phone TEXT,
            avatar TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Gyms ───────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gyms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            city TEXT,
            state TEXT,
            pincode TEXT,
            phone TEXT,
            email TEXT,
            description TEXT,
            logo TEXT,
            gym_type TEXT DEFAULT 'general',
            owner_id INTEGER NOT NULL,
            is_approved INTEGER DEFAULT 0,
            opening_time TEXT DEFAULT '06:00',
            closing_time TEXT DEFAULT '22:00',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
    ''')

    # ── Members ────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            gym_id INTEGER NOT NULL,
            date_of_birth DATE,
            gender TEXT,
            emergency_contact TEXT,
            emergency_phone TEXT,
            blood_group TEXT,
            weight_kg REAL,
            height_cm REAL,
            fitness_goal TEXT,
            membership_status TEXT DEFAULT 'active',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (gym_id) REFERENCES gyms(id)
        )
    ''')

    # ── Trainers ───────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trainers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            gym_id INTEGER NOT NULL,
            specialization TEXT,
            certification TEXT,
            experience_years INTEGER DEFAULT 0,
            bio TEXT,
            max_capacity INTEGER DEFAULT 20,
            is_approved INTEGER DEFAULT 0,
            approved_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (gym_id) REFERENCES gyms(id),
            FOREIGN KEY (approved_by) REFERENCES users(id)
        )
    ''')

    # ── Membership Plans ───────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS membership_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gym_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            plan_type TEXT DEFAULT 'monthly' CHECK(plan_type IN ('admission','monthly','quarterly','half_yearly','monthly_cardio','personal_training','annual')),
            duration_days INTEGER NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (gym_id) REFERENCES gyms(id)
        )
    ''')

    # ── Member Subscriptions ───────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS member_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            amount_paid REAL NOT NULL,
            payment_method TEXT DEFAULT 'cash',
            status TEXT DEFAULT 'active' CHECK(status IN ('active','expired','cancelled','frozen')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (plan_id) REFERENCES membership_plans(id)
        )
    ''')

    # ── Classes ────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gym_id INTEGER NOT NULL,
            trainer_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            class_type TEXT DEFAULT 'group',
            capacity INTEGER DEFAULT 20,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (gym_id) REFERENCES gyms(id),
            FOREIGN KEY (trainer_id) REFERENCES trainers(id)
        )
    ''')

    # ── Class Bookings ─────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS class_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            booking_date DATE NOT NULL,
            status TEXT DEFAULT 'booked' CHECK(status IN ('booked','attended','cancelled','no_show')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (class_id) REFERENCES classes(id),
            FOREIGN KEY (member_id) REFERENCES members(id)
        )
    ''')

    # ── Attendance ─────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            gym_id INTEGER NOT NULL,
            check_in_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            check_out_time TIMESTAMP,
            check_in_method TEXT DEFAULT 'manual' CHECK(check_in_method IN ('manual','qr_code','card')),
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (gym_id) REFERENCES gyms(id)
        )
    ''')

    # ── Payments ───────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            gym_id INTEGER NOT NULL,
            plan_id INTEGER,
            amount REAL NOT NULL,
            payment_type TEXT DEFAULT 'subscription',
            payment_method TEXT DEFAULT 'cash',
            reference_id TEXT,
            transaction_screenshot TEXT,
            admin_notes TEXT,
            payment_date DATE DEFAULT (date('now')),
            status TEXT DEFAULT 'pending' CHECK(status IN ('completed','pending','failed','refunded')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (gym_id) REFERENCES gyms(id),
            FOREIGN KEY (plan_id) REFERENCES membership_plans(id)
        )
    ''')

    # ── Workout Plans ──────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workout_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trainer_id INTEGER NOT NULL,
            member_id INTEGER,
            gym_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trainer_id) REFERENCES trainers(id),
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (gym_id) REFERENCES gyms(id)
        )
    ''')

    # ── Exercises ──────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_plan_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            sets INTEGER,
            reps INTEGER,
            duration TEXT,
            notes TEXT,
            day_of_week TEXT,
            FOREIGN KEY (workout_plan_id) REFERENCES workout_plans(id) ON DELETE CASCADE
        )
    ''')

    # ── Leads ──────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gym_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            source TEXT DEFAULT 'walk-in',
            status TEXT DEFAULT 'new' CHECK(status IN ('new','contacted','interested','converted','lost')),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            followed_up_at TIMESTAMP,
            FOREIGN KEY (gym_id) REFERENCES gyms(id)
        )
    ''')

    # ── Notifications ──────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── Slot Sessions (gym time slots) ─────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS slot_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gym_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            capacity INTEGER DEFAULT 40,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (gym_id) REFERENCES gyms(id)
        )
    ''')

    # ── Slot Bookings (member session bookings) ────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS slot_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            gym_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            trainer_id INTEGER,
            booking_date DATE NOT NULL,
            status TEXT DEFAULT 'booked' CHECK(status IN ('booked','attended','cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (gym_id) REFERENCES gyms(id),
            FOREIGN KEY (session_id) REFERENCES slot_sessions(id),
            FOREIGN KEY (trainer_id) REFERENCES trainers(id)
        )
    ''')

    # ── Trainer Sessions (availability) ────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trainer_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trainer_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            FOREIGN KEY (trainer_id) REFERENCES trainers(id),
            FOREIGN KEY (session_id) REFERENCES slot_sessions(id),
            UNIQUE(trainer_id, session_id)
        )
    ''')

    # ── Member-Trainer Assignment ──────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS member_trainer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            trainer_id INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (trainer_id) REFERENCES trainers(id),
            UNIQUE(member_id)
        )
    ''')

    # ── Diet Plans ─────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diet_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trainer_id INTEGER NOT NULL,
            member_id INTEGER,
            gym_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            breakfast TEXT,
            mid_morning TEXT,
            lunch TEXT,
            afternoon_snack TEXT,
            dinner TEXT,
            pre_workout TEXT,
            post_workout TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trainer_id) REFERENCES trainers(id),
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (gym_id) REFERENCES gyms(id)
        )
    ''')

    # ── Seed System Admin ──────────────────────────────────
    cursor.execute("SELECT id FROM users WHERE email = 'admin@gymdesk.com'")
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (email, password_hash, role, full_name, phone)
            VALUES (?, ?, 'system_admin', 'System Administrator', '+91-0000000000')
        ''', ('admin@gymdesk.com', generate_password_hash('admin123')))
        print("✅ Seeded system admin: admin@gymdesk.com / admin123")

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")


if __name__ == '__main__':
    init_db()
