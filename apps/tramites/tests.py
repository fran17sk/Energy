from django.test import TestCase
from apps.tramites.models import Tramite

class TramiteModelTests(TestCase):
    def test_generates_unique_number(self):
        t = Tramite.objects.create(nis='123', titular_nombre='Juan Pérez', titular_dni_cuit='20123456789', titular_email='juan@example.com')
        self.assertTrue(t.numero.startswith('GGER-'))


class ConsultaTramiteTests(TestCase):
    def setUp(self):
        from apps.workflow.models import Etapa, TramiteEtapa
        Etapa.objects.all().delete()
        self.anterior = Etapa.objects.create(orden=1, codigo='ingreso', nombre='Ingreso')
        self.actual = Etapa.objects.create(orden=2, codigo='revision', nombre='Revisión')
        self.futura = Etapa.objects.create(orden=3, codigo='conexion', nombre='Conexión')
        self.tramite = Tramite.objects.create(
            nis='123', titular_nombre='Juan', titular_dni_cuit='20123456789',
            titular_email='juan@example.com', etapa_actual=self.actual,
        )
        TramiteEtapa.objects.create(tramite=self.tramite, etapa=self.anterior, estado='APROBADO')
        self.datos = {'numero': self.tramite.numero.lower(), 'nis': '123', 'dni_cuit': '20123456789'}

    def test_resultado_muestra_etapa_actual_e_historial(self):
        response = self.client.post('/tramites/consultar/', self.datos)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p['estado'] for p in response.context['seguimiento']], ['done', 'current', 'pending'])
        self.assertContains(response, 'aria-current="step"')
        self.assertContains(response, 'Revisión')
        self.assertNotContains(response, 'id="consulta-no-encontrado"')

    def test_datos_no_coincidentes_muestran_alerta_sin_exponer_resultado(self):
        response = self.client.post('/tramites/consultar/', {**self.datos, 'nis': 'otro'})
        self.assertTrue(response.context['no_encontrado'])
        self.assertIsNone(response.context['resultado'])
        self.assertContains(response, 'id="consulta-no-encontrado"')
        self.assertNotContains(response, 'id="resultado-title"')

    def test_formulario_incompleto_muestra_validacion_sin_alerta(self):
        response = self.client.post('/tramites/consultar/', {'numero': self.tramite.numero})
        self.assertFalse(response.context['no_encontrado'])
        self.assertTrue(response.context['form'].errors)

    def test_sin_etapa_no_infiere_completadas(self):
        self.tramite.etapa_actual = None
        self.tramite.save()
        self.tramite.etapas_historial.all().delete()
        response = self.client.post('/tramites/consultar/', self.datos)
        self.assertContains(response, 'Pendiente de asignación')
        self.assertTrue(all(p['estado'] == 'pending' for p in response.context['seguimiento']))


class AltaTramiteTests(TestCase):
    def test_registro_con_adjunto_muestra_numero_y_guarda_archivo(self):
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        with tempfile.TemporaryDirectory() as media, self.settings(PRIVATE_MEDIA_ROOT=media):
            response = self.client.post('/tramites/nuevo/', {
                'nis': '456', 'titular_nombre': 'María Pérez',
                'titular_dni_cuit': '30123456', 'titular_email': 'maria@example.com',
                'solicitud_factibilidad': SimpleUploadedFile('solicitud.pdf', b'%PDF-1.4\nprueba', content_type='application/pdf'),
            })
            self.assertEqual(response.status_code, 200)
            tramite = Tramite.objects.get(nis='456')
            self.assertContains(response, tramite.numero)
            self.assertContains(response, '¡Tu trámite ya tiene número!')
            self.assertTrue(tramite.solicitud_factibilidad.storage.exists(tramite.solicitud_factibilidad.name))

    def test_datos_invalidos_se_conservan_y_no_crean_tramite(self):
        response = self.client.post('/tramites/nuevo/', {
            'nis': '456', 'titular_nombre': 'María Pérez',
            'titular_dni_cuit': '30123456', 'titular_email': 'correo-invalido',
        })
        self.assertEqual(Tramite.objects.count(), 0)
        self.assertContains(response, 'Revisá los datos antes de continuar.')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="María Pérez"')
