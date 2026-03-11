"""Seed test data for the GymDesk application."""
import sqlite3
import os
import traceback
from werkzeug.security import generate_password_hash
from config import Config


def seed():
    log_path = os.path.join(os.path.dirname(Config.DATABASE), 'seed_log.txt')
    with open(log_path, 'w') as log:
        try:
            conn = sqlite3.connect(Config.DATABASE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            log.write(f"Connected to: {Config.DATABASE}\n")

            # Clean all data for fresh seed
            for table in ['member_trainer', 'trainer_sessions', 'slot_bookings', 'slot_sessions',
                           'notifications', 'exercises', 'workout_plans', 'class_bookings',
                           'attendance', 'payments', 'member_subscriptions', 'leads',
                           'classes', 'membership_plans', 'members', 'trainers', 'gyms']:
                try:
                    c.execute(f"DELETE FROM [{table}]")
                    log.write(f"  Cleared {table}\n")
                except Exception as e:
                    log.write(f"  Error clearing {table}: {e}\n")
            c.execute("DELETE FROM users WHERE email != 'admin@gymdesk.com'")
            conn.commit()
            log.write("All old data cleared.\n\n")

            # ── Gym Admin ──────────────────────────────────────
            c.execute('''
                INSERT INTO users (email, password_hash, role, full_name, phone)
                VALUES (?, ?, 'gym_admin', 'Rajesh Kumar', '+91-9876543210')
            ''', ('gymadmin@example.com', generate_password_hash('password123')))
            admin_user_id = c.lastrowid
            log.write(f"Gym Admin user ID: {admin_user_id}\n")

            c.execute('''
                INSERT INTO gyms (name, address, city, state, pincode, phone, email,
                                  description, gym_type, owner_id, is_approved, opening_time, closing_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '06:00', '22:00')
            ''', ('Iron Fitness Studio', '123 MG Road', 'Kochi', 'Kerala', '682001',
                  '+91-4842345678', 'info@ironfitness.com',
                  'A premium facility for all your fitness goals.',
                  'general', admin_user_id))
            gym_id = c.lastrowid
            log.write(f"Gym ID: {gym_id}\n")

            # ── Trainer 1: Ahmed ───────────────────────────────
            c.execute('''
                INSERT INTO users (email, password_hash, role, full_name, phone)
                VALUES (?, ?, 'trainer', 'Ahmed Khan', '+91-9876501234')
            ''', ('trainer@example.com', generate_password_hash('password123')))
            t1_user_id = c.lastrowid
            log.write(f"Trainer 1 user ID: {t1_user_id}\n")

            c.execute('''
                INSERT INTO trainers (user_id, gym_id, specialization, certification,
                                      experience_years, bio, max_capacity, is_approved, approved_by)
                VALUES (?, ?, 'Weight Training', 'ACE Certified', 5,
                        'Expert in strength training and body building.', 20, 1, ?)
            ''', (t1_user_id, gym_id, admin_user_id))
            trainer1_id = c.lastrowid
            log.write(f"Trainer 1 ID: {trainer1_id}\n")

            # ── Trainer 2: Ali ─────────────────────────────────
            c.execute('''
                INSERT INTO users (email, password_hash, role, full_name, phone)
                VALUES (?, ?, 'trainer', 'Ali Reza', '+91-9876509876')
            ''', ('trainer2@example.com', generate_password_hash('password123')))
            t2_user_id = c.lastrowid
            log.write(f"Trainer 2 user ID: {t2_user_id}\n")

            c.execute('''
                INSERT INTO trainers (user_id, gym_id, specialization, certification,
                                      experience_years, bio, max_capacity, is_approved, approved_by)
                VALUES (?, ?, 'Cardio & HIIT', 'ISSA Certified', 3,
                        'Specialist in cardio and high-intensity interval training.', 15, 1, ?)
            ''', (t2_user_id, gym_id, admin_user_id))
            trainer2_id = c.lastrowid
            log.write(f"Trainer 2 ID: {trainer2_id}\n")

            # ── Members ────────────────────────────────────────
            for email, name, phone, goal, tid in [
                ('member1@example.com', 'Rahim Shah', '+91-9000100001', 'Weight Loss', trainer1_id),
                ('member2@example.com', 'Arjun Nair', '+91-9000100002', 'Muscle Gain', trainer2_id),
            ]:
                c.execute('''
                    INSERT INTO users (email, password_hash, role, full_name, phone)
                    VALUES (?, ?, 'member', ?, ?)
                ''', (email, generate_password_hash('password123'), name, phone))
                uid = c.lastrowid

                c.execute('''
                    INSERT INTO members (user_id, gym_id, gender, fitness_goal, membership_status)
                    VALUES (?, ?, 'Male', ?, 'inactive')
                ''', (uid, gym_id, goal))
                mid = c.lastrowid

                c.execute('INSERT INTO member_trainer (member_id, trainer_id) VALUES (?, ?)', (mid, tid))
                c.execute('''
                    INSERT INTO notifications (user_id, title, message, link)
                    VALUES (?, 'Trainer Assigned', 'You have been assigned a trainer.', '/member/slots')
                ''', (uid,))
                log.write(f"Member {email} ID={mid}, assigned trainer {tid}\n")

            # ── Membership Plans ───────────────────────────────
            for name, ptype, days, price, desc in [
                ('Admission Fee', 'admission', 365, 1000, 'One-time admission fee'),
                ('Monthly', 'monthly', 30, 1500, 'Standard monthly membership'),
                ('Quarterly', 'quarterly', 90, 4000, '3-month membership with savings'),
                ('Half Yearly', 'half_yearly', 180, 7500, '6-month membership with savings'),
                ('Monthly + Cardio', 'monthly_cardio', 30, 2000, 'Monthly with cardio access'),
                ('Personal Training', 'personal_training', 30, 5000, '1-on-1 personal training'),
            ]:
                c.execute('''
                    INSERT INTO membership_plans (gym_id, name, plan_type, duration_days, price, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (gym_id, name, ptype, days, price, desc))
            log.write("6 plans created\n")

            # ── Slot Sessions ──────────────────────────────────
            session_ids = []
            for name, start, end, cap in [
                ('Morning', '06:00', '08:00', 40),
                ('Afternoon', '12:00', '14:00', 30),
                ('Evening', '17:00', '20:00', 40),
            ]:
                c.execute('''
                    INSERT INTO slot_sessions (gym_id, name, start_time, end_time, capacity)
                    VALUES (?, ?, ?, ?, ?)
                ''', (gym_id, name, start, end, cap))
                session_ids.append(c.lastrowid)
            log.write(f"3 sessions created: IDs {session_ids}\n")

            # Trainer session availability
            c.execute('INSERT INTO trainer_sessions (trainer_id, session_id) VALUES (?, ?)',
                      (trainer1_id, session_ids[0]))  # Ahmed: Morning
            c.execute('INSERT INTO trainer_sessions (trainer_id, session_id) VALUES (?, ?)',
                      (trainer1_id, session_ids[2]))  # Ahmed: Evening
            c.execute('INSERT INTO trainer_sessions (trainer_id, session_id) VALUES (?, ?)',
                      (trainer2_id, session_ids[1]))  # Ali: Afternoon
            c.execute('INSERT INTO trainer_sessions (trainer_id, session_id) VALUES (?, ?)',
                      (trainer2_id, session_ids[2]))  # Ali: Evening
            log.write("Trainer sessions: Ahmed->Morning+Evening, Ali->Afternoon+Evening\n")

            # ── Sample Class ───────────────────────────────────
            c.execute('''
                INSERT INTO classes (gym_id, trainer_id, name, description, class_type,
                                     capacity, day_of_week, start_time, end_time)
                VALUES (?, ?, 'Morning Yoga', 'Energizing yoga class', 'group', 20,
                        'Monday', '07:00', '08:00')
            ''', (gym_id, trainer1_id))
            log.write("Sample class created\n")

            conn.commit()
            log.write("\nCOMMITTED SUCCESSFULLY!\n")
            conn.close()

            log.write("\n" + "="*50 + "\n")
            log.write("System Admin : admin@gymdesk.com      / admin123\n")
            log.write("Gym Admin    : gymadmin@example.com    / password123\n")
            log.write("Trainer 1    : trainer@example.com     / password123\n")
            log.write("Trainer 2    : trainer2@example.com    / password123\n")
            log.write("Member 1     : member1@example.com     / password123\n")
            log.write("Member 2     : member2@example.com     / password123\n")

        except Exception as e:
            log.write(f"\nERROR: {e}\n")
            log.write(traceback.format_exc())


if __name__ == '__main__':
    seed()
