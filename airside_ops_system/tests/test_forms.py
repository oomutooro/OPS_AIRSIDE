from app import create_app, db
from app.models.user import User
from app.models.form import FormTemplate, FormSubmission


def test_form_submission_create():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        user = User(
            username='inspector1',
            email='inspector1@example.com',
            full_name='Inspector One',
            role='inspector',
            is_active=True,
        )
        user.set_password('Pass123!')
        db.session.add(user)

        template = FormTemplate(form_number=1, title='Form 1', category='inspection')
        db.session.add(template)
        db.session.commit()

        sub = FormSubmission(
            form_template_id=template.id,
            status='submitted',
            submitted_by_user_id=user.id,
            location_ref='Apron 1',
            data={'score': 5},
        )
        db.session.add(sub)
        db.session.commit()

        assert sub.id is not None
        assert sub.status == 'submitted'
