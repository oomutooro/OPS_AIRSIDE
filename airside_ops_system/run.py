"""
Airside Operations Management System
Entebbe International Airport (HUEN/EBB)
Entry point for the application.
"""
import os
from app import create_app, db
from app.models.user import User, Role
from app.models.reference import Company, ParkingStand, AirsideLocation, AirsideVehicle
from app.models.incident import ViolationType

app = create_app(os.getenv('FLASK_ENV', 'development'))


@app.shell_context_processor
def make_shell_context():
    """Flask shell context for debugging."""
    return {
        'db': db,
        'app': app,
        'User': User,
        'Role': Role,
        'Company': Company,
    }


@app.cli.command('seed-db')
def seed_database():
    """Seed the database with initial reference data."""
    from app.utils.seed_data import seed_all
    seed_all(db)
    print("Database seeded successfully.")


@app.cli.command('create-admin')
def create_admin():
    """Create default users for all roles."""
    from app.models.user import User
    
    users_to_create = [
        {
            'username': 'admin',
            'email': 'admin@airside.entebbe.go.ug',
            'full_name': 'System Administrator',
            'role': 'admin',
            'badge_number': 'EBB-0001',
            'department': 'Airside Operations',
            'password': 'Admin@2025!'
        },
        {
            'username': 'supervisor',
            'email': 'supervisor@airside.entebbe.go.ug',
            'full_name': 'Operations Supervisor',
            'role': 'supervisor',
            'badge_number': 'EBB-0002',
            'department': 'Airside Operations',
            'password': 'Supervisor@2025!'
        },
        {
            'username': 'operator',
            'email': 'operator@airside.entebbe.go.ug',
            'full_name': 'Airside Operator',
            'role': 'operator',
            'badge_number': 'EBB-0003',
            'department': 'Airside Operations',
            'password': 'Operator@2025!'
        },
        {
            'username': 'inspector',
            'email': 'inspector@airside.entebbe.go.ug',
            'full_name': 'Safety Inspector',
            'role': 'inspector',
            'badge_number': 'EBB-0004',
            'department': 'Safety & Compliance',
            'password': 'Inspector@2025!'
        },
        {
            'username': 'auditor',
            'email': 'auditor@airside.entebbe.go.ug',
            'full_name': 'System Auditor',
            'role': 'auditor',
            'badge_number': 'EBB-0005',
            'department': 'Audit & Compliance',
            'password': 'Auditor@2025!'
        },
        {
            'username': 'viewer',
            'email': 'viewer@airside.entebbe.go.ug',
            'full_name': 'Dashboard Viewer',
            'role': 'viewer',
            'badge_number': 'EBB-0006',
            'department': 'Airside Operations',
            'password': 'Viewer@2025!'
        },
    ]
    
    for user_data in users_to_create:
        password = user_data.pop('password')
        existing = User.query.filter_by(username=user_data['username']).first()
        if existing:
            print(f"User '{user_data['username']}' already exists. Skipping.")
            continue
        
        user = User(**user_data, is_active=True)
        user.set_password(password)
        db.session.add(user)
    
    db.session.commit()
    
    print("\n" + "="*60)
    print("DEFAULT USER ACCOUNTS CREATED")
    print("="*60)
    for user_data in users_to_create:
        print(f"Role: {user_data['role'].upper()}")
        print(f"  Username: {user_data['username']}")
        print(f"  Password: {user_data['username'].capitalize()}@2025!")
        print(f"  Email: {user_data['email']}")
        print()
    print("="*60)
    print("⚠️  IMPORTANT: Change all passwords after first login!")
    print("="*60)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=app.config.get('DEBUG', False))
