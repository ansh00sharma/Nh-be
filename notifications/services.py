import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from core.observability.decorators import traced


logger = logging.getLogger(__name__)


@traced("notification.email.send")
def send_notification_email(user, subject, message, template_name=None, context=None):
    if not getattr(user, "email", None):
        return False

    try:
        email = EmailMultiAlternatives(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
        if template_name:
            html_message = render_to_string(template_name, context or {})
            email.attach_alternative(html_message, "text/html")

        email.send(fail_silently=False)
    except Exception:
        logger.exception("Failed to send notification email to user_id=%s", user.id)
        return False

    return True
