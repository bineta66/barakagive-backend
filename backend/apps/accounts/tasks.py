from celery import shared_task
from django.conf import settings
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException


@shared_task
def send_invitation_email(
    recipient_email,
    first_name,
    activation_link,
    temporary_password=None,
    subject_override=None,
    html_override=None,
):

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = settings.BREVO_API_KEY

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    subject = subject_override or "Activation de votre compte BarakaGive"
    if html_override:
        html = html_override
    else:
        html = f"""
        <h2>Bienvenue sur BarakaGive</h2>

        <p>Bonjour {first_name},</p>

        <p>Votre demande d'inscription a bien été enregistrée.</p>
        {f'<p><strong>Mot de passe temporaire :</strong> {temporary_password}</p>' if temporary_password else ''}

        <p>Cliquez sur le lien ci-dessous pour activer votre compte :</p>

        <p>
            <a href="{activation_link}"
               style="background:#744D03; color:white; padding:12px 20px; text-decoration:none; border-radius:6px;">
               Activer mon compte
            </a>
        </p>

        <p>Ce lien est valable pendant 24 heures.</p>

        <p>L'équipe BarakaGive</p>
        """

    sender = {
        "name": "BarakaGive360",
        "email": settings.DEFAULT_FROM_EMAIL,
    }

    to = [{
        "email": recipient_email,
        "name": first_name,
    }]

    email_data = sib_api_v3_sdk.SendSmtpEmail(
        sender=sender,
        to=to,
        subject=subject,
        html_content=html,
    )

    try:
        response = api_instance.send_transac_email(email_data)
        print("BREVO OK :", response)
        return str(response)

    except ApiException as e:
        print("BREVO ERROR :", e)
        raise
