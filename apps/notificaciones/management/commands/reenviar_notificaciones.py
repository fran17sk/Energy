from django.core.management.base import BaseCommand
from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import enviar


class Command(BaseCommand):
    help = 'Reintenta correos pendientes o con error sin reenviar los ya enviados.'

    def handle(self, *args, **options):
        enviados = fallidos = 0
        for pk in Notificacion.objects.filter(canal='EMAIL', estado__in=['PENDIENTE', 'ERROR']).values_list('pk', flat=True):
            if enviar(pk):
                enviados += 1
            else:
                fallidos += 1
        self.stdout.write(f'Enviados: {enviados}. Con error: {fallidos}.')
