"""Transactional email over plain SMTP (MailerSend in production, Mailpit in development;
decision 2026-10-19). Only invites and password resets are sent. Messages are Arabic first, then
French."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from sabq.settings import Settings


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    body: str


def send(settings: Settings, mail: Mail) -> None:
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = mail.to
    message["Subject"] = mail.subject
    message.set_content(mail.body)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_tls == "ssl" else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_tls == "starttls":
            smtp.starttls()
        if settings.smtp_user:
            password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
            smtp.login(settings.smtp_user, password)
        smtp.send_message(message)


def invite_mail(settings: Settings, to: str, organisation: str, token: str) -> Mail:
    link = f"{settings.public_base_url.rstrip('/')}/accept-invite?token={token}"
    hours = int(settings.invite_ttl_hours)
    return Mail(
        to=to,
        subject="دعوة إلى سبق · Invitation à Sabq",
        body=(
            f"تمت دعوتك للانضمام إلى {organisation} على سبق.\n"
            f"اختر كلمة المرور من هذا الرابط (صالح {hours} ساعة، لمرة واحدة):\n{link}\n\n"
            f"Vous êtes invité(e) à rejoindre {organisation} sur Sabq.\n"
            f"Choisissez votre mot de passe avec ce lien (valable {hours} h, une seule fois) :\n"
            f"{link}\n"
        ),
    )


def reset_mail(settings: Settings, to: str, token: str) -> Mail:
    link = f"{settings.public_base_url.rstrip('/')}/reset-password?token={token}"
    return Mail(
        to=to,
        subject="إعادة تعيين كلمة المرور · Réinitialisation du mot de passe",
        body=(
            f"لإعادة تعيين كلمة المرور، افتح هذا الرابط (صالح ساعة واحدة، لمرة واحدة):\n{link}\n"
            "إذا لم تطلب ذلك، تجاهل هذه الرسالة.\n\n"
            "Pour réinitialiser votre mot de passe, ouvrez ce lien "
            "(valable 1 h, une seule fois) :\n"
            f"{link}\nSi vous n'avez rien demandé, ignorez ce message.\n"
        ),
    )
