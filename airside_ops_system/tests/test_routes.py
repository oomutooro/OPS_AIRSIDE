from app import create_app, db
from app.models.user import User


def login(client, username='admin', password='Admin@2025!'):
    return client.post('/auth/login', data={
        'username': username,
        'password': password,
    }, follow_redirects=True)


def test_dashboard_requires_login():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        client = app.test_client()
        resp = client.get('/')
        assert resp.status_code in (302, 401)


def test_login_page_loads():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        client = app.test_client()
        resp = client.get('/auth/login')
        assert resp.status_code == 200
