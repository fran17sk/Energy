"""Observación y subsanación de la solicitud inicial, con autorización y bloqueo por trámite."""
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Tramite, ObservacionSolicitud
from .solicitud_forms import SolicitudFactibilidadForm
from .solicitud_email import datos_para_tramite, enviar_solicitud
from . import services


class ObservacionForm(forms.Form):
    detalle = forms.CharField(label='Qué debe corregir el solicitante', max_length=2000,
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'alta-input', 'placeholder': 'Detallá los datos o documentos incorrectos y cómo corregirlos.'}))


class SubsanacionForm(SolicitudFactibilidadForm):
    requiere_adjuntos_apoderado = False
    observacion_id = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ['formulario_digital', 'dni_titular', 'dni_apoderado', 'poder_apoderado']:
            self.fields[nombre].required = False
            self.fields[nombre].help_text = 'Adjuntá sólo si necesitás reemplazar o completar este documento.'



def puede_observar(user, tramite):
    return (services.puede_actuar(user, tramite) and tramite.organismo_actual.sigla == 'EDESA'
        and tramite.etapa_actual.codigo == 'respuesta-factibilidad'
        and tramite.estado_actual == Tramite.Estado.PENDIENTE)


@transaction.atomic
def observar(pk, user, detalle):
    tramite = Tramite.objects.select_for_update().get(pk=pk)
    if not puede_observar(user, tramite):
        raise PermissionDenied('Sólo EDESA puede observar una solicitud recibida y pendiente de respuesta.')
    detalle = detalle.strip()
    if not detalle or len(detalle) > 2000:
        raise ValidationError('Ingresá una observación de hasta 2000 caracteres.')
    observacion = ObservacionSolicitud.objects.create(tramite=tramite, usuario=user, detalle=detalle)
    tramite.estado_actual = Tramite.Estado.OBSERVADO
    tramite.save()
    services.auditar(tramite, 'SOLICITUD_OBSERVADA', user, observacion=detalle, observacion_id=observacion.pk)
    from apps.notificaciones.services import encolar
    encolar(tramite, 'OBSERVACION', 'Tu solicitud requiere correcciones',
        f'EDESA observó tu solicitud:\n\n{detalle}\n\nIngresá a Consultar estado del trámite con tu número de trámite, NIS y DNI/CUIT del titular. '
        'Allí podrás corregir los datos y adjuntar los documentos que necesiten reemplazo.', user=user)
    return observacion


@transaction.atomic
def subsanar(pk, data):
    tramite = Tramite.objects.select_for_update().get(pk=pk)
    if (tramite.estado_actual != Tramite.Estado.OBSERVADO or tramite.etapa_actual.codigo != 'respuesta-factibilidad'
            or tramite.organismo_actual.sigla != 'EDESA'):
        raise ValidationError('El trámite ya no está pendiente de corrección. Volvé a consultar su estado.')
    observacion = tramite.observaciones_solicitud.filter(pk=data['observacion_id'], subsanada_en__isnull=True).first()
    if not observacion:
        raise ValidationError('La observación cambió. Actualizá la página antes de enviar.')
    campos = datos_para_tramite(data)
    cambios = [nombre for nombre, valor in campos.items() if nombre != 'consulta_documento_hash' and getattr(tramite, nombre) != valor]
    for nombre, valor in campos.items():
        setattr(tramite, nombre, valor)
    enviar_solicitud(data, tramite.numero, subsanacion=observacion.detalle)
    tramite.estado_actual = Tramite.Estado.SUBSANADO
    tramite.save()
    observacion.subsanada_en = timezone.now()
    observacion.save(update_fields=['subsanada_en'])
    services.auditar(tramite, 'SOLICITUD_SUBSANADA', observacion_id=observacion.pk,
        campos_corregidos=cambios, documentos_reemplazados=[nombre for nombre in ['formulario_digital', 'dni_titular', 'dni_apoderado', 'poder_apoderado'] if data.get(nombre)])
    return tramite
