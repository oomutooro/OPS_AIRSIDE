from app import create_app, db
from app.models.user import User
from app.models.reference import Company


def test_user_password_hashing():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        user = User(
            username='tester',
            email='tester@example.com',
            full_name='Test User',
            role='viewer',
            is_active=True,
        )
        user.set_password('TestPass123!')
        db.session.add(user)
        db.session.commit()

        assert user.check_password('TestPass123!')
        assert not user.check_password('wrong')


def test_company_creation():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        company = Company(name='NAS', company_type='GHA', is_active=True)
        db.session.add(company)
        db.session.commit()
        assert company.id is not None
