"""Métricas de calendario sobre cohortes por fecha de alta; no reconstruye fechas ausentes."""
from collections import Counter
from datetime import datetime, time, timedelta
from statistics import fmean, median
from django.db.models import Prefetch, Q
from django.utils import timezone
from apps.auditoria.models import Auditoria
from apps.organismos.models import Organismo
from apps.tramites.models import Tramite, DocumentoTramite
from apps.workflow.models import TramiteEtapa

# Cada fila es una intervención; EDESA tiene tres instancias independientes.
INSTANCIAS = [
    ('factibilidad', 'EDESA', 'Factibilidad', 'ingreso-factibilidad', 'respuesta-factibilidad'),
    ('proyecto', 'EDESA', 'Proyecto Ejecutivo', 'presentacion-proyecto-ejecutivo', 'previsado-proyecto-ejecutivo'),
    ('copaipa', 'COPAIPA', 'Visado de COPAIPA', 'ingreso-copaipa', 'sellado-copaipa'),
    ('secretaria', 'SECRETARÍA', 'Expediente y dictamen', 'ingreso-secretaria', 'dictamen-expediente'),
    ('enresp', 'ENRESP', 'Resolución', 'ingreso-enresp', 'resolucion-enresp'),
    ('contrato', 'EDESA', 'Contrato · regreso a EDESA', 'firma-contrato', 'firma-contrato'),
]


def _intervalo(inicio, fin, ahora):
    if inicio is None or fin is None or fin < inicio or fin > ahora:
        return None
    return (fin - inicio).total_seconds()


def _espera_subsanacion(eventos, inicio, fin):
    if inicio is None or fin is None:
        return 0
    abierta = None
    segundos = 0
    for evento in eventos:
        if evento.accion == 'SOLICITUD_OBSERVADA' and abierta is None:
            abierta = evento.creado_en
        elif evento.accion == 'SOLICITUD_SUBSANADA' and abierta is not None:
            segundos += max(0, (min(fin, evento.creado_en) - max(inicio, abierta)).total_seconds())
            abierta = None
    if abierta is not None:
        segundos += max(0, (fin - max(inicio, abierta)).total_seconds())
    return segundos


def _resumen(tiempos):
    return {'promedio': fmean(tiempos) if tiempos else None,
            'mediana': median(tiempos) if tiempos else None, 'muestras': len(tiempos)}


def _fila(clave, nombre):
    return {'clave': clave, 'nombre': nombre, 'tramites': set(), 'gestiones': 0,
            'recepcion_tiempos': [], 'respuesta_tiempos': [],
            'pendientes_recepcion': 0, 'pendientes_respuesta': 0, 'sin_datos': 0}


def _cerrar_fila(fila):
    fila['unicos'] = len(fila.pop('tramites'))
    fila['recepcion'] = _resumen(fila.pop('recepcion_tiempos'))
    fila['respuesta'] = _resumen(fila.pop('respuesta_tiempos'))
    return fila


def _periodos(desde, hasta):
    dias = (hasta - desde).days + 1
    unidad = 'día' if dias <= 31 else ('semana' if dias <= 120 else 'mes')
    periodos = []
    inicio = desde
    while inicio <= hasta:
        if unidad == 'mes':
            siguiente = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            siguiente = inicio + timedelta(days=1 if unidad == 'día' else 7)
        fin = min(siguiente - timedelta(days=1), hasta)
        periodos.append({'inicio': inicio, 'fin': fin, 'label': inicio.strftime('%d/%m') if unidad != 'mes' else inicio.strftime('%m/%Y'), 'cantidad': 0})
        inicio = siguiente
    return unidad, periodos


def construir_reporte(desde, hasta, organismo=None, ahora=None, circuito='GGER'):
    ahora = ahora or timezone.now()
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(desde, time.min), tz)
    fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min), tz)
    qs = Tramite.objects.filter(creado_en__gte=inicio, creado_en__lt=fin, tramite_gger__isnull=circuito != 'NEXO')
    if organismo:
        qs = qs.filter(Q(organismo_actual=organismo) | Q(etapas_historial__etapa__organismo=organismo)).distinct()
    qs = qs.select_related('organismo_actual', 'etapa_actual').prefetch_related(
        Prefetch('etapas_historial', queryset=TramiteEtapa.objects.select_related('etapa'), to_attr='report_historial'),
        Prefetch('auditorias', queryset=Auditoria.objects.filter(accion__in=['RECIBIDO', 'PROYECTO_ENVIADO', 'SOLICITUD_OBSERVADA', 'SOLICITUD_SUBSANADA']).order_by('creado_en', 'pk'), to_attr='report_eventos'),
        Prefetch('documentos', queryset=DocumentoTramite.objects.filter(tipo='PROYECTO'), to_attr='report_proyectos'),
    )
    organismos = list(Organismo.objects.order_by('sigla'))
    por_organismo = {o.sigla: _fila(o.sigla, o.nombre) for o in organismos if not organismo or o.pk == organismo.pk}
    por_instancia = {clave: _fila(clave, nombre) for clave, sigla, nombre, _, _ in INSTANCIAS if sigla in por_organismo}
    unidad, periodos = _periodos(desde, hasta)
    estados = Counter()
    ciclos = []
    pendientes = []
    total = finalizados = sin_fecha_cierre = 0
    for tramite in qs:
        total += 1
        estados[tramite.estado_actual] += 1
        fecha_alta = timezone.localtime(tramite.creado_en, tz).date()
        # El rango admitido mantiene acotado el número de bloques.
        for periodo in periodos:
            if periodo['inicio'] <= fecha_alta <= periodo['fin']:
                periodo['cantidad'] += 1
                break
        if tramite.estado_actual == 'FINALIZADO':
            finalizados += 1
            duracion = _intervalo(tramite.creado_en, tramite.conexion_realizada, ahora)
            if duracion is None:
                sin_fecha_cierre += 1
            else:
                ciclos.append(duracion)
        historial = {h.etapa.codigo: h for h in tramite.report_historial}
        for clave, sigla, nombre, entrada, salida in INSTANCIAS:
            if sigla not in por_organismo:
                continue
            h_entrada, h_salida = historial.get(entrada), historial.get(salida)
            actual = tramite.etapa_actual.codigo if tramite.etapa_actual_id else ''
            if h_entrada is None and h_salida is None and actual not in {entrada, salida}:
                continue
            llegada = h_entrada.fecha_inicio if h_entrada else None
            recibido = h_entrada.fecha_fin if h_entrada and entrada != salida else None
            respuesta = h_salida.fecha_fin if h_salida else None
            if clave == 'proyecto':
                # El inicio de etapa 3 corresponde al pedido al cliente, no a su entrega.
                envios = [e.creado_en for e in tramite.report_eventos if e.accion == 'PROYECTO_ENVIADO']
                llegada = min(envios) if envios else (min((d.creado_en for d in tramite.report_proyectos), default=None))
                if llegada is None and tramite.estado_actual == 'PENDIENTE_CLIENTE' and tramite.etapa_actual_id and tramite.etapa_actual.codigo == entrada:
                    continue
            if clave == 'contrato':
                recepciones = [e.creado_en for e in tramite.report_eventos if e.accion == 'RECIBIDO' and e.detalle.get('etapa') == entrada]
                recibido = min(recepciones, default=None)
            tr = _intervalo(llegada, recibido, ahora)
            ts = _intervalo(recibido, respuesta, ahora)
            if clave == 'factibilidad' and ts is not None:
                ts = max(0, ts - _espera_subsanacion(tramite.report_eventos, recibido, respuesta))
            activa = tramite.estado_actual != 'FINALIZADO' and actual in {entrada, salida}
            recepcion_pendiente = (activa and actual == entrada and recibido is None and respuesta is None
                and llegada is not None and llegada <= ahora
                and (clave != 'contrato' or tramite.estado_actual == 'PENDIENTE'))
            respuesta_pendiente = activa and tramite.estado_actual != 'OBSERVADO' and recibido is not None and recibido <= ahora and respuesta is None
            recepcion_esperada = (actual == salida and entrada != salida) or (
                clave == 'contrato' and actual == entrada and tramite.estado_actual != 'PENDIENTE')
            incompleto = any((llegada is None, llegada is not None and llegada > ahora,
                recibido is not None and tr is None, respuesta is not None and ts is None,
                not activa and respuesta is None, activa and recepcion_esperada and recibido is None))
            for fila in [por_organismo[sigla], por_instancia[clave]]:
                fila['tramites'].add(tramite.pk)
                fila['gestiones'] += 1
                if tr is not None:
                    fila['recepcion_tiempos'].append(tr)
                if ts is not None:
                    fila['respuesta_tiempos'].append(ts)
                fila['pendientes_recepcion'] += int(recepcion_pendiente)
                fila['pendientes_respuesta'] += int(respuesta_pendiente)
                fila['sin_datos'] += int(incompleto)
            if recepcion_pendiente or respuesta_pendiente:
                inicio_espera = llegada if recepcion_pendiente else recibido
                pendientes.append({'pk': tramite.pk, 'titular': tramite.titular_display,
                    'organismo': sigla, 'instancia': nombre,
                    'tipo': 'Por recibir' if recepcion_pendiente else 'Por responder',
                    'espera': max(0, (ahora - inicio_espera).total_seconds() - (_espera_subsanacion(tramite.report_eventos, inicio_espera, ahora) if clave == 'factibilidad' else 0)), 'desde': inicio_espera})
    recepcion_global = _resumen([t for f in por_organismo.values() for t in f['recepcion_tiempos']])
    respuesta_global = _resumen([t for f in por_organismo.values() for t in f['respuesta_tiempos']])
    filas = [_cerrar_fila(f) for f in por_organismo.values()]
    instancias = [_cerrar_fila(f) for f in por_instancia.values()]
    maximo = max((p['cantidad'] for p in periodos), default=0)
    for periodo in periodos:
        periodo['porcentaje'] = round(100 * periodo['cantidad'] / maximo, 2) if maximo else 0
    etiquetas = dict(Tramite.Estado.choices)
    distribucion = [{'estado': clave, 'nombre': etiquetas.get(clave, clave.replace('_', ' ').capitalize()),
                     'cantidad': cantidad, 'porcentaje': round(cantidad * 100 / total, 1)}
                    for clave, cantidad in estados.most_common()] if total else []
    return {'circuito_filtro': 'Obra de nexo' if circuito == 'NEXO' else 'GGER', 'total': total, 'finalizados': finalizados, 'activos': total - finalizados,
            'ciclo': _resumen(ciclos), 'sin_fecha_cierre': sin_fecha_cierre,
            'organismos': filas, 'instancias': instancias, 'periodos': periodos, 'unidad': unidad,
            'estados': distribucion, 'ancho_grafico': max(320, len(periodos) * 38), 'pendientes': sorted(pendientes, key=lambda p: p['espera'], reverse=True)[:10],
            'pendientes_total': len(pendientes),
            'recepcion': recepcion_global, 'respuesta': respuesta_global,
            'corte': ahora, 'desde': desde, 'hasta': hasta, 'organismo_filtro': organismo,
            'sin_datos': sum(f['sin_datos'] for f in filas)}
