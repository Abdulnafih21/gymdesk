import sqlite3, os

db_path = os.path.join(r'c:\Users\abdul\projects\gymdesk1', 'gymdesk.db')
out = os.path.join(r'c:\Users\abdul\projects\gymdesk1', 'db_check.txt')

with open(out, 'w') as f:
    f.write(f"DB exists: {os.path.exists(db_path)}\n")
    if not os.path.exists(db_path):
        f.write("No database file found!\n")
    else:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        tables = [t['name'] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        f.write(f"Tables: {tables}\n\n")
        for t in tables:
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0]
                f.write(f"  {t}: {count} rows\n")
            except Exception as e:
                f.write(f"  {t}: ERROR - {e}\n")
        f.write("\nUsers:\n")
        for u in conn.execute("SELECT email, role FROM users ORDER BY role").fetchall():
            f.write(f"  {u['email']} ({u['role']})\n")
        f.write("\nTrainer Sessions:\n")
        try:
            for ts in conn.execute("""
                SELECT u.full_name, ss.name as session_name 
                FROM trainer_sessions ts 
                JOIN trainers t ON ts.trainer_id = t.id 
                JOIN users u ON t.user_id = u.id 
                JOIN slot_sessions ss ON ts.session_id = ss.id
            """).fetchall():
                f.write(f"  {ts['full_name']} -> {ts['session_name']}\n")
        except Exception as e:
            f.write(f"  ERROR: {e}\n")
        f.write("\nMember-Trainer:\n")
        try:
            for mt in conn.execute("""
                SELECT u1.full_name as member, u2.full_name as trainer
                FROM member_trainer mt
                JOIN members m ON mt.member_id = m.id
                JOIN users u1 ON m.user_id = u1.id
                JOIN trainers t ON mt.trainer_id = t.id
                JOIN users u2 ON t.user_id = u2.id
            """).fetchall():
                f.write(f"  {mt['member']} -> {mt['trainer']}\n")
        except Exception as e:
            f.write(f"  ERROR: {e}\n")
        conn.close()
    f.write("\nDONE\n")
