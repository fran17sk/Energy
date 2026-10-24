from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.db import connections, transaction
from django.test import TransactionTestCase
from apps.organismos.models import Organismo
from apps.workflow.circuito import configurar_circuito
from .models import Tramite
from . import services


class RecepcionConcurrenteTests(TransactionTestCase):
    def test_dos_aperturas_simultaneas_generan_una_sola_recepcion(self):
        configurar_circuito()
        user = get_user_model().objects.create_user(username='gestor', rol='OPER',
            organismo=Organismo.objects.get(sigla='EDESA'))
        tramite = Tramite.objects.create(nis='concurrente', titular_nombre='Prueba',
            titular_dni_cuit='123', titular_email='prueba@example.com')
        with transaction.atomic():
            services.mover(tramite, 'ingreso-factibilidad')
        barrier = Barrier(2)

        def abrir():
            try:
                usuario = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                return services.recibir(tramite.pk, usuario).etapa_actual.codigo
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(abrir) for _ in range(2)]
            resultados = [future.result(timeout=20) for future in futures]
        self.assertEqual(resultados, ['respuesta-factibilidad', 'respuesta-factibilidad'])
        self.assertEqual(tramite.auditorias.filter(accion='RECIBIDO').count(), 1)
        self.assertEqual(tramite.etapas_historial.count(), 2)
