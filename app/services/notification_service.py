"""
Notification service: in-app, email, and real-time socket events.
"""
from flask import current_app
from flask_mail import Message
from app import db, mail, socketio
from app.models.user import Notification


class NotificationService:
    """Send and persist notifications."""

    @staticmethod
    def create_in_app(user_id: int, title: str, message: str, notification_type='info', link_url=None):
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            link_url=link_url,
        )
        db.session.add(notif)
        db.session.commit()

        socketio.emit('notification', {
            'user_id': user_id,
            'title': title,
            'message': message,
            'type': notification_type,
            'link_url': link_url,
        }, room=f'user_{user_id}')

        return notif

    @staticmethod
    def send_email(to_email: str, subject: str, body: str):
        if not to_email:
            return False
        try:
            msg = Message(subject=subject, recipients=[to_email], body=body)
            mail.send(msg)
            return True
        except Exception as exc:
            current_app.logger.error(f'Email send failed: {exc}')
            return False
