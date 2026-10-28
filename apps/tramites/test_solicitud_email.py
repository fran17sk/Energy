import tempfile
from pathlib import Path
from unittest.mock import patch
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile, InMemoryUploadedFile
from django.db import connection
from django.test import TestCase, Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from apps.auditoria.models import Auditoria
from apps.notificaciones.models import Notificacion
from .models import Tramite, DocumentoTramite
from .solicitud_forms import SolicitudFactibilidadForm, DEPARTAMENTOS_SALTA


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', EDESA_SOLICITUD_EMAIL='recepcion-edesa@example.com')
class SolicitudEmailTests(TestCase):
    def datos(self, **cambios):
        return {
            'propietario_tipo': 'HUMANA', 'propietario_nombre': 'Ana Propietaria', 'propietario_dni': '30123456',
            'titular_tipo': 'HUMANA', 'titular_nombre': 'Juan Titular', 'titular_dni': '28123456',
            'nis': '123456789', 'potencia_contratada_kw': '10.5', 'catastro': 'CAT-12345', 'departamento': 'Capital',
            'tecnologia': 'FOTOVOLTAICO', 'tipo_conexion': 'MONOFASICA_220', 'potencia_inyectada_kw': '5.25',
            'coordenadas_pilar': '-24.7821, -65.4232', 'solicitante_condicion': 'TITULAR',
            'solicitante_nombre': 'Juan Solicitante', 'solicitante_dni': '28123456',
            'solicitante_celular': '+54 387 1234567', 'solicitante_email': 'solicitante@example.com', **cambios,
        }

    def pdf(self, nombre='documento.pdf', size=32):
        return SimpleUploadedFile(nombre, b'%PDF-1.4\n' + b'x' * max(0, size - 9), content_type='application/pdf')

    def archivos(self, apoderado=False):
        files = {'formulario_digital': self.pdf('formulario.pdf'), 'dni_titular': self.pdf('dni.pdf')}
        if apoderado:
            files.update(dni_apoderado=self.pdf('apoderado.pdf'), poder_apoderado=self.pdf('poder.pdf'))
        return files

    def test_envia_toda_la_informacion_y_adjuntos_con_registro_minimo(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
        self.assertEqual(response.status_code, 303)
        tramite = Tramite.objects.get()
        self.assertEqual(tramite.nis, '123456789')
        self.assertEqual(tramite.titular_email, 'solicitante@example.com')
        self.assertTrue(tramite.presentacion_por_correo)
        self.assertEqual(tramite.titular_nombre, '')
        self.assertEqual(tramite.titular_dni_cuit, '')
        self.assertTrue(tramite.verificar_documento_consulta('28123456'))
        self.assertEqual(tramite.catastro, '')
        self.assertEqual(tramite.departamento, '')
        self.assertEqual(tramite.tecnologia, '')
        self.assertEqual(tramite.coordenadas_pilar, '')
        self.assertEqual(tramite.titular_telefono, '')
        self.assertIsNone(tramite.potencia_contratada_kw)
        self.assertIsNone(tramite.potencia_inyectada_kw)
        self.assertFalse(tramite.solicitud_factibilidad)
        self.assertEqual(DocumentoTramite.objects.count(), 0)
        self.assertEqual(tramite.etapa_actual.codigo, 'ingreso-factibilidad')
        self.assertEqual(tramite.organismo_actual.sigla, 'EDESA')
        sql = '\n'.join(q['sql'] for q in queries)
        for privado in ['Ana Propietaria', 'Juan Titular', '30123456', '28123456', 'CAT-12345', '-24.7821', '+54 387 1234567']:
            self.assertNotIn(privado, sql)
        mensaje = mail.outbox[0]
        self.assertEqual(mensaje.to, ['recepcion-edesa@example.com'])
        self.assertEqual(mensaje.reply_to, ['solicitante@example.com'])
        for dato in ['Ana Propietaria', '30123456', 'Juan Titular', '28123456', '123456789',
                     '10.5', 'CAT-12345', 'Capital', 'Sistema fotovoltaico', 'Monofásica (220 V)',
                     '5.25', '-24.7821, -65.4232', 'Juan Solicitante', '+54 387 1234567', 'solicitante@example.com']:
            self.assertIn(dato, mensaje.body)
        self.assertEqual([a.filename for a in mensaje.attachments], ['formulario-digital.pdf', 'dni-titular.pdf'])
        for archivo in mensaje.attachments:
            self.assertTrue(archivo.content.startswith(b'%PDF-'))
        self.assertEqual(mensaje.alternatives[0].mimetype, 'text/html')
        self.assertContains(self.client.get(response.url), 'Tu solicitud fue enviada a EDESA.')
        self.assertIn('no-store', response['Cache-Control'])

    def test_cuit_para_personas_juridicas_y_limpieza_de_documentos_inactivos(self):
        form = SolicitudFactibilidadForm(self.datos(propietario_tipo='JURIDICA', propietario_cuit='30-12345678-9',
            titular_tipo='JURIDICA', titular_cuit='30-98765432-1'), self.archivos())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['propietario_cuit'], '30123456789')
        self.assertEqual(form.cleaned_data['titular_cuit'], '30987654321')
        self.assertEqual(form.cleaned_data['propietario_dni'], '')
        self.assertEqual(form.cleaned_data['titular_dni'], '')

    def test_apoderado_exige_ambos_documentos_y_los_envia(self):
        form = SolicitudFactibilidadForm(self.datos(solicitante_condicion='APODERADO'), self.archivos())
        self.assertFalse(form.is_valid())
        self.assertIn('dni_apoderado', form.errors)
        self.assertIn('poder_apoderado', form.errors)
        response = self.client.post(reverse('tramite_nuevo'), {
            **self.datos(solicitante_condicion='APODERADO'), **self.archivos(apoderado=True)})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(len(mail.outbox[0].attachments), 4)
        self.assertIn('Actúa como: Apoderado', mail.outbox[0].body)

    def test_dni_y_cuit_condicionales_se_validan_en_servidor(self):
        for cambios, campo in [({'propietario_dni': ''}, 'propietario_dni'),
            ({'titular_tipo': 'JURIDICA', 'titular_cuit': ''}, 'titular_cuit'),
            ({'solicitante_dni': '123'}, 'solicitante_dni')]:
            form = SolicitudFactibilidadForm(self.datos(**cambios), self.archivos())
            self.assertFalse(form.is_valid())
            self.assertIn(campo, form.errors)

    def test_opciones_salta_y_equipamiento_no_admiten_valores_arbitrarios(self):
        self.assertEqual(len(DEPARTAMENTOS_SALTA), 23)
        for campo, valor in [('departamento', 'Otra provincia'), ('tecnologia', 'OTRA'),
            ('tipo_conexion', 'OTRA'), ('potencia_inyectada_kw', '-1'), ('coordenadas_pilar', 'https://maps.app.goo.gl/ejemplo')]:
            form = SolicitudFactibilidadForm(self.datos(**{campo: valor}), self.archivos())
            self.assertFalse(form.is_valid())
            self.assertIn(campo, form.errors)

    def test_html_de_usuario_se_escapa_en_correo_html(self):
        response = self.client.post(reverse('tramite_nuevo'), {
            **self.datos(propietario_nombre='<img src=x onerror=alert(1)>'), **self.archivos()})
        self.assertEqual(response.status_code, 303)
        html = mail.outbox[0].alternatives[0].content
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)

    def test_fallo_smtp_no_crea_registros_y_permite_corregir(self):
        with patch('apps.tramites.solicitud_email.EmailMultiAlternatives.send', side_effect=OSError('fallo de transporte')):
            response = self.client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se pudo enviar la solicitud a EDESA.')
        self.assertContains(response, 'value="Ana Propietaria"')
        self.assertEqual(Tramite.objects.count(), 0)
        self.assertEqual(Notificacion.objects.count(), 0)
        self.assertEqual(Auditoria.objects.count(), 0)

    @override_settings(EDESA_SOLICITUD_EMAIL='')
    def test_destinatario_sin_configurar_no_simula_envio_correcto(self):
        response = self.client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No se pudo enviar la solicitud')
        self.assertFalse(getattr(mail, 'outbox', []))

    def test_backends_que_guardan_contenido_estan_bloqueados(self):
        for backend in ['django.core.mail.backends.console.EmailBackend', 'django.core.mail.backends.filebased.EmailBackend']:
            with self.settings(EMAIL_BACKEND=backend):
                response = self.client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'No se pudo enviar la solicitud')

    @override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=1,
        FILE_UPLOAD_HANDLERS=['django.core.files.uploadhandler.TemporaryFileUploadHandler'])
    def test_adjuntos_no_pasan_por_archivos_temporales_ni_storage(self):
        with tempfile.TemporaryDirectory() as media, tempfile.TemporaryDirectory() as privado:
            with self.settings(MEDIA_ROOT=media, PRIVATE_MEDIA_ROOT=privado), \
                 patch('django.core.files.uploadhandler.TemporaryUploadedFile', side_effect=AssertionError('Escritura temporal prohibida')), \
                 patch('django.core.files.storage.FileSystemStorage.save', side_effect=AssertionError('Escritura persistente prohibida')):
                response = self.client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
            self.assertEqual(response.status_code, 303)
            self.assertIsInstance(response.wsgi_request.FILES['formulario_digital'], InMemoryUploadedFile)
            self.assertEqual(list(Path(media).rglob('*')), [])
            self.assertEqual(list(Path(privado).rglob('*')), [])

    def test_archivo_grande_se_rechaza_antes_del_envio(self):
        response = self.client.post(reverse('tramite_nuevo'), {
            **self.datos(), **self.archivos(), 'formulario_digital': self.pdf(size=5 * 1024 * 1024 + 1)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '5 MB')
        self.assertFalse(getattr(mail, 'outbox', []))
        self.assertEqual(DocumentoTramite.objects.count(), 0)

    def test_carga_total_demasiado_grande_se_rechaza_sin_guardarse(self):
        data = {**self.datos(solicitante_condicion='APODERADO')}
        data.update({name: self.pdf(size=4 * 1024 * 1024) for name in ['formulario_digital', 'dni_titular', 'dni_apoderado', 'poder_apoderado']})
        response = self.client.post(reverse('tramite_nuevo'), data)
        self.assertEqual(response.status_code, 413)
        self.assertContains(response, 'supera los límites', status_code=413)
        self.assertFalse(getattr(mail, 'outbox', []))

    def test_csrf_se_exige_antes_de_enviar_incluso_con_handler_personalizado(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(getattr(mail, 'outbox', []))
        client.get(reverse('tramite_nuevo'))
        response = client.post(reverse('tramite_nuevo'), {
            **self.datos(), **self.archivos(), 'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 303)

    def test_confirmacion_temporal_no_contiene_datos_y_recargar_no_reenvia(self):
        response = self.client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
        self.assertEqual(response.url, reverse('solicitud_enviada'))
        self.assertTrue(response.cookies['solicitud_enviada']['httponly'])
        success = self.client.get(response.url)
        self.assertEqual(success.wsgi_request.get_signed_cookie('solicitud_enviada', salt='solicitud-enviada'), str(Tramite.objects.get().pk))
        self.client.get(response.url)
        self.assertEqual(len(mail.outbox), 1)
        self.client.cookies['solicitud_enviada'] = 'invalido'
        self.assertRedirects(self.client.get(reverse('solicitud_enviada')), reverse('tramite_nuevo'))

    def test_consulta_publica_verifica_documento_protegido_y_sigue_circuito(self):
        from django.core.cache import cache
        cache.clear()
        self.client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
        t = Tramite.objects.get()
        datos = {'numero': t.numero, 'nis': t.nis, 'dni_cuit': '28.123.456'}
        response = self.client.post(reverse('tramite_consultar'), datos)
        self.assertEqual(response.context['resultado'], t)
        response = self.client.post(reverse('tramite_consultar'), {**datos, 'dni_cuit': '99999999'})
        self.assertTrue(response.context['no_encontrado'])
        self.assertIsNone(response.context['resultado'])
        self.assertEqual(DocumentoTramite.objects.count(), 0)

    def test_correo_al_solicitante_solo_contiene_datos_de_seguimiento(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('tramite_nuevo'), {**self.datos(), **self.archivos()})
        self.assertEqual(len(mail.outbox), 2)
        mensaje = mail.outbox[1]
        self.assertEqual(mensaje.to, ['solicitante@example.com'])
        self.assertIn(Tramite.objects.get().numero, mensaje.body)
        self.assertNotIn('Ana Propietaria', mensaje.body)
        self.assertEqual(mensaje.attachments, [])
        self.assertEqual(Notificacion.objects.get().estado, 'ENVIADA')
