from flask import Blueprint, render_template, request
from database import get_db

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def landing():
    db = get_db()

    # Global stats
    total_gyms = db.execute('SELECT COUNT(*) as c FROM gyms WHERE is_approved = 1').fetchone()['c']
    total_members = db.execute('SELECT COUNT(*) as c FROM members').fetchone()['c']
    total_trainers = db.execute('SELECT COUNT(*) as c FROM trainers WHERE is_approved = 1').fetchone()['c']
    total_classes = db.execute('SELECT COUNT(*) as c FROM classes WHERE is_active = 1').fetchone()['c']

    # Featured gyms (latest 6)
    featured_gyms = db.execute('''
        SELECT g.*, u.full_name as owner_name,
               (SELECT COUNT(*) FROM members m WHERE m.gym_id = g.id) as member_count,
               (SELECT COUNT(*) FROM trainers t WHERE t.gym_id = g.id AND t.is_approved = 1) as trainer_count
        FROM gyms g
        JOIN users u ON g.owner_id = u.id
        WHERE g.is_approved = 1
        ORDER BY g.created_at DESC
        LIMIT 6
    ''').fetchall()

    db.close()

    return render_template('public/landing.html',
                           total_gyms=total_gyms,
                           total_members=total_members,
                           total_trainers=total_trainers,
                           total_classes=total_classes,
                           featured_gyms=featured_gyms)


@public_bp.route('/gyms')
def gym_list():
    db = get_db()
    search = request.args.get('search', '').strip()
    city = request.args.get('city', '').strip()

    query = '''
        SELECT g.*, u.full_name as owner_name,
               (SELECT COUNT(*) FROM members m WHERE m.gym_id = g.id) as member_count,
               (SELECT COUNT(*) FROM trainers t WHERE t.gym_id = g.id AND t.is_approved = 1) as trainer_count
        FROM gyms g
        JOIN users u ON g.owner_id = u.id
        WHERE g.is_approved = 1
    '''
    params = []

    if search:
        query += " AND (g.name LIKE ? OR g.city LIKE ? OR g.description LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if city:
        query += " AND g.city LIKE ?"
        params.append(f'%{city}%')

    query += " ORDER BY g.created_at DESC"

    gyms = db.execute(query, params).fetchall()

    # Get distinct cities for filter
    cities = db.execute('''
        SELECT DISTINCT city FROM gyms WHERE is_approved = 1 AND city IS NOT NULL AND city != ''
        ORDER BY city
    ''').fetchall()

    db.close()

    return render_template('public/gym_list.html', gyms=gyms, cities=cities,
                           search=search, selected_city=city)
