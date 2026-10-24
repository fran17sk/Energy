"""Transiciones atómicas y autorización del circuito. Toda actuación deja auditoría."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from apps.workflow.models import Etapa, TramiteEtapa
from apps.auditoria.models import Auditoria
from .models import Tramite, DocumentoTramite


HISTORIAL_COMPLETO = ['RECIBIDO', 'ENVIADA', 'PREVISADO', 'VISADO', 'APROBADO', 'FINALIZADO']

RECEPCIONES = {
    'ingreso-factibilidad': 'respuesta-factibilidad',
    'ingreso-copaipa': 'sellado-copaipa',
    'ingreso-secretaria': 'dictamen-expediente',
    'ingreso-enresp': 'resolucion-enresp',
}
ACCIONES = {
    'respuesta-factibilidad': [('respuesta', 'Adjuntar y enviar respuesta de factibilidad')],
    'previsado-proyecto-ejecutivo': [('previsar', 'Marcar previsado y enviar a COPAIPA')],
    'sellado-copaipa': [('copaipa', 'Adjuntar dictamen y visar por COPAIPA')],
    'dictamen-expediente': [('expediente', 'Asociar expediente administrativo')],
    'resolucion-enresp': [('resolucion', 'Adjuntar resolución y aprobar')],
    'firma-contrato': [('convocar', 'Notificar al titular para firmar contrato')],
    'inspeccion': [('programar', 'Programar inspección')],
    'conexion-red': [('conectar', 'Registrar conexión y finalizar trámite')],
}


def institucional(user):
    return user.is_authenticated and user.is_active and (user.is_superuser or bool(user.organismo_id))


def puede_actuar(user, tramite):
    # El rol de consulta no modifica ni acusa recepción en nombre del organismo.
    return (institucional(user) and bool(user.organismo_id) and user.rol in {'ADMIN', 'RESP', 'OPER'}
            and user.organismo_id == tramite.organismo_actual_id
            and tramite.estado_actual != Tramite.Estado.FINALIZADO)


def acciones_disponibles(tramite):
    codigo = tramite.etapa_actual.codigo if tramite.etapa_actual_id else ''
    if tramite.estado_actual == Tramite.Estado.PENDIENTE_ENVIO:
        return []
    if codigo == 'dictamen-expediente' and tramite.expediente_administrativo:
        return [('dictamen', 'Adjuntar dictamen y aprobar sección de la Secretaría')]
    if codigo == 'firma-contrato' and tramite.estado_actual == Tramite.Estado.PENDIENTE:
        return []  # Primero se debe registrar la recepción final de EDESA.
    if codigo == 'firma-contrato' and tramite.estado_actual == Tramite.Estado.CONVOCADO:
        return [('contrato', 'Adjuntar contrato firmado')]
    if codigo == 'inspeccion' and tramite.estado_actual == Tramite.Estado.PROGRAMADA:
        return [('inspeccionar', 'Registrar inspección realizada')]
    return ACCIONES.get(codigo, [])


def auditar(tramite, accion, user=None, **detalle):
    cliente = accion in {'SOLICITUD_INICIADA', 'PROYECTO_ENVIADO'} and user is None
    detalle.update(organismo_usuario=user.organismo.sigla if user and user.organismo_id else None,
                   usuario_nombre=user.get_username() if user else (tramite.titular_nombre if cliente else 'Sistema'),
                   actor='CLIENTE' if cliente else ('INSTITUCIONAL' if user else 'SISTEMA'))
    Auditoria.objects.create(tramite=tramite, usuario=user, accion=accion, detalle=detalle)


def historial(tramite, estado, user=None, observacion=''):
    registro, _ = TramiteEtapa.objects.get_or_create(tramite=tramite, etapa=tramite.etapa_actual)
    registro.estado = estado
    registro.fecha_inicio = registro.fecha_inicio or timezone.now()
    registro.fecha_fin = timezone.now() if estado in HISTORIAL_COMPLETO else None
    registro.usuario = user
    registro.observacion = observacion
    registro.save()


def mover(tramite, codigo, estado=Tramite.Estado.PENDIENTE, user=None):
    etapa = Etapa.objects.select_related('organismo').get(codigo=codigo)
    tramite.etapa_actual = etapa
    tramite.organismo_actual = etapa.organismo
    tramite.estado_actual = estado
    tramite.save()
    historial(tramite, 'PENDIENTE', user)


@transaction.atomic
def iniciar(tramite):
    mover(tramite, 'ingreso-factibilidad')
    DocumentoTramite.objects.create(tramite=tramite, tipo='SOLICITUD', archivo=tramite.solicitud_factibilidad.name)
    auditar(tramite, 'SOLICITUD_INICIADA')
    from apps.notificaciones.services import encolar
    encolar(tramite, 'ALTA', 'Guardá tu número de trámite',
            'Tu solicitud de factibilidad fue registrada y enviada a EDESA. '
            'Guardá este número: junto con el NIS y el DNI / CUIT te permitirá consultar documentos y presentar tu proyecto ejecutivo.')


@transaction.atomic
def recibir(pk, user):
    tramite = Tramite.objects.select_for_update().get(pk=pk)
    if not puede_actuar(user, tramite) or not tramite.etapa_actual_id:
        return tramite
    codigo = tramite.etapa_actual.codigo
    if codigo in RECEPCIONES:
        historial(tramite, 'RECIBIDO', user, 'Recibido por el organismo al abrir el trámite.')
        auditar(tramite, 'RECIBIDO', user, etapa=codigo, organismo=tramite.organismo_actual.sigla)
        mover(tramite, RECEPCIONES[codigo], user=user)
        # La respuesta de factibilidad comienza pendiente; los demás dictámenes, recibidos.
        if codigo != 'ingreso-factibilidad':
            tramite.estado_actual = Tramite.Estado.RECIBIDO
            tramite.save()
    elif codigo == 'presentacion-proyecto-ejecutivo' and tramite.estado_actual == Tramite.Estado.PROYECTO_ENVIADO:
        historial(tramite, 'RECIBIDO', user, 'Proyecto ejecutivo recibido por EDESA.')
        auditar(tramite, 'PROYECTO_RECIBIDO', user)
        mover(tramite, 'previsado-proyecto-ejecutivo', Tramite.Estado.RECIBIDO, user)
    elif codigo == 'firma-contrato' and tramite.estado_actual == Tramite.Estado.PENDIENTE:
        tramite.estado_actual = Tramite.Estado.RECIBIDO
        tramite.save()
        historial(tramite, 'EN_PROCESO', user, 'Recibido en EDESA para firma del contrato.')
        auditar(tramite, 'RECIBIDO', user, etapa=codigo, organismo='EDESA')
    return tramite


def guardar_documento(tramite, tipo, archivo, user=None):
    return DocumentoTramite.objects.create(tramite=tramite, tipo=tipo, archivo=archivo, usuario=user)


@transaction.atomic
def presentar_proyecto(pk, archivo):
    tramite = Tramite.objects.select_for_update().get(pk=pk)
    if tramite.etapa_actual.codigo != 'presentacion-proyecto-ejecutivo' or tramite.estado_actual != Tramite.Estado.PENDIENTE_CLIENTE:
        raise ValidationError('El trámite no está esperando un proyecto ejecutivo o ya fue presentado.')
    guardar_documento(tramite, 'PROYECTO', archivo)
    tramite.estado_actual = Tramite.Estado.PROYECTO_ENVIADO
    tramite.save()
    historial(tramite, 'EN_PROCESO', observacion='Proyecto enviado por el cliente. Pendiente de recepción de EDESA.')
    auditar(tramite, 'PROYECTO_ENVIADO')
    return tramite


@transaction.atomic
def actuar(pk, user, data):
    from apps.notificaciones.services import encolar
    tramite = Tramite.objects.select_for_update().get(pk=pk)
    if not puede_actuar(user, tramite):
        raise PermissionDenied('No tenés permiso para actuar por este organismo.')
    codigo = tramite.etapa_actual.codigo
    accion = data['accion']
    if data['etapa'] != codigo or accion not in dict(acciones_disponibles(tramite)):
        raise ValidationError('El trámite cambió de estado. Actualizá la pantalla antes de continuar.')
    fecha = data.get('fecha')
    if accion in {'programar', 'inspeccionar', 'conectar'} and not fecha:
        raise ValidationError('Ingresá la fecha y hora de la actuación.')
    if fecha and accion == 'programar' and fecha <= timezone.now():
        raise ValidationError('La inspección debe programarse para una fecha futura.')
    if fecha and accion in {'inspeccionar', 'conectar'} and fecha > timezone.now():
        raise ValidationError('Una actuación realizada no puede tener fecha futura.')
    if accion == 'conectar' and (not tramite.inspeccion_realizada or fecha < tramite.inspeccion_realizada):
        raise ValidationError('La conexión debe ser posterior a la inspección realizada.')
    if accion == 'inspeccionar' and fecha < tramite.creado_en:
        raise ValidationError('La inspección no puede ser anterior al inicio del trámite.')
    docs = {'respuesta': 'RESPUESTA', 'copaipa': 'COPAIPA', 'dictamen': 'SECRETARIA', 'resolucion': 'RESOLUCION', 'contrato': 'CONTRATO'}
    documento = None
    if accion in docs:
        if not data.get('archivo'):
            raise ValidationError('Esta actuación requiere un documento.')
        documento = guardar_documento(tramite, docs[accion], data['archivo'], user)
    observacion = data.get('observacion', '')
    auditar(tramite, accion.upper(), user, etapa=codigo, observacion=observacion,
            expediente=data.get('expediente', ''), fecha=fecha.isoformat() if fecha else None)
    if accion == 'respuesta':
        tramite.estado_actual = Tramite.Estado.PENDIENTE_ENVIO
        tramite.save()
        encolar(tramite, 'RESPUESTA', 'Respuesta de factibilidad',
                'EDESA emitió la respuesta de factibilidad adjunta. Podés consultarla en el sistema. '
                'El siguiente paso es presentar tu Proyecto Ejecutivo desde la consulta de tu trámite.', documento, user=user)
    elif accion == 'expediente':
        if not data.get('expediente'):
            raise ValidationError('Ingresá el expediente administrativo.')
        tramite.expediente_administrativo = data['expediente']
        tramite.estado_actual = Tramite.Estado.EXPEDIENTE_ASOCIADO
        tramite.save()
        historial(tramite, 'EN_PROCESO', user, f'Expediente administrativo asociado: {tramite.expediente_administrativo}')
    elif accion == 'convocar':
        if not observacion:
            raise ValidationError('Ingresá las instrucciones para la firma.')
        tramite.estado_actual = Tramite.Estado.PENDIENTE_ENVIO
        tramite.save()
        encolar(tramite, 'CONVOCATORIA', 'Acercate a EDESA para firmar tu contrato',
                'EDESA te convoca a firmar el contrato.\n\n' + observacion, user=user)
    elif accion == 'programar':
        tramite.inspeccion_programada = fecha
        tramite.estado_actual = Tramite.Estado.PROGRAMADA
        tramite.save()
        historial(tramite, 'EN_PROCESO', user, f'Inspección programada: {timezone.localtime(fecha):%d/%m/%Y %H:%M}. {observacion}')
        encolar(tramite, 'INSPECCION', 'Inspección programada',
                f'EDESA programó una inspección para el {timezone.localtime(fecha):%d/%m/%Y a las %H:%M}.\n{observacion}', user=user)
    else:
        finales = {'previsar': ('ingreso-copaipa', 'Previsado por EDESA'),
                   'copaipa': ('ingreso-secretaria', 'Visado por COPAIPA'),
                   'dictamen': ('ingreso-enresp', 'Sección aprobada por la Secretaría de Minería y Energía'),
                   'resolucion': ('firma-contrato', 'Aprobado por el ente regulador'),
                   'contrato': ('inspeccion', 'Contrato firmado adjuntado'),
                   'inspeccionar': ('conexion-red', 'Inspección realizada')}
        if accion == 'conectar':
            tramite.conexion_realizada = fecha
            tramite.estado_actual = Tramite.Estado.FINALIZADO
            tramite.save()
            historial(tramite, 'FINALIZADO', user, 'Conexión registrada por EDESA. ' + observacion)
            encolar(tramite, 'FINALIZACION', 'Tu conexión fue registrada',
                    'EDESA registró la conexión a la red. Tu trámite está finalizado y disponible para todos los organismos intervinientes.', user=user)
        else:
            siguiente, detalle = finales[accion]
            if accion == 'inspeccionar':
                tramite.inspeccion_realizada = fecha
            estado_historial = {'previsar': 'PREVISADO', 'copaipa': 'VISADO',
                                'dictamen': 'APROBADO', 'resolucion': 'APROBADO'}.get(accion, 'FINALIZADO')
            historial(tramite, estado_historial, user, detalle + '. ' + observacion)
            mover(tramite, siguiente, user=user)
    return tramite
