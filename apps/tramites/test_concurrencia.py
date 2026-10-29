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

    def test_finalizacion_simultanea_de_nexo_y_gger_respeta_bloqueo(self):
        from django.core.exceptions import ValidationError
        from django.test import override_settings
        from django.utils import timezone
        configurar_circuito()
        user = get_user_model().objects.create_user(username='conexiones', rol='OPER',
            organismo=Organismo.objects.get(sigla='EDESA'))
        gger = Tramite.objects.create(nis='simultaneo', titular_email='cliente@example.com', requiere_nexo=True)
        nexo = Tramite.objects.create(tramite_gger=gger, nis='simultaneo', titular_email='cliente@example.com')
        with transaction.atomic():
            for t in [gger, nexo]:
                services.mover(t, 'conexion-red')
                t.inspeccion_realizada = timezone.now()
                t.save()
        barrier = Barrier(2)

        def finalizar(pk):
            try:
                usuario = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                try:
                    services.actuar(pk, usuario, {'accion': 'conectar', 'etapa': 'conexion-red', 'fecha': timezone.now()})
                    return 'finalizado'
                except ValidationError:
                    return 'bloqueado'
            finally:
                connections.close_all()

        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            with ThreadPoolExecutor(max_workers=2) as executor:
                principal = executor.submit(finalizar, gger.pk)
                secundario = executor.submit(finalizar, nexo.pk)
                resultado_gger = principal.result(timeout=20)
                self.assertEqual(secundario.result(timeout=20), 'finalizado')
            nexo.refresh_from_db()
            gger.refresh_from_db()
            self.assertEqual(nexo.estado_actual, 'FINALIZADO')
            if resultado_gger == 'bloqueado':
                self.assertNotEqual(gger.estado_actual, 'FINALIZADO')
                services.actuar(gger.pk, user, {'accion': 'conectar', 'etapa': 'conexion-red', 'fecha': timezone.now()})
                gger.refresh_from_db()
            self.assertEqual(gger.estado_actual, 'FINALIZADO')
            self.assertGreaterEqual(gger.actualizado_en, nexo.actualizado_en)
