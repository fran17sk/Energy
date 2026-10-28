from pathlib import Path
import tempfile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from apps.organismos.models import Organismo
from apps.workflow.circuito import configurar_circuito
from apps.auditoria.models import Auditoria
from apps.notificaciones.models import Notificacion
from . import test_solicitud_email as fixtures
from .solicitud_forms import SolicitudFactibilidadForm
from .models import Tramite, DocumentoTramite
from . import services, observaciones
from .solicitud_email import datos_para_tramite


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', EDESA_SOLICITUD_EMAIL='edesa@example.com')
class ObservacionesTests(TestCase):
    datos = fixtures.SolicitudEmailTests.datos
    pdf = fixtures.SolicitudEmailTests.pdf
    archivos = fixtures.SolicitudEmailTests.archivos

    def setUp(self):
        cache.clear()
        configurar_circuito()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        setting = override_settings(PRIVATE_MEDIA_ROOT=self.tmp.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.edesa = get_user_model().objects.create_user(username='edesa', rol='OPER', organismo=Organismo.objects.get(sigla='EDESA'))
        self.otro = get_user_model().objects.create_user(username='otro', rol='OPER', organismo=Organismo.objects.get(sigla='COPAIPA'))
        form = SolicitudFactibilidadForm(self.datos(), self.archivos())
        self.assertTrue(form.is_valid(), form.errors)
        self.t = Tramite.objects.create(**datos_para_tramite(form.cleaned_data))
        services.iniciar(self.t)
        services.recibir(self.t.pk, self.edesa)
        self.t.refresh_from_db()
        self.url = reverse('tramite_corregir', args=[self.t.pk])

    def observar(self):
        with self.captureOnCommitCallbacks(execute=True):
            return observaciones.observar(self.t.pk, self.edesa, 'Corregí el nombre y reemplazá la fotocopia ilegible del DNI.')

    def acceder(self):
        response = self.client.post(reverse('tramite_consultar'), {'numero': self.t.numero, 'nis': self.t.nis, 'dni_cuit': self.t.titular_dni_cuit})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['resultado'])

    def test_observacion_notifica_bloquea_y_es_auditable(self):
        obs = self.observar()
        self.t.refresh_from_db()
        self.assertEqual(self.t.estado_actual, 'OBSERVADO')
        self.assertEqual(services.acciones_disponibles(self.t), [])
        self.assertEqual(obs.usuario, self.edesa)
        self.assertIsNotNone(obs.creada_en)
        self.assertEqual(Notificacion.objects.get(evento='OBSERVACION').estado, 'ENVIADA')
        self.assertIn(obs.detalle, mail.outbox[-1].body)
        self.assertEqual(mail.outbox[-1].to, [self.t.titular_email])
        self.assertEqual(Auditoria.objects.get(accion='SOLICITUD_OBSERVADA').detalle['usuario_nombre'], 'edesa')
        self.client.force_login(self.edesa)
        self.assertEqual(self.client.get(reverse('institucional_dashboard')).context['pendientes'], 0)

    def test_autorizacion_y_recepcion_previa(self):
        with self.assertRaises(PermissionDenied):
            observaciones.observar(self.t.pk, self.otro, 'No autorizado')
        self.edesa.rol = 'CONS'
        with self.assertRaises(PermissionDenied):
            observaciones.observar(self.t.pk, self.edesa, 'No autorizado')
        self.edesa.rol = 'OPER'
        services.mover(self.t, 'ingreso-factibilidad')
        with self.assertRaises(PermissionDenied):
            observaciones.observar(self.t.pk, self.edesa, 'Primero recibir')

    def test_acceso_publico_requiere_tres_datos_y_formulario_precargado(self):
        self.observar()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.acceder()
        response = self.client.get(self.url)
        self.assertContains(response, 'value="Juan Titular"')
        self.assertContains(response, 'fotocopia ilegible')
        self.assertContains(response, 'data-subsanacion')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertFalse(response.context['form'].fields['dni_titular'].required)

    def test_subsanacion_con_reemplazo_y_nuevas_credenciales_y_recepcion(self):
        obs = self.observar()
        self.acceder()
        data = self.datos(titular_nombre='Titular Corregido', titular_dni='27123456', nis='999888', observacion_id=obs.pk)
        with patch('django.core.files.storage.FileSystemStorage.save', side_effect=AssertionError('No guardar archivos')):
            response = self.client.post(self.url, {**data, 'dni_titular': self.pdf()})
        self.assertEqual(response.status_code, 302)
        self.t.refresh_from_db()
        obs.refresh_from_db()
        self.assertEqual(self.t.estado_actual, 'SUBSANADO')
        self.assertEqual(self.t.titular_nombre, 'Titular Corregido')
        self.assertEqual(self.t.nis, '999888')
        self.assertTrue(self.t.verificar_documento_consulta('27123456'))
        self.assertFalse(self.t.verificar_documento_consulta('28123456'))
        self.assertIsNotNone(obs.subsanada_en)
        mensaje = mail.outbox[-1]
        self.assertIn('Subsanación', mensaje.subject)
        self.assertEqual(mensaje.to, ['edesa@example.com'])
        self.assertIn('Titular Corregido', mensaje.body)
        self.assertIn('27123456', mensaje.body)
        self.assertEqual(len(mensaje.attachments), 1)
        self.assertFalse(DocumentoTramite.objects.exists())
        self.assertEqual(list(Path(self.tmp.name).rglob('*')), [])
        self.assertEqual(Auditoria.objects.get(accion='SOLICITUD_SUBSANADA').detalle['actor'], 'CLIENTE')
        self.client.force_login(self.edesa)
        self.assertEqual(self.client.get(reverse('institucional_dashboard')).context['pendientes'], 1)
        services.recibir(self.t.pk, self.edesa)
        self.t.refresh_from_db()
        obs.refresh_from_db()
        self.assertEqual(self.t.estado_actual, 'PENDIENTE')
        self.assertIsNotNone(obs.recibida_en)
        self.assertEqual(self.t.etapa_actual.codigo, 'respuesta-factibilidad')
        # A second review may request another correction without overwriting history.
        self.observar()
        self.assertEqual(self.t.observaciones_solicitud.count(), 2)

    def test_smtp_falla_conserva_datos_y_observacion_abierta(self):
        obs = self.observar()
        self.acceder()
        with patch('apps.tramites.observaciones.enviar_solicitud', side_effect=OSError('privado')):
            response = self.client.post(self.url, self.datos(titular_nombre='No aplicar', observacion_id=obs.pk))
        self.assertContains(response, 'No se aplicaron las correcciones')
        self.assertNotContains(response, 'privado')
        self.t.refresh_from_db()
        obs.refresh_from_db()
        self.assertEqual(self.t.titular_nombre, 'Juan Titular')
        self.assertEqual(self.t.estado_actual, 'OBSERVADO')
        self.assertIsNone(obs.subsanada_en)

    def test_sin_archivos_apoderado_solo_datos_y_sin_reenvio_duplicado(self):
        obs = self.observar()
        self.acceder()
        data = self.datos(solicitante_condicion='APODERADO', observacion_id=obs.pk)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox[-1].attachments), 0)
        total = len(mail.outbox)
        self.client.post(self.url, data)
        self.assertEqual(len(mail.outbox), total)

    def test_version_observacion_y_archivos_invalidos(self):
        obs = self.observar()
        self.acceder()
        response = self.client.post(self.url, self.datos(observacion_id=obs.pk + 10))
        self.assertContains(response, 'La observación cambió')
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.client.post(self.url, {**self.datos(observacion_id=obs.pk), 'dni_titular': SimpleUploadedFile('mal.pdf', b'invalido')})
        self.assertContains(response, 'válido')
        self.t.refresh_from_db()
        self.assertEqual(self.t.estado_actual, 'OBSERVADO')

    def test_csrf_tambien_en_subsanacion(self):
        self.observar()
        session = self.client.session
        import time
        session['consulta_tramite'] = {'id': self.t.pk, 'hasta': time.time() + 60}
        session.save()
        cliente = Client(enforce_csrf_checks=True)
        cliente.cookies = self.client.cookies
        self.assertEqual(cliente.post(self.url, self.datos(observacion_id=1)).status_code, 403)
