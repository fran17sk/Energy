"""Circuito operativo: códigos estables, recepciones separadas por organismo."""
from apps.organismos.models import Organismo
from .models import Etapa

CIRCUITO = [
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


def configurar_circuito():
    for sigla, nombre in [('EDESA', 'EDESA'), ('COPAIPA', 'COPAIPA'),
                          ('SECRETARÍA', 'Secretaría de Minería y Energía'), ('ENRESP', 'Ente regulador ENRESP')]:
        Organismo.objects.get_or_create(sigla=sigla, defaults={'nombre': nombre})
    for orden, codigo, nombre, sigla in CIRCUITO:
        Etapa.objects.update_or_create(codigo=codigo, defaults={
            'orden': orden, 'nombre': nombre, 'organismo': Organismo.objects.get(sigla=sigla),
            'actor_externo': codigo == 'presentacion-proyecto-ejecutivo', 'activa': True,
        })
    # Se conservan etapas antiguas e historial, sin incluir los pasos de salida redundantes.
    Etapa.objects.filter(codigo__in=['entregado-titular', 'salida-copaipa', 'salida-secretaria', 'salida-enresp']).update(activa=False)
