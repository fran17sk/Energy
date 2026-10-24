from django.core.management.base import BaseCommand
from apps.workflow.circuito import configurar_circuito


class Command(BaseCommand):
    help = 'Configura el circuito operativo GGER sin borrar el historial existente.'

    def handle(self, *args, **options):
        configurar_circuito()
        self.stdout.write(self.style.SUCCESS('Circuito GGER configurado.'))
