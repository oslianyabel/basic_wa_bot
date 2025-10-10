import asyncio
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, Optional

import aiohttp
import aiosmtplib
from config import config
from logging_conf import logger


async def send_email(
    email_to: str,
    subject: str,
    body: str,
    sender=config.EMAIL,
    password=config.EMAIL_PASSWORD,
    host=config.EMAIL_HOST,
    port: int = 465,
    use_tls: bool = True,
    pdf_path_list: Optional[list[str]] = None,
):
    """
    Envía un correo electrónico de forma asíncrona con opción a adjuntar archivos.

    Args:
        email_to: Dirección del destinatario
        subject: Asunto del correo
        body: Cuerpo del mensaje (puede ser HTML o texto plano)
        sender: Remitente (por defecto julia.m@jumo.cat)
        password: Contraseña del remitente
        host: Servidor SMTP (por defecto smtp.jumo.cat)
        port: Puerto SMTP (por defecto 587)
        use_tls: Usar TLS (por defecto True)
        pdf_path_list: Rutas a los archivos que se desean adjuntar (opcional)
    """
    if config.ENV_STATE == "test":
        return True

    message = EmailMessage()
    message["From"] = sender
    message["To"] = email_to
    message["Subject"] = subject
    message.set_content(body)

    if pdf_path_list:
        try:
            for pdf_path in pdf_path_list:
                with open(pdf_path, "rb") as file:
                    file_data = file.read()
                    file_name = os.path.basename(pdf_path)

                message.add_attachment(
                    file_data,
                    maintype="application",
                    subtype="pdf",
                    filename=file_name,
                )
                logger.info(f"Archivo adjunto {file_name} añadido al correo")

        except Exception as e:
            logger.error(f"Error al adjuntar el archivo: {str(e)}")
            return False

    try:
        await aiosmtplib.send(
            message,
            hostname=host,
            port=port,
            username=sender,
            password=password,
            use_tls=use_tls,
        )
        logger.info(f"Correo enviado a {email_to}")
        return True

    except Exception as exc:
        logger.error(f"Error al enviar el correo: {str(exc)}")
        return False


async def send_whatsapp_message(body, to, media=None):
    """Send WhatsApp message using Meta's WhatsApp Business API"""
    if config.ENV_STATE == "test":
        return True

    try:
        logger.debug(f"Enviando mensaje de WhatsApp a {to}")

        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        url = f"https://graph.facebook.com/v22.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"

        if media:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "image",
                "image": {"link": media, "caption": body if body else ""},
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": body},
            }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 200:
                    logger.debug(f"Mensaje enviado exitosamente a {to}")
                    return True
                else:
                    logger.error(f"Error enviando mensaje: {data}")
                    return False

    except Exception as exc:
        msg = f"Error enviando mensaje de WhatsApp a {to}"
        if media:
            msg += f"\nmedia_url: {media}"
        logger.error(msg + f"\nError: {exc}")
        return False


async def send_whatsapp_message_with_retry(body, to, media=None):
    """Send WhatsApp message with retry logic using Meta's API"""
    if config.ENV_STATE == "test":
        return True

    retries = 3
    delay = 0.5  # 500ms delay

    for attempt in range(1, retries + 1):
        try:
            logger.debug(f"Enviando mensaje de WhatsApp a {to} (intento {attempt})")

            headers = {
                "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            }

            url = f"https://graph.facebook.com/v22.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"

            if media:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "image",
                    "image": {"link": media, "caption": body if body else ""},
                }
            else:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": body},
                }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        logger.debug(f"Mensaje enviado exitosamente a {to}")
                        return True
                    else:
                        data = await resp.json(content_type=None)
                        raise Exception(f"API Error: {data}")

        except Exception as exc:
            logger.warning(f"Attempt {attempt} failed: {exc}")
            if attempt < retries:
                logger.warning(f"Retrying in {delay * 1000}ms...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Error enviando mensaje de WhatsApp a {to}. Error: {exc}")
                return False

    return False


# New helper to mark messages as read via WhatsApp Cloud API
async def mark_whatsapp_message_as_read(message_id: str) -> bool:
    """Mark an incoming WhatsApp message as read using Meta's API.

    Args:
        message_id: The WAMID of the incoming message to mark as read

    Returns:
        bool: True if successfully marked as read, False otherwise
    """
    if config.ENV_STATE == "test":
        return True

    try:
        headers = {
            "Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

        url = f"https://graph.facebook.com/v22.0/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    logger.debug(f"Mensaje {message_id} marcado como leído")
                    return True
                else:
                    data = await resp.json(content_type=None)
                    logger.error(f"No se pudo marcar como leído {message_id}: {data}")
                    return False
    except Exception as exc:
        logger.error(f"Error marcando como leído {message_id}: {exc}")
        return False


# Backward compatibility functions
async def send_twilio_message(body, to, media=None):
    """Backward compatibility wrapper for send_whatsapp_message"""
    return await send_whatsapp_message(body, to, media)


async def send_twilio_message2(body, to, media=None):
    """Backward compatibility wrapper for send_whatsapp_message_with_retry"""
    return await send_whatsapp_message_with_retry(body, to, media)


async def notify_lead(partner, resume, client_email, lead):
    subject = "He creado un lead en el Odoo de Orion desde WhatsApp"
    body = "=" * 50
    body += f"\nNombre del cliente: {partner['name']}\n"
    body += f"Teléfono del cliente: {partner['phone']}\n"
    body += f"Email del cliente: {client_email}\n"
    body += f"ID del lead: {lead[0][0]}\n"
    body += f"Nombre del lead: {lead[0][1]}\n"
    body += f"Resumen de la conversación: \n{resume}"

    if config.ENV_STATE == "prod":
        await send_email(config.ADMIN_EMAIL, subject, body)  # type: ignore

    await send_email(config.DEV_EMAIL, subject, body)  # type: ignore


async def notify_sale_order(email, msg, pdf_path=None):
    args = {
        "body": msg,
    }
    if pdf_path:
        args["pdf_path_list"] = [pdf_path]

    await send_email(
        email_to=email,
        subject="Se ha creado un presupuesto para usted",
        **args,
    )

    logger.info(f"{email} ha sido notificado de su pedido")


def send_email_sync(email_to, subject, body, pdf_path=None):
    if config.ENV_STATE == "test":
        return True

    logger.debug(f"Enviando correo a {email_to} ...")
    EMAIL = config.EMAIL
    PASSWORD = config.EMAIL_PASSWORD
    HOST = config.EMAIL_HOST

    email = EmailMessage()
    email["from"] = EMAIL
    email["to"] = email_to
    email["subject"] = subject
    email.set_content(body)

    if pdf_path and os.path.isfile(pdf_path):
        with open(pdf_path, "rb") as pdf_file:
            pdf_data = pdf_file.read()
            email.add_attachment(
                pdf_data,
                maintype="application",
                subtype="pdf",
                filename=os.path.basename(pdf_path),
            )

    try:
        with smtplib.SMTP(HOST, port=587) as smtp:  # type: ignore
            smtp.starttls()
            smtp.login(EMAIL, PASSWORD)  # type: ignore
            smtp.sendmail(EMAIL, email_to, email.as_string())  # type: ignore

        logger.info(f"Correo enviado! Destinatario: {email_to}")
        return True

    except Exception as exc:
        logger.error(f"Error enviando correo a {email_to}: {exc}")
        return False
