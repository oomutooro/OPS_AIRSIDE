"""Initialize database with seed data and user accounts."""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.utils.seed_data import seed_all

app = create_app('development')

with app.app_context():
    # Create tables
    db.create_all()
    print("✓ Database tables created")
    
    # Seed reference data
    seed_all(db)
    print("✓ Reference data seeded")
    
    # Create users
    users_to_create = [
        {'username': 'admin', 'email': 'admin@airside.entebbe.go.ug', 'full_name': 'System Administrator', 'role': 'admin', 'badge_number': 'EBB-0001', 'department': 'Airside Operations', 'password': 'Admin@2025!'},
        {'username': 'supervisor', 'email': 'supervisor@airside.entebbe.go.ug', 'full_name': 'Operations Supervisor', 'role': 'supervisor', 'badge_number': 'EBB-0002', 'department': 'Airside Operations', 'password': 'Supervisor@2025!'},
        {'username': 'operator', 'email': 'operator@airside.entebbe.go.ug', 'full_name': 'Airside Operator', 'role': 'operator', 'badge_number': 'EBB-0003', 'department': 'Airside Operations', 'password': 'Operator@2025!'},
        {'username': 'inspector', 'email': 'inspector@airside.entebbe.go.ug', 'full_name': 'Safety Inspector', 'role': 'inspector', 'badge_number': 'EBB-0004', 'department': 'Safety & Compliance', 'password': 'Inspector@2025!'},
        {'username': 'auditor', 'email': 'auditor@airside.entebbe.go.ug', 'full_name': 'System Auditor', 'role': 'auditor', 'badge_number': 'EBB-0005', 'department': 'Audit & Compliance', 'password': 'Auditor@2025!'},
        {'username': 'viewer', 'email': 'viewer@airside.entebbe.go.ug', 'full_name': 'Dashboard Viewer', 'role': 'viewer', 'badge_number': 'EBB-0006', 'department': 'Airside Operations', 'password': 'Viewer@2025!'},
    ]
    
    for user_data in users_to_create:
        password = user_data.pop('password')
        existing = User.query.filter_by(username=user_data['username']).first()
        if existing:
            print(f"  User '{user_data['username']}' already exists")
            continue
        user = User(**user_data, is_active=True)
        user.set_password(password)
        db.session.add(user)
    
    db.session.commit()
    print("✓ User accounts created")
    
    print("\n" + "="*60)
    print("LOGIN CREDENTIALS")
    print("="*60)
    print("ADMIN:      admin / Admin@2025!")
    print("SUPERVISOR: supervisor / Supervisor@2025!")
    print("OPERATOR:   operator / Operator@2025!")
    print("INSPECTOR:  inspector / Inspector@2025!")
    print("AUDITOR:    auditor / Auditor@2025!")
    print("VIEWER:     viewer / Viewer@2025!")
    print("="*60)
    print("⚠️  Change all passwords after first login!")
    print("="*60)
