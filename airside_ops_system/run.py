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
    """Create the default admin user."""
    from app.models.user import User
    admin = User(
        username='admin',
        email='admin@airside.entebbe.go.ug',
        full_name='System Administrator',
        role='admin',
        badge_number='EBB-0001',
        department='Airside Operations',
        is_active=True
    )
    admin.set_password('Admin@2025!')
    db.session.add(admin)
    db.session.commit()
    print("Admin user created. Username: admin, Password: Admin@2025!")
    print("IMPORTANT: Change the password immediately after first login.")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=app.config.get('DEBUG', False))
