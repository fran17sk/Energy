import csv
import io
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from apps.tramites.views import exigir_institucional
from .forms import FiltrosReportesForm
from .services import construir_reporte


def _filtros(request):
    datos = FiltrosReportesForm.datos_iniciales()
    datos.update({key: value for key, value in request.GET.items() if key in {'desde', 'hasta', 'organismo'}})
    return FiltrosReportesForm(datos)


@login_required
@never_cache
def dashboard(request):
    exigir_institucional(request)
    form = _filtros(request)
    reporte = construir_reporte(**form.cleaned_data) if form.is_valid() else None
    export_query = ''
    if reporte:
        from urllib.parse import urlencode
        export_query = urlencode({'desde': form.cleaned_data['desde'].isoformat(),
            'hasta': form.cleaned_data['hasta'].isoformat(),
            'organismo': form.cleaned_data['organismo'].pk if form.cleaned_data['organismo'] else ''})
    return render(request, 'reportes/dashboard.html', {
        'filtros': form, 'reporte': reporte, 'export_query': export_query,
    }, status=200 if reporte is not None else 400)


def _celda_segura(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


def _dias(value):
    return '' if value is None else f'{value / 86400:.4f}'.replace('.', ',')


@login_required
@never_cache
def exportar(request):
    exigir_institucional(request)
    form = _filtros(request)
    if not form.is_valid():
        return HttpResponse('Corregí los filtros antes de exportar el reporte.', status=400)
    reporte = construir_reporte(**form.cleaned_data)
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow(['Reporte GGER', 'Trámites por fecha de inicio', str(reporte['desde']), str(reporte['hasta'])])
    writer.writerow(['Organismo seleccionado', _celda_segura(reporte['organismo_filtro'].sigla) if reporte['organismo_filtro'] else 'Todos'])
    writer.writerow(['Corte', timezone.localtime(reporte['corte']).isoformat(), 'Unidad de duración: días corridos'])
    writer.writerow(['Total trámites', reporte['total'], 'En curso', reporte['activos'], 'Finalizados', reporte['finalizados']])
    writer.writerow([])
    writer.writerow(['Indicador', 'Promedio (días)', 'Mediana (días)', 'Muestras'])
    for nombre, medida in [('Recepción', reporte['recepcion']), ('Respuesta', reporte['respuesta']), ('Ciclo completo', reporte['ciclo'])]:
        writer.writerow([nombre, _dias(medida['promedio']), _dias(medida['mediana']), medida['muestras']])
    writer.writerow([])
    writer.writerow(['Organismo', 'Nombre', 'Trámites únicos', 'Gestiones',
        'Recepción promedio (días)', 'Recepción mediana (días)', 'Muestras recepción',
        'Respuesta promedio (días)', 'Respuesta mediana (días)', 'Muestras respuesta',
        'Por recibir', 'Por responder', 'Gestiones con fechas incompletas o inconsistentes'])
    for fila in reporte['organismos']:
        writer.writerow([_celda_segura(fila['clave']), _celda_segura(fila['nombre']), fila['unicos'], fila['gestiones'],
            _dias(fila['recepcion']['promedio']), _dias(fila['recepcion']['mediana']), fila['recepcion']['muestras'],
            _dias(fila['respuesta']['promedio']), _dias(fila['respuesta']['mediana']), fila['respuesta']['muestras'],
            fila['pendientes_recepcion'], fila['pendientes_respuesta'], fila['sin_datos']])
    writer.writerow([])
    writer.writerow(['Instancia', 'Gestiones', 'Recepción promedio (días)', 'Muestras recepción', 'Respuesta promedio (días)', 'Muestras respuesta'])
    for fila in reporte['instancias']:
        writer.writerow([fila['nombre'], fila['gestiones'], _dias(fila['recepcion']['promedio']), fila['recepcion']['muestras'],
                         _dias(fila['respuesta']['promedio']), fila['respuesta']['muestras']])
    writer.writerow([])
    writer.writerow(['Estado actual', 'Cantidad', 'Porcentaje'])
    for estado in reporte['estados']:
        writer.writerow([_celda_segura(estado['nombre']), estado['cantidad'], str(estado['porcentaje']).replace('.', ',')])
    writer.writerow([])
    writer.writerow(['Altas desde', 'Altas hasta', 'Cantidad'])
    for periodo in reporte['periodos']:
        writer.writerow([periodo['inicio'].isoformat(), periodo['fin'].isoformat(), periodo['cantidad']])
    response = HttpResponse('\ufeff' + buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="reportes-gger.csv"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
