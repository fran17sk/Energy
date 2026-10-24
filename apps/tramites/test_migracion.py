import tempfile
from pathlib import Path
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings


class MigracionCircuitoTests(TransactionTestCase):
    def test_conserva_codigo_y_copia_solicitud_antigua_a_almacenamiento_privado(self):
        with tempfile.TemporaryDirectory() as media, tempfile.TemporaryDirectory() as privado:
            with override_settings(MEDIA_ROOT=media, PRIVATE_MEDIA_ROOT=privado):
                executor = MigrationExecutor(connection)
                destino_anterior = [('tramites', '0002_initial')]
                executor.migrate(destino_anterior)
                try:
                    apps = executor.loader.project_state(destino_anterior).apps
                    TramiteAnterior = apps.get_model('tramites', 'Tramite')
                    archivo = Path(media) / 'tramites/solicitud-antigua.pdf'
                    archivo.parent.mkdir(parents=True)
                    archivo.write_bytes(b'%PDF-1.4\nsolicitud antigua')
                    anterior = TramiteAnterior.objects.create(
                        numero='GGER-2026-000001', nis='antiguo', titular_nombre='Cliente anterior',
                        titular_dni_cuit='123', titular_email='anterior@example.com',
                        solicitud_factibilidad='tramites/solicitud-antigua.pdf')
                finally:
                    executor = MigrationExecutor(connection)
                    executor.migrate(executor.loader.graph.leaf_nodes())
                from .models import Tramite
                actual = Tramite.objects.get(pk=anterior.pk)
                self.assertEqual(actual.numero, 'GGER-2026-000001')
                self.assertEqual(actual.etapa_actual.codigo, 'ingreso-factibilidad')
                self.assertEqual(actual.organismo_actual.sigla, 'EDESA')
                documento = actual.documentos.get(tipo='SOLICITUD')
                self.assertEqual(Path(documento.archivo.path).read_bytes(), archivo.read_bytes())
                self.assertTrue(archivo.exists())
                self.assertTrue(actual.auditorias.filter(accion='MIGRACION_CIRCUITO').exists())
