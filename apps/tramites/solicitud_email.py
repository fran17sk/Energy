"""Datos de la solicitud persistidos; adjuntos iniciales sólo por correo."""
from pathlib import Path
import socket
import smtplib
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string
from .solicitud_forms import TECNOLOGIAS, CONEXIONES

ADJUNTOS = [('formulario_digital', 'formulario-digital'), ('dni_titular', 'dni-titular'),
            ('dni_apoderado', 'dni-apoderado'), ('poder_apoderado', 'poder-apoderado')]


def secciones_solicitud(data):
    personas = []
    for prefix, titulo in [('propietario', 'Datos del propietario del inmueble'), ('titular', 'Datos del titular del suministro')]:
        humana = data[f'{prefix}_tipo'] == 'HUMANA'
        personas.append({'titulo': titulo, 'campos': [
            {'etiqueta': 'Tipo de persona', 'valor': 'Persona humana' if humana else 'Persona jurídica'},
            {'etiqueta': 'Nombre completo / Razón social', 'valor': data[f'{prefix}_nombre']},
            {'etiqueta': 'DNI' if humana else 'CUIT', 'valor': data[f'{prefix}_dni' if humana else f'{prefix}_cuit']},
        ]})
    grupos = [
        ('Datos del suministro', [('NIS', data['nis']), ('Potencia contratada con EDESA (kW)', str(data['potencia_contratada_kw'])),
            ('Catastro N.º', data['catastro']), ('Departamento', data['departamento'])]),
        ('Características del equipamiento GGER', [('Tecnología', dict(TECNOLOGIAS)[data['tecnologia']]),
            ('Tipo de conexión', dict(CONEXIONES)[data['tipo_conexion']]),
            ('Potencia efectiva a plena carga inyectada en corriente alterna (kW)', str(data['potencia_inyectada_kw'])),
            ('Coordenadas del pilar de medición', data['coordenadas_pilar'])]),
        ('Datos del solicitante', [('Actúa como', 'Apoderado' if data['solicitante_condicion'] == 'APODERADO' else 'Titular del suministro'),
            ('Nombre completo', data['solicitante_nombre']), ('DNI', data['solicitante_dni']),
            ('Celular', data['solicitante_celular']), ('Dirección electrónica para notificaciones', data['solicitante_email'])]),
    ]
    return personas + [{'titulo': titulo, 'campos': [{'etiqueta': k, 'valor': v} for k, v in campos]} for titulo, campos in grupos]


class ConfiguracionSolicitudError(ImproperlyConfigured):
    """Mensaje de configuración controlado y apto para mostrar al usuario."""


def error_publico_envio(exc):
    """Diagnóstico útil sin mostrar credenciales ni respuestas del servidor SMTP."""
    if isinstance(exc, ConfiguracionSolicitudError):
        return str(exc)
    if isinstance(exc, socket.gaierror):
        return 'No se pudo resolver el servidor SMTP. Revisá EMAIL_HOST y la conexión DNS del equipo.'
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return 'El servidor rechazó la autenticación. Revisá EMAIL_HOST_USER y EMAIL_HOST_PASSWORD (contraseña de aplicación).'
    if isinstance(exc, (TimeoutError, ConnectionError, smtplib.SMTPConnectError)):
        return 'No se pudo conectar al servidor de correo. Revisá la conexión, EMAIL_HOST, EMAIL_PORT y EMAIL_USE_TLS.'
    return 'El correo no pudo ser enviado. Contactá al administrador para revisar el servicio SMTP.'


def validar_configuracion_envio():
    destino = getattr(settings, 'EDESA_SOLICITUD_EMAIL', '').strip()
    if not destino:
        raise ConfiguracionSolicitudError('Falta configurar EDESA_SOLICITUD_EMAIL en el archivo .env y reiniciar la aplicación.')
    try:
        validate_email(destino)
    except ValidationError:
        raise ConfiguracionSolicitudError('EDESA_SOLICITUD_EMAIL debe contener una dirección de correo válida.') from None
    if settings.EMAIL_BACKEND not in {'django.core.mail.backends.smtp.EmailBackend', 'django.core.mail.backends.locmem.EmailBackend'}:
        raise ConfiguracionSolicitudError('Este envío requiere un backend SMTP sin escritura de contenido en archivos o consola.')
    return destino


def enviar_solicitud(data, numero):
    destino = validar_configuracion_envio()
    contexto = {'secciones': secciones_solicitud(data),
        'documentos': [nombre for campo, nombre in ADJUNTOS if data.get(campo)],
        'contacto': data['solicitante_email'], 'numero': numero}
    mensaje = EmailMultiAlternatives(
        subject='Solicitud de factibilidad GGER',
        body=render_to_string('email/solicitud_factibilidad.txt', contexto),
        from_email=settings.DEFAULT_FROM_EMAIL, to=[destino], reply_to=[data['solicitante_email']],
    )
    mensaje.attach_alternative(render_to_string('email/solicitud_factibilidad.html', contexto), 'text/html')
    for campo, nombre in ADJUNTOS:
        archivo = data.get(campo)
        if archivo:
            archivo.seek(0)
            extension = Path(archivo.name).suffix.lower()
            tipo = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}[extension]
            mensaje.attach(nombre + extension, archivo.read(), tipo)
    if mensaje.send(fail_silently=False) != 1:
        raise RuntimeError('El servidor de correo no aceptó la solicitud.')


@transaction.atomic
def registrar_y_enviar_solicitud(data):
    from .models import Tramite
    from .services import iniciar
    documento = data['titular_dni'] if data['titular_tipo'] == 'HUMANA' else data['titular_cuit']
    campos = {nombre: data[nombre] for nombre in (
        'propietario_tipo', 'propietario_nombre', 'propietario_dni', 'propietario_cuit',
        'titular_tipo', 'titular_nombre', 'nis', 'catastro', 'departamento',
        'potencia_contratada_kw', 'tecnologia', 'tipo_conexion', 'potencia_inyectada_kw',
        'coordenadas_pilar', 'solicitante_condicion', 'solicitante_nombre',
        'solicitante_dni', 'solicitante_celular')}
    tramite = Tramite.objects.create(**campos, titular_email=data['solicitante_email'],
        titular_dni_cuit=documento, titular_telefono=data['solicitante_celular'],
        presentacion_por_correo=True, consulta_documento_hash=make_password(documento))
    enviar_solicitud(data, tramite.numero)
    iniciar(tramite)
    return tramite
