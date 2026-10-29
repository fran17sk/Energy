import tempfile
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.organismos.models import Organismo
from apps.workflow.circuito import configurar_circuito
from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import enviar
from apps.reportes.services import construir_reporte
from .models import Tramite, DocumentoTramite
from .forms import AccionTramiteForm
from . import services


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CircuitoNexoTests(TestCase):
    def setUp(self):
        cache.clear()
        configurar_circuito()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        setting = override_settings(PRIVATE_MEDIA_ROOT=self.tmp.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.users = {sigla: get_user_model().objects.create_user(username=sigla, rol='OPER',
            organismo=Organismo.objects.get(sigla=sigla)) for sigla in ['EDESA', 'COPAIPA', 'SECRETARÍA', 'ENRESP']}
        self.gger = Tramite.objects.create(nis='123456', titular_nombre='Titular de los dos proyectos',
            titular_dni_cuit='28123456', titular_email='cliente@example.com')
        services.iniciar(self.gger)
        services.recibir(self.gger.pk, self.users['EDESA'])
        self.gger.refresh_from_db()
        self.cliente = Client()

    def pdf(self):
        return SimpleUploadedFile('documento.pdf', b'%PDF-1.4\nproyecto de prueba', content_type='application/pdf')

    def actuar(self, tramite, sigla, accion, **datos):
        tramite.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            services.actuar(tramite.pk, self.users[sigla], {'accion': accion, 'etapa': tramite.etapa_actual.codigo, **datos})
        tramite.refresh_from_db()

    def habilitar(self):
        self.actuar(self.gger, 'EDESA', 'respuesta', archivo=self.pdf(), recorrido='CON_NEXO')
        return self.gger.obra_nexo

    def consultar(self):
        return self.cliente.post(reverse('tramite_consultar'), {'numero': self.gger.numero, 'nis': self.gger.nis,
            'dni_cuit': self.gger.titular_dni_cuit})

    def hasta_conexion(self, t):
        services.presentar_proyecto(t.pk, self.pdf())
        self.actuar(t, 'EDESA', 'recibir')
        self.actuar(t, 'EDESA', 'previsar')
        self.actuar(t, 'COPAIPA', 'recibir')
        self.actuar(t, 'COPAIPA', 'copaipa', archivo=self.pdf())
        self.actuar(t, 'SECRETARÍA', 'recibir')
        self.actuar(t, 'SECRETARÍA', 'expediente', expediente='EXP-NEXO' if t.es_nexo else 'EXP-GGER')
        self.actuar(t, 'SECRETARÍA', 'dictamen', archivo=self.pdf())
        self.actuar(t, 'ENRESP', 'recibir')
        self.actuar(t, 'ENRESP', 'resolucion', archivo=self.pdf())
        self.actuar(t, 'EDESA', 'recibir')
        self.actuar(t, 'EDESA', 'convocar', observacion='Presentarse en oficinas para firmar el contrato de ' + t.circuito_display)
        self.actuar(t, 'EDESA', 'contrato', archivo=self.pdf())
        self.actuar(t, 'EDESA', 'programar', fecha=timezone.now() + timedelta(days=1))
        self.actuar(t, 'EDESA', 'inspeccionar', fecha=timezone.now())

    def test_eleccion_explicita_y_circuito_normal_sin_nexo(self):
        form = AccionTramiteForm({'accion': 'respuesta', 'etapa': 'respuesta-factibilidad'}, {'archivo': self.pdf()},
            acciones=services.acciones_disponibles(self.gger))
        self.assertFalse(form.is_valid())
        self.assertIn('recorrido', form.errors)
        with self.assertRaises(ValidationError):
            self.actuar(self.gger, 'EDESA', 'respuesta', archivo=self.pdf())
        self.assertFalse(self.gger.documentos.exists())
        self.actuar(self.gger, 'EDESA', 'respuesta', archivo=self.pdf(), recorrido='GGER')
        self.assertFalse(self.gger.requiere_nexo)
        self.assertIsNone(self.gger.nexo_asociado)
        self.assertFalse(self.gger.conexion_bloqueada)

    def test_mismo_numero_dos_circuitos_y_correo_con_instrucciones(self):
        nexo = self.habilitar()
        self.assertEqual(nexo.numero, self.gger.numero)
        self.assertEqual(nexo.codigo_consulta, self.gger.numero)
        self.assertEqual(nexo.estado_actual, 'PENDIENTE_CLIENTE')
        self.assertEqual(nexo.etapa_actual.codigo, 'presentacion-proyecto-ejecutivo')
        self.assertFalse(nexo.requiere_nexo)
        self.assertTrue(self.gger.conexion_bloqueada)
        self.assertIn('proyecto de obra de nexo', mail.outbox[-1].body)
        self.assertEqual(self.gger.documentos.count(), 1)
        self.assertEqual(nexo.documentos.count(), 0)
        self.assertEqual(self.gger.auditorias.get(accion='RESPUESTA').detalle['recorrido'], 'CON_NEXO')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tramite.objects.create(numero=self.gger.numero, nis='otro', titular_email='otro@example.com')

    def test_dos_presentaciones_independientes_y_acceso_documentos(self):
        nexo = self.habilitar()
        response = self.consultar()
        self.assertContains(response, 'Proyecto Ejecutivo GGER')
        self.assertContains(response, 'proyecto de obra de nexo')
        self.assertContains(response, 'name="nexo-archivo"')
        url = reverse('tramite_proyecto', args=[nexo.pk])
        self.assertEqual(Client().post(url, {'nexo-archivo': self.pdf()}).status_code, 403)
        self.assertEqual(self.cliente.post(url, {'nexo-archivo': self.pdf()}).status_code, 302)
        self.gger.refresh_from_db()
        self.assertEqual(self.gger.estado_actual, 'PENDIENTE_CLIENTE')
        nexo.refresh_from_db()
        self.assertEqual(nexo.estado_actual, 'PROYECTO_ENVIADO')
        doc = nexo.documentos.get(tipo='PROYECTO')
        self.assertEqual(self.cliente.get(reverse('tramite_documento', args=[doc.pk])).status_code, 200)
        self.assertEqual(Client().get(reverse('tramite_documento', args=[doc.pk])).status_code, 403)
        self.assertEqual(self.cliente.post(reverse('tramite_proyecto', args=[self.gger.pk]), {'archivo': self.pdf()}).status_code, 302)
        self.assertEqual(self.gger.documentos.filter(tipo='PROYECTO').count(), 1)
        self.assertEqual(nexo.documentos.filter(tipo='PROYECTO').count(), 1)
        self.assertEqual(self.cliente.post(url, {'nexo-archivo': self.pdf()}).status_code, 200)
        self.assertEqual(nexo.documentos.filter(tipo='PROYECTO').count(), 1)

    def test_permisos_por_circuito_y_etapas_independientes(self):
        nexo = self.habilitar()
        services.presentar_proyecto(self.gger.pk, self.pdf())
        self.actuar(self.gger, 'EDESA', 'recibir')
        self.actuar(self.gger, 'EDESA', 'previsar')
        self.assertEqual(self.gger.organismo_actual.sigla, 'COPAIPA')
        nexo.refresh_from_db()
        self.assertEqual(nexo.organismo_actual.sigla, 'EDESA')
        self.assertEqual(nexo.estado_actual, 'PENDIENTE_CLIENTE')
        self.assertTrue(services.puede_actuar(self.users['COPAIPA'], self.gger))
        self.assertFalse(services.puede_actuar(self.users['COPAIPA'], nexo))
        with self.assertRaises(PermissionDenied):
            self.actuar(nexo, 'COPAIPA', 'previsar')
        self.client.force_login(self.users['COPAIPA'])
        self.assertEqual(self.client.get(reverse('institucional_tramite_detalle', args=[nexo.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse('institucional_tramite_detalle', args=[nexo.pk]), {'accion': 'recibir', 'etapa': nexo.etapa_actual.codigo}).status_code, 403)

    def test_circuitos_completos_y_bloqueo_hasta_finalizar_nexo(self):
        nexo = self.habilitar()
        self.hasta_conexion(self.gger)
        self.assertEqual(services.acciones_disponibles(self.gger), [])
        with self.assertRaisesMessage(ValidationError, 'hasta que EDESA registre la finalización'):
            self.actuar(self.gger, 'EDESA', 'conectar', fecha=timezone.now())
        self.assertIsNone(self.gger.conexion_realizada)
        self.hasta_conexion(nexo)
        self.assertEqual(nexo.expediente_administrativo, 'EXP-NEXO')
        self.assertEqual(self.gger.expediente_administrativo, 'EXP-GGER')
        self.assertTrue(self.gger.conexion_bloqueada)
        self.actuar(nexo, 'EDESA', 'conectar', fecha=timezone.now())
        self.gger.refresh_from_db()
        self.assertFalse(self.gger.conexion_bloqueada)
        self.assertNotEqual(self.gger.estado_actual, 'FINALIZADO')
        self.assertIn(('conectar', 'Registrar conexión y finalizar trámite'), services.acciones_disponibles(self.gger))
        self.assertIn(self.gger.numero, mail.outbox[-1].body)
        self.assertIn('Obra de nexo', mail.outbox[-1].subject)
        self.actuar(self.gger, 'EDESA', 'conectar', fecha=timezone.now())
        self.assertEqual(self.gger.estado_actual, 'FINALIZADO')
        self.assertEqual(nexo.estado_actual, 'FINALIZADO')
        self.assertEqual(nexo.documentos.count(), 5)  # proyecto, tres organismos, contrato
        self.assertEqual(self.gger.documentos.count(), 6)  # incluye la factibilidad compartida
        self.assertEqual(nexo.auditorias.get(accion='CONECTAR').detalle['circuito'], 'Obra de nexo')
        response = self.consultar()
        self.assertContains(response, 'Finalizado · obra de nexo registrada')
        self.assertContains(response, 'Conexión registrada:')

    def test_no_se_puede_fechar_conexion_gger_antes_del_cierre_del_nexo(self):
        nexo = self.habilitar()
        ahora = timezone.now()
        for t in [self.gger, nexo]:
            services.mover(t, 'conexion-red')
            t.inspeccion_realizada = ahora - timedelta(hours=2)
            t.save()
        self.actuar(nexo, 'EDESA', 'conectar', fecha=ahora - timedelta(minutes=20))
        with self.assertRaisesMessage(ValidationError, 'anterior a la finalización'):
            self.actuar(self.gger, 'EDESA', 'conectar', fecha=ahora - timedelta(hours=1))
        self.assertIsNone(self.gger.conexion_realizada)

    def test_nexo_puede_finalizar_antes_que_gger_se_presente(self):
        nexo = self.habilitar()
        self.hasta_conexion(nexo)
        self.actuar(nexo, 'EDESA', 'conectar', fecha=timezone.now())
        self.gger.refresh_from_db()
        self.assertEqual(self.gger.estado_actual, 'PENDIENTE_CLIENTE')
        self.assertFalse(self.gger.conexion_bloqueada)

    def test_fallo_correo_y_reintento_crea_un_solo_nexo(self):
        with patch('django.core.mail.message.EmailMessage.send', side_effect=OSError('SMTP')):
            self.actuar(self.gger, 'EDESA', 'respuesta', archivo=self.pdf(), recorrido='CON_NEXO')
        self.assertEqual(self.gger.estado_actual, 'PENDIENTE_ENVIO')
        self.assertIsNone(self.gger.nexo_asociado)
        aviso = Notificacion.objects.get(tramite=self.gger, evento='RESPUESTA')
        self.assertTrue(enviar(aviso.pk))
        self.assertTrue(enviar(aviso.pk))
        self.gger.refresh_from_db()
        self.assertEqual(Tramite.objects.filter(tramite_gger=self.gger).count(), 1)
        self.assertEqual(self.gger.obra_nexo.numero, self.gger.numero)
        self.assertEqual(self.gger.estado_actual, 'PENDIENTE_CLIENTE')

    def test_consulta_y_documentos_no_cruzan_expedientes(self):
        nexo = self.habilitar()
        self.consultar()
        otro = Tramite.objects.create(nis='otro', titular_dni_cuit='otro', titular_email='otro@example.com')
        child = Tramite.objects.create(tramite_gger=otro, nis='otro', titular_email='otro@example.com')
        services.mover(child, 'presentacion-proyecto-ejecutivo', 'PENDIENTE_CLIENTE')
        self.assertEqual(self.cliente.post(reverse('tramite_proyecto', args=[child.pk]), {'nexo-archivo': self.pdf()}).status_code, 403)
        doc = DocumentoTramite.objects.create(tramite=child, tipo='PROYECTO', archivo=self.pdf())
        self.assertEqual(self.cliente.get(reverse('tramite_documento', args=[doc.pk])).status_code, 403)
        response = self.consultar()
        self.assertEqual(response.context['resultado'].pk, self.gger.pk)
        self.assertEqual(response.context['nexo'].pk, nexo.pk)

    def test_reportes_y_dashboard_no_duplican_expediente(self):
        nexo = self.habilitar()
        hoy = timezone.localdate()
        principal = construir_reporte(hoy, hoy)
        secundario = construir_reporte(hoy, hoy, circuito='NEXO')
        self.assertEqual(principal['total'], 1)
        self.assertEqual(secundario['total'], 1)
        self.assertEqual(secundario['circuito_filtro'], 'Obra de nexo')
        self.client.force_login(self.users['EDESA'])
        response = self.client.get(reverse('institucional_dashboard'))
        self.assertEqual(response.context['total'], 1)
        self.assertEqual(response.context['total_nexos'], 1)
        self.assertEqual(response.context['pendientes'], 0)
        response = self.client.get(reverse('institucional_reportes_exportar'), {'circuito': 'NEXO'})
        self.assertContains(response, 'Circuito seleccionado;Obra de nexo')
