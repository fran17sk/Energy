"""Bandeja persistente; el correo sólo se marca enviado si el backend lo acepta."""
import logging
from pathlib import Path
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from .models import Notificacion

logger = logging.getLogger(__name__)


def encolar(tramite, evento, asunto, mensaje, documento=None, user=None):
    notificacion = Notificacion.objects.create(
        tramite=tramite, canal='EMAIL', asunto=asunto, mensaje=mensaje,
        destinatario=tramite.titular_email, evento=evento, documento=documento, usuario=user,
    )
    transaction.on_commit(lambda: enviar(notificacion.pk))
    return notificacion


def enviar(pk):
    try:
        with transaction.atomic():
            notificacion = Notificacion.objects.select_for_update(of=('self',)).get(pk=pk)
            if notificacion.estado == 'ENVIADA':
                return True
            notificacion.intentos += 1
            try:
                email = EmailMessage(
                    subject=f'{notificacion.tramite.circuito_display} · {notificacion.asunto}',
                    body=((f'Hola {notificacion.tramite.solicitante_nombre or notificacion.tramite.titular_nombre},' if (notificacion.tramite.solicitante_nombre or notificacion.tramite.titular_nombre) else 'Hola,') + f'\n\n{notificacion.mensaje}\n\n'
                          f'Circuito: {notificacion.tramite.circuito_display}\nNúmero de trámite para consulta: {notificacion.tramite.codigo_consulta}\n'
                          'Guardá este código en un lugar seguro y no lo compartas. '
                          'Para consultar ingresá al sitio GGER con este código, tu NIS y el DNI / CUIT del titular.\n'),
                    to=[notificacion.destinatario],
                )
                if notificacion.documento_id:
                    documento = notificacion.documento
                    with documento.archivo.open('rb') as archivo:
                        extension = Path(documento.archivo.name).suffix
                        email.attach(f'{"Obra de nexo - " if notificacion.tramite.es_nexo else ""}{documento.get_tipo_display()}{extension}', archivo.read())
                if email.send(fail_silently=False) != 1:
                    raise RuntimeError('El backend no aceptó el correo.')
            except Exception:
                # No imprimir direcciones, códigos, documentos ni credenciales en logs.
                notificacion.estado = 'ERROR'
                notificacion.save(update_fields=['estado', 'intentos'])
                logger.warning('Fallo de envío de la notificación %s; se conserva para reintento.', pk)
                return False
            notificacion.estado = 'ENVIADA'
            notificacion.enviado_en = timezone.now()
            notificacion.save(update_fields=['estado', 'intentos', 'enviado_en'])
            from apps.tramites.services import historial, auditar, bloquear_tramite, habilitar_proyectos
            tramite = bloquear_tramite(notificacion.tramite_id)
            auditar(tramite, 'CORREO_ENVIADO', notificacion.usuario, evento=notificacion.evento,
                    notificacion=notificacion.pk)
            if (notificacion.evento == 'RESPUESTA' and tramite.etapa_actual.codigo == 'respuesta-factibilidad'
                    and tramite.estado_actual == 'PENDIENTE_ENVIO'):
                historial(tramite, 'ENVIADA', notificacion.usuario, 'Respuesta de factibilidad enviada por correo al cliente.')
                auditar(tramite, 'RESPUESTA_ENVIADA', notificacion.usuario)
                habilitar_proyectos(tramite, notificacion.usuario)
            elif (notificacion.evento == 'CONVOCATORIA' and tramite.etapa_actual.codigo == 'firma-contrato'
                    and tramite.estado_actual == 'PENDIENTE_ENVIO'):
                tramite.estado_actual = 'CONVOCADO'
                tramite.save()
            return True
    except Exception:
        logger.exception('No se pudo procesar la notificación %s.', pk)
        return False
