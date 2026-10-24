import csv
import io
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from apps.auditoria.models import Auditoria
from apps.organismos.models import Organismo
from apps.tramites.models import Tramite
from apps.workflow.circuito import configurar_circuito
from apps.workflow.models import Etapa, TramiteEtapa
from .services import construir_reporte


class ReportesTests(TestCase):
    def setUp(self):
        configurar_circuito()
        self.base = timezone.make_aware(datetime(2026, 1, 1, 12))
        self.ahora = self.base + timedelta(days=60)
        self.edesa = Organismo.objects.get(sigla='EDESA')
        self.user = get_user_model().objects.create_user(username='consulta_reportes', organismo=self.edesa, rol='CONS')
        self.client.force_login(self.user)
        self.params = {'desde': '2026-01-01', 'hasta': '2026-01-31'}

    def instante(self, dias):
        return self.base + timedelta(days=dias)

    def tramite(self, **kwargs):
        return Tramite.objects.create(creado_en=self.base, nis='reporte', titular_nombre='Titular privado',
            titular_dni_cuit='123', titular_email='privado@example.com', **kwargs)

    def historial(self, tramite, codigo, inicio, fin=None):
        return TramiteEtapa.objects.create(tramite=tramite, etapa=Etapa.objects.get(codigo=codigo),
            fecha_inicio=self.instante(inicio) if inicio is not None else None,
            fecha_fin=self.instante(fin) if fin is not None else None,
            estado='FINALIZADO' if fin is not None else 'PENDIENTE')

    def evento(self, tramite, accion, dia, **detalle):
        evento = Auditoria.objects.create(tramite=tramite, accion=accion, detalle=detalle)
        Auditoria.objects.filter(pk=evento.pk).update(creado_en=self.instante(dia))

    def reporte(self, **kwargs):
        return construir_reporte(datetime(2026, 1, 1).date(), datetime(2026, 1, 31).date(), ahora=self.ahora, **kwargs)

    def fila(self, reporte, clave, grupo='organismos'):
        return next(f for f in reporte[grupo] if f['clave'] == clave)

    def test_promedios_ponderados_y_mediana_con_muestras_reales(self):
        uno = self.tramite(organismo_actual=Organismo.objects.get(sigla='COPAIPA'))
        dos = self.tramite()
        self.historial(uno, 'ingreso-factibilidad', 0, 1)
        self.historial(uno, 'respuesta-factibilidad', 1, 3)
        self.historial(uno, 'ingreso-copaipa', 3, 5)
        self.historial(uno, 'sellado-copaipa', 5, 9)
        self.historial(dos, 'ingreso-factibilidad', 2, 5)
        self.historial(dos, 'respuesta-factibilidad', 5, 9)
        reporte = self.reporte()
        edesa = self.fila(reporte, 'EDESA')
        self.assertEqual(edesa['recepcion']['promedio'], 2 * 86400)
        self.assertEqual(edesa['respuesta']['promedio'], 3 * 86400)
        self.assertEqual(edesa['recepcion']['mediana'], 2 * 86400)
        self.assertEqual(edesa['recepcion']['muestras'], 2)
        self.assertEqual(reporte['recepcion']['promedio'], 2 * 86400)
        self.assertAlmostEqual(reporte['respuesta']['promedio'], 10 / 3 * 86400)
        self.assertEqual(reporte['total'], 2)

    def test_proyecto_excluye_espera_del_cliente(self):
        t = self.tramite()
        self.historial(t, 'presentacion-proyecto-ejecutivo', 2, 13)
        self.historial(t, 'previsado-proyecto-ejecutivo', 13, 15)
        self.evento(t, 'PROYECTO_ENVIADO', 12)
        reporte = self.reporte()
        fila = self.fila(reporte, 'proyecto', 'instancias')
        self.assertEqual(fila['recepcion']['promedio'], 86400)
        self.assertEqual(fila['respuesta']['promedio'], 2 * 86400)

    def test_etapa_pendiente_del_cliente_no_es_gestion_de_edesa(self):
        t = self.tramite(etapa_actual=Etapa.objects.get(codigo='presentacion-proyecto-ejecutivo'),
            organismo_actual=self.edesa, estado_actual='PENDIENTE_CLIENTE')
        self.historial(t, 'presentacion-proyecto-ejecutivo', 1)
        reporte = self.reporte()
        self.assertEqual(reporte['total'], 1)
        self.assertEqual(self.fila(reporte, 'EDESA')['gestiones'], 0)
        self.assertEqual(reporte['pendientes_total'], 0)

    def test_recepcion_final_utiliza_evento_de_auditoria(self):
        t = self.tramite(estado_actual='FINALIZADO', conexion_realizada=self.instante(20))
        self.historial(t, 'firma-contrato', 3, 10)
        self.evento(t, 'RECIBIDO', 5, etapa='firma-contrato')
        fila = self.fila(self.reporte(), 'contrato', 'instancias')
        self.assertEqual(fila['recepcion']['promedio'], 2 * 86400)
        self.assertEqual(fila['respuesta']['promedio'], 5 * 86400)
        self.assertEqual(self.reporte()['ciclo']['promedio'], 20 * 86400)

    def test_fechas_faltantes_o_invertidas_no_se_convierten_en_cero(self):
        t = self.tramite()
        self.historial(t, 'firma-contrato', 3, 10)
        fila = self.fila(self.reporte(), 'contrato', 'instancias')
        self.assertIsNone(fila['recepcion']['promedio'])
        self.assertIsNone(fila['respuesta']['promedio'])
        self.assertEqual(fila['sin_datos'], 1)
        t2 = self.tramite()
        self.historial(t2, 'ingreso-factibilidad', 5, 3)
        self.historial(t2, 'respuesta-factibilidad', 3, 2)
        fila = self.fila(self.reporte(), 'factibilidad', 'instancias')
        self.assertEqual(fila['recepcion']['muestras'], 0)
        self.assertEqual(fila['respuesta']['muestras'], 0)

    def test_pendientes_solo_de_instancia_actual_y_ordenados_por_espera(self):
        pendiente = self.tramite(etapa_actual=Etapa.objects.get(codigo='ingreso-copaipa'),
            organismo_actual=Organismo.objects.get(sigla='COPAIPA'))
        self.historial(pendiente, 'ingreso-copaipa', 10)
        viejo = self.tramite(estado_actual='FINALIZADO', conexion_realizada=self.instante(20))
        self.historial(viejo, 'ingreso-factibilidad', 0)  # Fechas históricas incompletas, no una tarea activa.
        reporte = self.reporte()
        self.assertEqual(reporte['pendientes_total'], 1)
        self.assertEqual(reporte['pendientes'][0]['pk'], pendiente.pk)
        self.assertEqual(reporte['pendientes'][0]['espera'], 50 * 86400)

    def test_filtro_organismo_incluye_participacion_historica_sin_duplicar(self):
        t = self.tramite(organismo_actual=Organismo.objects.get(sigla='ENRESP'))
        self.historial(t, 'ingreso-copaipa', 3, 5)
        self.historial(t, 'sellado-copaipa', 5, 9)
        reporte = self.reporte(organismo=Organismo.objects.get(sigla='COPAIPA'))
        self.assertEqual(reporte['total'], 1)
        self.assertEqual(len(reporte['organismos']), 1)
        self.assertEqual(reporte['organismos'][0]['gestiones'], 1)

    def test_rango_inclusivo_en_hora_de_salta_y_bloques_vacios(self):
        desde = timezone.make_aware(datetime(2026, 1, 1))
        fin = timezone.make_aware(datetime(2026, 2, 1))
        t = self.tramite()
        Tramite.objects.filter(pk=t.pk).update(creado_en=desde)
        fuera = self.tramite()
        Tramite.objects.filter(pk=fuera.pk).update(creado_en=fin)
        reporte = self.reporte()
        self.assertEqual(reporte['total'], 1)
        self.assertEqual(sum(p['cantidad'] for p in reporte['periodos']), 1)
        self.assertEqual(len(reporte['periodos']), 31)
        self.assertEqual(reporte['periodos'][-1]['cantidad'], 0)

    def test_filtros_invalidos_no_generan_reportes_ni_exportaciones(self):
        for params in [{'desde': '2026-02-01', 'hasta': '2026-01-01'},
                       {**self.params, 'organismo': '999999'}, {'desde': 'mal', 'hasta': '2026-01-01'}]:
            self.assertEqual(self.client.get(reverse('institucional_reportes'), params).status_code, 400)
            self.assertEqual(self.client.get(reverse('institucional_reportes_exportar'), params).status_code, 400)

    def test_acceso_solo_institucional_incluye_rol_consulta(self):
        self.assertEqual(self.client.get(reverse('institucional_reportes')).status_code, 200)
        self.user.organismo = None
        self.user.save()
        self.assertEqual(self.client.get(reverse('institucional_reportes')).status_code, 403)
        self.assertEqual(self.client.get(reverse('institucional_reportes_exportar')).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('institucional_reportes')).status_code, 302)

    def test_csv_filtrado_utf8_seguro_y_sin_datos_personales(self):
        t = self.tramite()
        Organismo.objects.create(sigla='@org', nombre='=SUM(1)')
        response = self.client.get(reverse('institucional_reportes_exportar'), self.params)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        contenido = response.content.decode('utf-8-sig')
        self.assertNotIn(t.numero, contenido)
        self.assertNotIn(t.titular_email, contenido)
        self.assertNotIn(t.titular_nombre, contenido)
        filas = list(csv.reader(io.StringIO(contenido), delimiter=';'))
        peligrosa = next(f for f in filas if f and f[0] == "'@org")
        self.assertEqual(peligrosa[1], "'=SUM(1)")
        self.assertContains(self.client.get(reverse('institucional_reportes'), self.params), 'Reportes y estadísticas')

    def test_consultas_sql_no_crecen_por_cada_tramite(self):
        for _ in range(15):
            self.historial(self.tramite(), 'ingreso-factibilidad', 0, 1)
        with CaptureQueriesContext(connection) as queries:
            self.reporte()
        self.assertLessEqual(len(queries), 6)

    def test_reporte_vacio_no_presenta_promedios_inventados(self):
        reporte = self.reporte()
        self.assertEqual(reporte['total'], 0)
        self.assertIsNone(reporte['recepcion']['promedio'])
        response = self.client.get(reverse('institucional_reportes'), self.params)
        self.assertContains(response, 'No hay trámites en este período')
        self.assertContains(response, '0 gestiones con llegada y recepción')

    def test_tres_instancias_edesa_no_duplican_tramites_unicos(self):
        t = self.tramite(estado_actual='FINALIZADO', conexion_realizada=self.instante(30))
        self.historial(t, 'ingreso-factibilidad', 0, 1)
        self.historial(t, 'respuesta-factibilidad', 1, 3)
        self.historial(t, 'presentacion-proyecto-ejecutivo', 3, 10)
        self.evento(t, 'PROYECTO_ENVIADO', 9)
        self.historial(t, 'previsado-proyecto-ejecutivo', 10, 12)
        self.historial(t, 'firma-contrato', 20, 25)
        self.evento(t, 'RECIBIDO', 21, etapa='firma-contrato')
        fila = self.fila(self.reporte(), 'EDESA')
        self.assertEqual(fila['gestiones'], 3)
        self.assertEqual(fila['unicos'], 1)
        self.assertEqual(fila['recepcion']['muestras'], 3)
        self.assertEqual(fila['respuesta']['muestras'], 3)

    def test_fechas_futuras_y_cierres_ausentes_no_entran_en_promedios(self):
        t = self.tramite(estado_actual='FINALIZADO')
        self.historial(t, 'ingreso-factibilidad', 0, 100)
        self.historial(t, 'respuesta-factibilidad', 100, 110)
        reporte = self.reporte()
        self.assertEqual(reporte['finalizados'], 1)
        self.assertEqual(reporte['sin_fecha_cierre'], 1)
        self.assertIsNone(reporte['ciclo']['promedio'])
        self.assertEqual(reporte['recepcion']['muestras'], 0)
        self.assertEqual(reporte['respuesta']['muestras'], 0)
        self.assertEqual(reporte['pendientes_total'], 0)

    def test_exportacion_respeta_organismo_y_contiene_todos_los_resumenes(self):
        t = self.tramite()
        self.historial(t, 'ingreso-factibilidad', 0, 1)
        response = self.client.get(reverse('institucional_reportes_exportar'), {**self.params, 'organismo': self.edesa.pk})
        contenido = response.content.decode('utf-8-sig')
        self.assertIn('Ciclo completo', contenido)
        self.assertIn('Altas desde', contenido)
        self.assertIn('Estado actual', contenido)
        self.assertIn('Organismo seleccionado;EDESA', contenido)
        self.assertNotIn('COPAIPA', contenido)
        self.assertNotIn('ENRESP', contenido)

    def test_recepcion_sin_fecha_en_etapa_de_respuesta_informa_calidad(self):
        t = self.tramite(etapa_actual=Etapa.objects.get(codigo='respuesta-factibilidad'), organismo_actual=self.edesa)
        self.historial(t, 'ingreso-factibilidad', 0)
        self.historial(t, 'respuesta-factibilidad', 2)
        reporte = self.reporte()
        self.assertEqual(reporte['sin_datos'], 1)
        self.assertEqual(reporte['recepcion']['muestras'], 0)
        self.assertEqual(reporte['pendientes_total'], 0)
