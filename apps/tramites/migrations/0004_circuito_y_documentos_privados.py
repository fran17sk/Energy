from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import migrations


# Datos congelados: esta migración no depende de futuras versiones de servicios.
ETAPAS = [
    (1, 'ingreso-factibilidad', 'Solicitud de factibilidad', 'EDESA'),
    (2, 'respuesta-factibilidad', 'Respuesta de factibilidad', 'EDESA'),
    (3, 'presentacion-proyecto-ejecutivo', 'Presentación de Proyecto Ejecutivo', 'EDESA'),
    (4, 'previsado-proyecto-ejecutivo', 'Previsado del Proyecto Ejecutivo', 'EDESA'),
    (6, 'ingreso-copaipa', 'Recepción en COPAIPA', 'COPAIPA'),
    (7, 'sellado-copaipa', 'Visado de COPAIPA', 'COPAIPA'),
    (9, 'ingreso-secretaria', 'Recepción en la Secretaría de Minería y Energía', 'SECRETARÍA'),
    (10, 'dictamen-expediente', 'Expediente administrativo y dictamen', 'SECRETARÍA'),
    (12, 'ingreso-enresp', 'Recepción en el ente regulador', 'ENRESP'),
    (13, 'resolucion-enresp', 'Resolución del ente regulador', 'ENRESP'),
    (15, 'firma-contrato', 'Firma del contrato · recepción final en EDESA', 'EDESA'),
    (16, 'inspeccion', 'Inspección del domicilio', 'EDESA'),
    (17, 'conexion-red', 'Conexión a la red', 'EDESA'),
]


def preparar(apps, schema_editor):
    Organismo = apps.get_model('organismos', 'Organismo')
    Etapa = apps.get_model('workflow', 'Etapa')
    Tramite = apps.get_model('tramites', 'Tramite')
    Documento = apps.get_model('tramites', 'DocumentoTramite')
    Auditoria = apps.get_model('auditoria', 'Auditoria')
    for orden, codigo, nombre, sigla in ETAPAS:
        organismo, _ = Organismo.objects.get_or_create(sigla=sigla, defaults={
            'nombre': 'Secretaría de Minería y Energía' if sigla == 'SECRETARÍA' else sigla})
        Etapa.objects.update_or_create(codigo=codigo, defaults={'orden': orden, 'nombre': nombre,
            'organismo': organismo, 'actor_externo': codigo == 'presentacion-proyecto-ejecutivo', 'activa': True})
    Etapa.objects.filter(codigo__in=['entregado-titular', 'salida-copaipa', 'salida-secretaria', 'salida-enresp']).update(activa=False)
    anterior = FileSystemStorage(location=settings.MEDIA_ROOT)
    privado = FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)
    equivalencias = {'entregado-titular': 'ingreso-copaipa', 'salida-copaipa': 'ingreso-secretaria',
                     'salida-secretaria': 'ingreso-enresp', 'salida-enresp': 'firma-contrato'}
    for tramite in Tramite.objects.select_related('etapa_actual').iterator():
        archivo = tramite.solicitud_factibilidad.name
        if archivo:
            if not privado.exists(archivo):
                if not anterior.exists(archivo):
                    raise RuntimeError(f'Falta el archivo de la solicitud del trámite ID {tramite.pk}. Restaurá el respaldo antes de migrar.')
                with anterior.open(archivo, 'rb') as contenido:
                    nombre = privado.save(archivo, contenido)
                if nombre != archivo:
                    raise RuntimeError('No se pudo conservar la ruta del documento migrado.')
            Documento.objects.get_or_create(tramite=tramite, tipo='SOLICITUD', defaults={'archivo': archivo})
        codigo = tramite.etapa_actual.codigo if tramite.etapa_actual_id else ''
        destino = equivalencias.get(codigo)
        if not codigo:
            destino = 'ingreso-factibilidad'
        if destino and tramite.estado_actual != 'FINALIZADO':
            tramite.etapa_actual = Etapa.objects.get(codigo=destino)
            tramite.organismo_actual = tramite.etapa_actual.organismo
            tramite.estado_actual = 'PENDIENTE'
            tramite.save()
            Auditoria.objects.create(tramite=tramite, accion='MIGRACION_CIRCUITO', detalle={
                'etapa_anterior': codigo, 'etapa': destino, 'usuario_nombre': 'Migración del sistema'})


class Migration(migrations.Migration):
    dependencies = [('tramites', '0003_tramite_conexion_realizada_and_more'),
                    ('workflow', '0001_initial'), ('auditoria', '0002_initial')]
    operations = [migrations.RunPython(preparar, migrations.RunPython.noop)]
