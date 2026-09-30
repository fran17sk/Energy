from django.core.management.base import BaseCommand
from apps.organismos.models import Organismo
from apps.workflow.models import Etapa

ETAPAS = [
    (1, 'ingreso-factibilidad', 'Ingreso de solicitud de factibilidad', 'EDESA'),
    (2, 'respuesta-factibilidad', 'Respuesta de factibilidad', 'EDESA'),
    (3, 'presentacion-proyecto-ejecutivo', 'Presentación de Proyecto Ejecutivo', None),
    (4, 'previsado-proyecto-ejecutivo', 'Previsado del Proyecto Ejecutivo', 'EDESA'),
    (5, 'entregado-titular', 'Entregado al Titular o responsable', 'EDESA'),
    (6, 'ingreso-copaipa', 'Ingreso para revisión', 'COPAIPA'),
    (7, 'sellado-copaipa', 'Sellado', 'COPAIPA'),
    (8, 'salida-copaipa', 'Salida', 'COPAIPA'),
    (9, 'ingreso-secretaria', 'Ingreso', 'SECRETARÍA'),
    (10, 'dictamen-expediente', 'Dictamen/expediente', 'SECRETARÍA'),
    (11, 'salida-secretaria', 'Salida', 'SECRETARÍA'),
    (12, 'ingreso-enresp', 'Ingreso', 'ENRESP'),
    (13, 'resolucion-enresp', 'Resolución', 'ENRESP'),
    (14, 'salida-enresp', 'Salida', 'ENRESP'),
    (15, 'firma-contrato', 'Firma del contrato', 'EDESA'),
    (16, 'inspeccion', 'Inspección', 'EDESA'),
    (17, 'conexion-red', 'Conexión a la red de la Distribuidora', 'EDESA'),
]

class Command(BaseCommand):
    help = 'Carga el circuito inicial de 17 etapas definido para GGER.'
    def handle(self, *args, **options):
        for orden, codigo, nombre, sigla in ETAPAS:
            organismo = Organismo.objects.filter(sigla=sigla).first() if sigla else None
            Etapa.objects.update_or_create(
                codigo=codigo,
                defaults={'orden': orden, 'nombre': nombre, 'organismo': organismo, 'actor_externo': sigla is None, 'activa': True}
            )
        self.stdout.write(self.style.SUCCESS('Workflow GGER cargado/actualizado.'))
