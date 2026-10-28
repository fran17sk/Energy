import hashlib
import time
import logging
from django.core import signing
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError, RequestDataTooBig, TooManyFilesSent, TooManyFieldsSent
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from .forms import ConsultaTramiteForm, DocumentoForm, AccionTramiteForm
from .solicitud_forms import SolicitudFactibilidadForm
from .solicitud_uploads import SolicitudMemoryUploadHandler
from .solicitud_email import registrar_y_enviar_solicitud
from .models import Tramite, DocumentoTramite
from . import services
from apps.workflow.models import Etapa


def inicio(request):
    return render(request, 'public/inicio.html')


@csrf_exempt
@never_cache
def nuevo(request):
    # Instalar antes de que CSRF lea request.POST: no hay upload handler temporal.
    request.upload_handlers = [SolicitudMemoryUploadHandler(request)]
    try:
        return _nuevo_protegido(request)
    except (RequestDataTooBig, TooManyFilesSent, TooManyFieldsSent):
        form = SolicitudFactibilidadForm()
        return render(request, 'public/nuevo.html', {
            'form': form, 'error_carga': 'La carga supera los límites permitidos. Adjuntá archivos de hasta 5 MB y 15 MB en total.',
        }, status=413)


@csrf_protect
def _nuevo_protegido(request):
    if request.method == 'POST':
        post = request.POST
        error_carga = getattr(request, 'solicitud_upload_error', None)
        form = SolicitudFactibilidadForm(post, {} if error_carga else request.FILES)
        if error_carga:
            form.add_error(None, error_carga)
        if form.is_valid():
            try:
                tramite = registrar_y_enviar_solicitud(form.cleaned_data)
            except Exception as exc:
                # Nunca registrar datos, adjuntos, dirección del solicitante ni detalles SMTP.
                logging.getLogger(__name__).warning('Solicitud no enviada (%s); no se conservan datos de la presentación para reintento.', type(exc).__name__)
                form.add_error(None, 'No se pudo enviar la solicitud a EDESA. No se creó el trámite ni se guardaron los documentos. '
                    'Conservá los archivos, volvé a seleccionarlos e intentá nuevamente más tarde.')
            else:
                response = redirect('solicitud_enviada')
                response.status_code = 303
                response.set_signed_cookie('solicitud_enviada', str(tramite.pk), salt='solicitud-enviada',
                    max_age=600, httponly=True, samesite='Lax', secure=request.is_secure())
                return response
    else:
        form = SolicitudFactibilidadForm()
    return render(request, 'public/nuevo.html', {'form': form})


@never_cache
def solicitud_enviada(request):
    try:
        pk = int(request.get_signed_cookie('solicitud_enviada', salt='solicitud-enviada', max_age=600))
    except (KeyError, signing.BadSignature, ValueError, TypeError):
        return redirect('tramite_nuevo')
    tramite = get_object_or_404(Tramite, pk=pk, presentacion_por_correo=True)
    response = render(request, 'public/solicitud_enviada.html', {'tramite': tramite})
    response['Referrer-Policy'] = 'no-referrer'
    return response


def acceso_cliente(request, pk):
    acceso = request.session.get('consulta_tramite', {})
    return acceso.get('id') == pk and acceso.get('hasta', 0) > time.time()


def contexto_consulta(form, resultado=None, no_encontrado=False, proyecto_form=None):
    seguimiento = []
    if resultado:
        completadas = set(resultado.etapas_historial.filter(
            estado__in=services.HISTORIAL_COMPLETO
        ).values_list('etapa_id', flat=True))
        for etapa in Etapa.objects.filter(activa=True).select_related('organismo'):
            estado = 'done' if etapa.pk in completadas else 'pending'
            if etapa.pk == resultado.etapa_actual_id and resultado.estado_actual != 'FINALIZADO':
                estado = 'current'
            seguimiento.append({'etapa': etapa, 'estado': estado})
    return {'form': form, 'resultado': resultado, 'no_encontrado': no_encontrado,
            'seguimiento': seguimiento, 'proyecto_form': proyecto_form or DocumentoForm()}


@never_cache
def consultar(request):
    resultado = None
    no_encontrado = False
    if request.method == 'POST':
        request.session.pop('consulta_tramite', None)
        # Protección adicional por IP; desplegar un límite compartido en el proxy en producción.
        key = 'consulta:' + hashlib.sha256(request.META.get('REMOTE_ADDR', '').encode()).hexdigest()
        cache.add(key, 0, 60)
        try:
            intentos = cache.incr(key)
        except ValueError:
            cache.set(key, 1, 60)
            intentos = 1
        if intentos > 15:
            return HttpResponse('Demasiados intentos. Esperá un minuto antes de volver a consultar.', status=429)
        form = ConsultaTramiteForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            resultado = Tramite.objects.filter(
                numero__iexact=cd['numero'], nis=cd['nis'],
            ).select_related('etapa_actual', 'organismo_actual').first()
            if resultado and not resultado.verificar_documento_consulta(cd['dni_cuit']):
                resultado = None
            if resultado:
                request.session['consulta_tramite'] = {'id': resultado.pk, 'hasta': time.time() + 1800}
            else:
                no_encontrado = True
    else:
        form = ConsultaTramiteForm()
        acceso = request.session.get('consulta_tramite', {})
        if request.GET.get('vista') and acceso_cliente(request, acceso.get('id')):
            resultado = Tramite.objects.select_related('etapa_actual', 'organismo_actual').filter(pk=acceso['id']).first()
    return render(request, 'public/consultar.html', contexto_consulta(form, resultado, no_encontrado))


@never_cache
@require_POST
def proyecto_cliente(request, pk):
    if not acceso_cliente(request, pk):
        raise PermissionDenied('Volvé a consultar con el código, NIS y DNI / CUIT para presentar el proyecto.')
    tramite = get_object_or_404(Tramite.objects.select_related('etapa_actual', 'organismo_actual'), pk=pk)
    form = DocumentoForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            services.presentar_proyecto(pk, form.cleaned_data['archivo'])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Proyecto enviado correctamente. EDESA tiene una tarea pendiente de recepción y revisión.')
            return redirect('/tramites/consultar/?vista=1')
    return render(request, 'public/consultar.html', contexto_consulta(ConsultaTramiteForm(), tramite, proyecto_form=form))


@never_cache
def documento(request, pk):
    doc = get_object_or_404(DocumentoTramite, pk=pk)
    if not (services.institucional(request.user) or acceso_cliente(request, doc.tramite_id)):
        raise PermissionDenied('Consultá primero el trámite con tus datos de acceso.')
    try:
        archivo = doc.archivo.open('rb')
    except FileNotFoundError:
        return HttpResponse('El documento no está disponible. Contactá al organismo responsable.', status=404)
    extension = doc.archivo.name.rsplit('.', 1)[-1]
    response = FileResponse(archivo, as_attachment=True, filename=f'{doc.get_tipo_display()}.{extension}')
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def exigir_institucional(request):
    if not services.institucional(request.user):
        raise PermissionDenied('Tu cuenta debe estar activa y asociada a un organismo.')


@login_required
@never_cache
def dashboard(request):
    exigir_institucional(request)
    qs = Tramite.objects.select_related('etapa_actual', 'organismo_actual')
    tareas = qs.filter(organismo_actual_id=request.user.organismo_id).exclude(
        estado_actual__in=['FINALIZADO', 'PENDIENTE_CLIENTE'])
    return render(request, 'institutional/dashboard.html', {
        'total': qs.count(), 'pendientes': tareas.count(),
        'conectados': qs.filter(estado_actual='FINALIZADO').count(),
        'ultimos': qs[:5], 'tareas': tareas[:20],
    })


@login_required
@never_cache
def lista(request):
    exigir_institucional(request)
    qs = Tramite.objects.select_related('etapa_actual', 'organismo_actual')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(nis__icontains=q) | Q(titular_nombre__icontains=q) | Q(titular_dni_cuit__icontains=q))
    if request.GET.get('mias'):
        qs = qs.filter(organismo_actual_id=request.user.organismo_id).exclude(estado_actual__in=['FINALIZADO', 'PENDIENTE_CLIENTE'])
    return render(request, 'institutional/tramites.html', {'tramites': qs, 'q': q})


@login_required
@never_cache
def detalle(request, pk):
    exigir_institucional(request)
    tramite = get_object_or_404(Tramite.objects.select_related('etapa_actual', 'organismo_actual'), pk=pk)
    if request.method == 'GET':
        services.auditar(tramite, 'CONSULTA_EXPEDIENTE', request.user,
                         etapa=tramite.etapa_actual.codigo if tramite.etapa_actual_id else '')
    puede = services.puede_actuar(request.user, tramite)
    acciones = services.acciones_disponibles(tramite) if puede else []
    form = AccionTramiteForm(request.POST or None, request.FILES or None,
                            acciones=acciones, initial={'etapa': tramite.etapa_actual.codigo if tramite.etapa_actual_id else ''})
    if request.method == 'POST':
        if not puede:
            raise PermissionDenied('El trámite no está en una etapa de tu organismo o tu rol es de consulta.')
        if form.is_valid():
            try:
                services.actuar(pk, request.user, form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, 'Actuación registrada con tu usuario, fecha y hora.')
                return redirect('institucional_tramite_detalle', pk=pk)
    return render(request, 'institutional/detalle.html', {
        'tramite': tramite, 'accion_form': form, 'acciones': acciones, 'puede_actuar': puede,
        'historial': tramite.etapas_historial.select_related('etapa', 'usuario'),
        'auditorias': tramite.auditorias.select_related('usuario').order_by('creado_en', 'pk'),
        'correos': tramite.notificaciones.filter(canal='EMAIL').order_by('-creado_en'),
        'pasos_circuito': contexto_consulta(ConsultaTramiteForm(), tramite)['seguimiento'],
        'confirmaciones': {codigo: services.resumen_actuacion(tramite, codigo) for codigo, _ in acciones},
        'accion_info': services.resumen_actuacion(tramite, acciones[0][0]) if acciones else None,
        'requiere_recepcion': puede and services.requiere_recepcion(tramite),
    })


@login_required
@require_POST
def reintentar_correo(request, pk):
    from apps.notificaciones.models import Notificacion
    from apps.notificaciones.services import enviar
    notificacion = get_object_or_404(Notificacion.objects.select_related('tramite'), pk=pk, canal='EMAIL')
    if not services.puede_actuar(request.user, notificacion.tramite):
        raise PermissionDenied('Sólo el organismo de la etapa actual puede reintentar el envío.')
    services.auditar(notificacion.tramite, 'REINTENTO_CORREO', request.user, notificacion=pk)
    if enviar(pk):
        messages.success(request, 'Correo enviado correctamente.')
    else:
        messages.error(request, 'No se pudo enviar el correo. Revisá la configuración SMTP; el envío sigue disponible para reintento.')
    return redirect('institucional_tramite_detalle', pk=notificacion.tramite_id)
