import tempfile
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from django.utils import timezone
from apps.organismos.models import Organismo
from apps.workflow.circuito import configurar_circuito
from apps.workflow.models import TramiteEtapa
from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import enviar
from .models import Tramite, DocumentoTramite
from . import services


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CircuitoTests(TestCase):
    def setUp(self):
        cache.clear()
        configurar_circuito()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        setting = override_settings(PRIVATE_MEDIA_ROOT=self.tmp.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.users = {}
        for sigla in ['EDESA', 'COPAIPA', 'SECRETARÍA', 'ENRESP']:
            self.users[sigla] = get_user_model().objects.create_user(
                username=sigla, organismo=Organismo.objects.get(sigla=sigla), rol='OPER')
        self.cliente = Client()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.cliente.post('/tramites/nuevo/', {
                'nis': '123456', 'titular_nombre': 'Cliente de prueba',
                'titular_dni_cuit': '20301234567', 'titular_email': 'cliente@example.com',
                'solicitud_factibilidad': self.pdf(),
            })
        self.assertEqual(response.status_code, 200)
        self.t = Tramite.objects.get()

    def pdf(self):
        return SimpleUploadedFile('documento.pdf', b'%PDF-1.4\ncontenido de prueba', content_type='application/pdf')

    def abrir(self, sigla):
        self.client.force_login(self.users[sigla])
        response = self.client.get(reverse('institucional_tramite_detalle', args=[self.t.pk]))
        self.assertEqual(response.status_code, 200)
        if response.context['requiere_recepcion']:
            self.client.post(reverse('institucional_tramite_detalle', args=[self.t.pk]), {
                'accion': 'recibir', 'etapa': response.context['tramite'].etapa_actual.codigo,
            })
            response = self.client.get(reverse('institucional_tramite_detalle', args=[self.t.pk]))
        self.t.refresh_from_db()
        return response

    def accion(self, sigla, accion, **extra):
        self.t.refresh_from_db()
        self.client.force_login(self.users[sigla])
        data = {'accion': accion, 'etapa': self.t.etapa_actual.codigo, **extra}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('institucional_tramite_detalle', args=[self.t.pk]), data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:1000])
        self.t.refresh_from_db()
        return response

    def respuesta(self):
        self.abrir('EDESA')
        self.accion('EDESA', 'respuesta', archivo=self.pdf())

    def consultar(self, **extra):
        return self.cliente.post('/tramites/consultar/', {
            'numero': self.t.numero, 'nis': self.t.nis, 'dni_cuit': self.t.titular_dni_cuit, **extra})

    def test_circuito_completo_con_documentos_correos_y_autoria(self):
        self.assertRegex(self.t.numero, r'^GGER-[A-F0-9]{48}$')
        self.assertEqual(self.t.etapa_actual.codigo, 'ingreso-factibilidad')
        self.assertEqual(self.t.organismo_actual.sigla, 'EDESA')
        self.assertIn(self.t.numero, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['cliente@example.com'])
        # Otro organismo puede ver, pero no acusar recepción.
        self.abrir('COPAIPA')
        self.assertEqual(self.t.etapa_actual.codigo, 'ingreso-factibilidad')
        self.abrir('EDESA')
        self.assertEqual(self.t.etapa_actual.codigo, 'respuesta-factibilidad')
        self.assertEqual(self.t.estado_actual, 'PENDIENTE')
        self.abrir('EDESA')
        self.assertEqual(self.t.auditorias.filter(accion='RECIBIDO').count(), 1)
        self.accion('EDESA', 'respuesta', archivo=self.pdf())
        self.assertEqual(self.t.estado_actual, 'PENDIENTE_CLIENTE')
        self.assertEqual(mail.outbox[-1].attachments[0][0], 'Respuesta de factibilidad.pdf')
        self.assertTrue(self.t.auditorias.filter(accion='RESPUESTA_ENVIADA').exists())
        response = self.consultar()
        self.assertContains(response, 'Presentá tu Proyecto Ejecutivo')
        response = self.cliente.post(reverse('tramite_proyecto', args=[self.t.pk]), {'archivo': self.pdf()})
        self.assertEqual(response.status_code, 302)
        self.t.refresh_from_db()
        self.assertEqual(self.t.estado_actual, 'PROYECTO_ENVIADO')
        self.client.force_login(self.users['EDESA'])
        self.assertContains(self.client.get('/institucional/'), 'Proyecto enviado')
        self.abrir('EDESA')
        self.assertEqual(self.t.estado_actual, 'RECIBIDO')
        self.accion('EDESA', 'previsar')
        self.assertEqual(self.t.organismo_actual.sigla, 'COPAIPA')
        self.abrir('COPAIPA')
        self.assertEqual(self.t.estado_actual, 'RECIBIDO')
        self.accion('COPAIPA', 'copaipa', archivo=self.pdf())
        self.abrir('SECRETARÍA')
        self.accion('SECRETARÍA', 'expediente', expediente='EXP-2026-000123')
        self.assertEqual(self.t.estado_actual, 'EXPEDIENTE_ASOCIADO')
        self.accion('SECRETARÍA', 'dictamen', archivo=self.pdf())
        self.abrir('ENRESP')
        self.accion('ENRESP', 'resolucion', archivo=self.pdf())
        self.assertEqual(self.t.organismo_actual.sigla, 'EDESA')
        self.abrir('EDESA')
        self.assertEqual(self.t.estado_actual, 'RECIBIDO')
        self.accion('EDESA', 'convocar', observacion='Acercate a la oficina de EDESA con tu DNI.')
        self.assertEqual(self.t.estado_actual, 'CONVOCADO')
        self.assertIn('oficina de EDESA', mail.outbox[-1].body)
        self.accion('EDESA', 'contrato', archivo=self.pdf())
        self.accion('EDESA', 'programar', fecha=timezone.now() + timedelta(days=1))
        self.assertEqual(self.t.estado_actual, 'PROGRAMADA')
        self.accion('EDESA', 'inspeccionar', fecha=timezone.now())
        self.accion('EDESA', 'conectar', fecha=timezone.now())
        self.assertEqual(self.t.estado_actual, 'FINALIZADO')
        self.assertIsNotNone(self.t.conexion_realizada)
        self.assertEqual(self.t.documentos.count(), 7)
        self.assertEqual(self.t.etapas_historial.filter(estado__in=services.HISTORIAL_COMPLETO).count(), 13)
        # Todos los organismos ven el cierre. Ninguna nueva visita lo altera.
        for sigla in self.users:
            response = self.abrir(sigla)
            self.assertContains(response, 'Conexión realizada')
            self.assertFalse(response.context['acciones'])
        response = self.consultar()
        self.assertContains(response, 'Trámite finalizado')
        self.assertContains(response, 'Contrato firmado')
        # Cada recepción institucional conserva usuario, organismo y fecha/hora.
        recepciones = self.t.auditorias.filter(accion__in=['RECIBIDO', 'PROYECTO_RECIBIDO'])
        self.assertEqual(recepciones.count(), 6)
        for evento in recepciones:
            self.assertIsNotNone(evento.usuario_id)
            self.assertTrue(timezone.is_aware(evento.creado_en))
            self.assertEqual(evento.detalle['usuario_nombre'], evento.usuario.username)
            self.assertEqual(evento.detalle['organismo_usuario'], evento.usuario.organismo.sigla)
        for documento in self.t.documentos.exclude(tipo__in=['SOLICITUD', 'PROYECTO']):
            self.assertIsNotNone(documento.usuario_id)

    def test_otro_organismo_no_puede_actuar_aunque_falsifique_post(self):
        self.abrir('EDESA')
        self.client.force_login(self.users['COPAIPA'])
        response = self.client.post(reverse('institucional_tramite_detalle', args=[self.t.pk]), {
            'accion': 'respuesta', 'etapa': 'respuesta-factibilidad', 'archivo': self.pdf()})
        self.assertEqual(response.status_code, 403)
        self.t.refresh_from_db()
        self.assertEqual(self.t.estado_actual, 'PENDIENTE')
        self.assertFalse(self.t.documentos.filter(tipo='RESPUESTA').exists())

    def test_rol_consulta_y_usuario_sin_organismo_no_reciben_ni_modifican(self):
        user = self.users['EDESA']
        user.rol = 'CONS'
        user.save()
        self.abrir('EDESA')
        self.assertEqual(self.t.etapa_actual.codigo, 'ingreso-factibilidad')
        self.assertTrue(self.t.auditorias.filter(accion='CONSULTA_EXPEDIENTE', usuario=user).exists())
        user.organismo = None
        user.save()
        self.assertEqual(self.client.get('/institucional/').status_code, 403)

    def test_archivos_privados_y_acceso_cliente_vencido(self):
        doc = self.t.documentos.get(tipo='SOLICITUD')
        url = reverse('tramite_documento', args=[doc.pk])
        self.assertEqual(self.cliente.get(url).status_code, 403)
        self.consultar()
        response = self.cliente.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF-'))
        session = self.cliente.session
        session['consulta_tramite'] = {'id': self.t.pk, 'hasta': 0}
        session.save()
        self.assertEqual(self.cliente.get(url).status_code, 403)
        self.assertEqual(self.cliente.post(reverse('tramite_proyecto', args=[self.t.pk]), {'archivo': self.pdf()}).status_code, 403)
        self.assertEqual(self.client.get('/media/' + doc.archivo.name).status_code, 404)
        self.consultar(nis='incorrecto')
        self.assertNotIn('consulta_tramite', self.cliente.session)

    def test_cliente_no_puede_presentar_proyecto_antes_de_respuesta_ni_duplicarlo(self):
        self.consultar()
        url = reverse('tramite_proyecto', args=[self.t.pk])
        self.assertEqual(self.cliente.post(url, {'archivo': self.pdf()}).status_code, 200)
        self.assertFalse(self.t.documentos.filter(tipo='PROYECTO').exists())
        self.respuesta()
        self.cliente.post(url, {'archivo': self.pdf()})
        response = self.cliente.post(url, {'archivo': self.pdf()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.t.documentos.filter(tipo='PROYECTO').count(), 1)

    def test_fallo_smtp_no_avanza_respuesta_y_reintento_no_duplica_correo(self):
        self.abrir('EDESA')
        with patch('django.core.mail.message.EmailMessage.send', side_effect=OSError('SMTP no disponible')):
            self.accion('EDESA', 'respuesta', archivo=self.pdf())
        self.assertEqual(self.t.estado_actual, 'PENDIENTE_ENVIO')
        aviso = Notificacion.objects.get(evento='RESPUESTA')
        self.assertEqual(aviso.estado, 'ERROR')
        self.assertEqual(aviso.intentos, 1)
        self.assertTrue(enviar(aviso.pk))
        self.t.refresh_from_db()
        self.assertEqual(self.t.estado_actual, 'PENDIENTE_CLIENTE')
        cantidad = len(mail.outbox)
        self.assertTrue(enviar(aviso.pk))
        self.assertEqual(len(mail.outbox), cantidad)
        self.assertEqual(self.t.documentos.filter(tipo='RESPUESTA').count(), 1)

    def test_no_se_puede_saltar_expediente_ni_enviar_sin_archivo(self):
        self.abrir('EDESA')
        response = self.client.post(reverse('institucional_tramite_detalle', args=[self.t.pk]), {
            'accion': 'respuesta', 'etapa': 'respuesta-factibilidad'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Esta actuación requiere un documento.')
        self.assertFalse(self.t.documentos.filter(tipo='RESPUESTA').exists())
        services.mover(self.t, 'dictamen-expediente')
        with self.assertRaises(ValidationError):
            services.actuar(self.t.pk, self.users['SECRETARÍA'], {
                'accion': 'dictamen', 'etapa': 'dictamen-expediente', 'archivo': self.pdf()})

    def test_formulario_viejo_no_puede_repetir_una_actuacion(self):
        self.abrir('EDESA')
        data = {'accion': 'respuesta', 'etapa': 'respuesta-factibilidad', 'archivo': self.pdf()}
        with self.captureOnCommitCallbacks(execute=True):
            services.actuar(self.t.pk, self.users['EDESA'], data)
        with self.assertRaises(ValidationError):
            services.actuar(self.t.pk, self.users['EDESA'], {**data, 'archivo': self.pdf()})
        self.assertEqual(self.t.documentos.filter(tipo='RESPUESTA').count(), 1)

    def test_archivo_falso_y_superior_a_limite_son_rechazados(self):
        from .forms import DocumentoForm
        self.assertFalse(DocumentoForm(files={'archivo': SimpleUploadedFile('falso.pdf', b'contenido sin PDF')}).is_valid())
        self.assertFalse(DocumentoForm(files={'archivo': SimpleUploadedFile('exceso.pdf', b'%PDF-' + b'x' * (10 * 1024 * 1024))}).is_valid())

    def test_fechas_invalidas_no_permiten_finalizar_ni_programar_en_pasado(self):
        services.mover(self.t, 'inspeccion')
        with self.assertRaises(ValidationError):
            services.actuar(self.t.pk, self.users['EDESA'], {
                'accion': 'programar', 'etapa': 'inspeccion', 'fecha': timezone.now() - timedelta(days=1)})
        services.mover(self.t, 'conexion-red')
        with self.assertRaises(ValidationError):
            services.actuar(self.t.pk, self.users['EDESA'], {
                'accion': 'conectar', 'etapa': 'conexion-red', 'fecha': timezone.now()})
        self.t.refresh_from_db()
        self.assertNotEqual(self.t.estado_actual, 'FINALIZADO')

    def test_codigo_cliente_no_da_acceso_a_documentos_de_otro_tramite(self):
        self.consultar()
        otro = Tramite.objects.create(nis='otro', titular_nombre='Otro', titular_dni_cuit='otro', titular_email='otro@example.com')
        doc = DocumentoTramite.objects.create(tramite=otro, tipo='CONTRATO', archivo=self.pdf())
        self.assertEqual(self.cliente.get(reverse('tramite_documento', args=[doc.pk])).status_code, 403)

    def test_respuesta_requiere_csrf_y_consulta_tiene_limite_de_intentos(self):
        protegido = Client(enforce_csrf_checks=True)
        self.assertEqual(protegido.post('/tramites/consultar/', {}).status_code, 403)
        for _ in range(15):
            self.consultar(nis='incorrecto')
        self.assertEqual(self.consultar().status_code, 429)

    def test_convocatoria_fallida_no_permite_subir_contrato_hasta_reintentar(self):
        services.mover(self.t, 'firma-contrato')
        self.abrir('EDESA')
        with patch('django.core.mail.message.EmailMessage.send', side_effect=OSError('SMTP no disponible')):
            self.accion('EDESA', 'convocar', observacion='Presentarse en EDESA con DNI.')
        self.assertEqual(self.t.estado_actual, 'PENDIENTE_ENVIO')
        with self.assertRaises(ValidationError):
            services.actuar(self.t.pk, self.users['EDESA'], {
                'accion': 'contrato', 'etapa': 'firma-contrato', 'archivo': self.pdf()})
        aviso = Notificacion.objects.get(evento='CONVOCATORIA')
        self.client.force_login(self.users['COPAIPA'])
        self.assertEqual(self.client.post(reverse('institucional_reintentar_correo', args=[aviso.pk])).status_code, 403)
        self.client.force_login(self.users['EDESA'])
        self.assertEqual(self.client.post(reverse('institucional_reintentar_correo', args=[aviso.pk])).status_code, 302)
        self.t.refresh_from_db()
        self.assertEqual(self.t.estado_actual, 'CONVOCADO')
        self.assertTrue(self.t.auditorias.filter(accion='REINTENTO_CORREO', usuario=self.users['EDESA']).exists())

    def test_abrir_no_cambia_estado_hasta_confirmar_recepcion(self):
        self.client.force_login(self.users['EDESA'])
        url = reverse('institucional_tramite_detalle', args=[self.t.pk])
        response = self.client.get(url)
        self.assertTrue(response.context['requiere_recepcion'])
        self.t.refresh_from_db()
        self.assertEqual(self.t.etapa_actual.codigo, 'ingreso-factibilidad')
        self.assertFalse(self.t.auditorias.filter(accion='RECIBIDO').exists())
        self.client.post(url, {'accion': 'recibir', 'etapa': 'ingreso-factibilidad'})
        self.t.refresh_from_db()
        self.assertEqual(self.t.etapa_actual.codigo, 'respuesta-factibilidad')
        self.assertEqual(self.t.auditorias.filter(accion='RECIBIDO').count(), 1)

    def test_portal_publico_sin_sidebar_aun_con_usuario_institucional(self):
        self.client.force_login(self.users['EDESA'])
        for path in ['/', '/tramites/nuevo/', '/tramites/consultar/', '/acceso/']:
            response = self.client.get(path)
            self.assertNotContains(response, 'id="app-navigation"')
            self.assertContains(response, 'ui-theme-toggle')
        self.assertContains(self.client.get('/institucional/'), 'id="app-navigation"')
