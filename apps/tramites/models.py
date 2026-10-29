from django.db import models
from django.utils import timezone
import secrets
import uuid
import os
import re
from django.contrib.auth.hashers import check_password
from django.utils.crypto import constant_time_compare
from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)


def private_storage():
    return PrivateStorage()


class Tramite(models.Model):
    numero = models.CharField(max_length=64, editable=False)
    requiere_nexo = models.BooleanField(default=False)
    tramite_gger = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='obra_nexo', editable=False)

    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)
    presentacion_por_correo = models.BooleanField(default=False)
    consulta_documento_hash = models.CharField(max_length=128, blank=True, editable=False)

    # Datos declarados en la solicitud; los adjuntos iniciales no se persisten.
    propietario_tipo = models.CharField(max_length=10, blank=True)
    propietario_nombre = models.CharField(max_length=180, blank=True)
    propietario_dni = models.CharField(max_length=15, blank=True)
    propietario_cuit = models.CharField(max_length=15, blank=True)
    titular_tipo = models.CharField(max_length=10, blank=True)
    solicitante_condicion = models.CharField(max_length=10, blank=True)
    solicitante_nombre = models.CharField(max_length=180, blank=True)
    solicitante_dni = models.CharField(max_length=15, blank=True)
    solicitante_celular = models.CharField(max_length=30, blank=True)

    # Datos del suministro
    nis = models.CharField(max_length=40, db_index=True)
    catastro = models.CharField(max_length=80, blank=True)
    departamento = models.CharField(max_length=100, blank=True)
    potencia_contratada_kw = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    # Titular
    titular_nombre = models.CharField(max_length=180)
    titular_dni_cuit = models.CharField(max_length=30)
    titular_email = models.EmailField()
    titular_telefono = models.CharField(max_length=50, blank=True)

    # GGER
    tecnologia = models.CharField(max_length=30, blank=True)
    tipo_conexion = models.CharField(max_length=30, blank=True)
    modalidad_conexion = models.CharField(max_length=120, blank=True)
    potencia_inyectada_kw = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    coordenadas_pilar = models.CharField(max_length=180, blank=True)

    solicitud_factibilidad = models.FileField(upload_to='solicitudes/%Y/%m/%d/', storage=private_storage, blank=True, null=True)

    etapa_actual = models.ForeignKey('workflow.Etapa', on_delete=models.PROTECT, null=True, blank=True, related_name='tramites_actuales')
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        RECIBIDO = 'RECIBIDO', 'Recibido'
        OBSERVADO = 'OBSERVADO', 'Observado · pendiente de corrección del solicitante'
        SUBSANADO = 'SUBSANADO', 'Subsanación enviada · requiere atención de EDESA'
        PENDIENTE_ENVIO = 'PENDIENTE_ENVIO', 'Pendiente de envío de correo'
        PENDIENTE_CLIENTE = 'PENDIENTE_CLIENTE', 'Pendiente de envío por parte del cliente'
        PROYECTO_ENVIADO = 'PROYECTO_ENVIADO', 'Proyecto enviado · requiere atención de EDESA'
        EXPEDIENTE_ASOCIADO = 'EXPEDIENTE_ASOCIADO', 'Número de expediente administrativo asociado'
        CONVOCADO = 'CONVOCADO', 'Notificación de firma enviada'
        PROGRAMADA = 'PROGRAMADA', 'Inspección programada'
        FINALIZADO = 'FINALIZADO', 'Finalizado · conexión registrada'

    estado_actual = models.CharField(max_length=30, choices=Estado.choices, default=Estado.PENDIENTE)
    expediente_administrativo = models.CharField(max_length=100, blank=True)
    inspeccion_programada = models.DateTimeField(null=True, blank=True)
    inspeccion_realizada = models.DateTimeField(null=True, blank=True)
    conexion_realizada = models.DateTimeField(null=True, blank=True)
    organismo_actual = models.ForeignKey('organismos.Organismo', on_delete=models.PROTECT, null=True, blank=True, related_name='tramites_actuales')

    class Meta:
        ordering = ['-creado_en']
        constraints = [
            models.UniqueConstraint(fields=['numero'], condition=models.Q(tramite_gger__isnull=True),
                name='numero_unico_expediente_gger'),
            models.CheckConstraint(condition=~models.Q(pk=models.F('tramite_gger_id')),
                name='nexo_no_es_su_propio_gger'),
            models.CheckConstraint(condition=models.Q(tramite_gger__isnull=True) | models.Q(requiere_nexo=False),
                name='nexo_no_requiere_otro_nexo'),
        ]
        indexes = [
            models.Index(fields=['nis']),
            models.Index(fields=['titular_dni_cuit']),
            models.Index(fields=['organismo_actual', 'estado_actual']),
        ]

    @property
    def es_nexo(self):
        return self.tramite_gger_id is not None

    @property
    def circuito_display(self):
        return 'Obra de nexo' if self.es_nexo else 'GGER'

    def nombre_etapa(self, etapa):
        if not etapa:
            return 'Sin etapa asignada'
        nombres_nexo = {
            'presentacion-proyecto-ejecutivo': 'Presentación del proyecto de obra de nexo',
            'previsado-proyecto-ejecutivo': 'Previsado del proyecto de obra de nexo',
            'firma-contrato': 'Contrato de obra de nexo · recepción final en EDESA',
            'inspeccion': 'Inspección de obra de nexo',
            'conexion-red': 'Finalización de la obra de nexo',
        }
        return nombres_nexo.get(etapa.codigo, etapa.nombre) if self.es_nexo else etapa.nombre

    @property
    def etapa_display(self):
        return self.nombre_etapa(self.etapa_actual)

    @property
    def codigo_consulta(self):
        return self.tramite_gger.numero if self.es_nexo else self.numero

    @property
    def nexo_asociado(self):
        try:
            return self.obra_nexo
        except Tramite.DoesNotExist:
            return None

    @property
    def conexion_bloqueada(self):
        if self.es_nexo or not self.requiere_nexo:
            return False
        nexo = self.nexo_asociado
        return not (nexo and nexo.estado_actual == self.Estado.FINALIZADO and nexo.conexion_realizada)

    @property
    def estado_display(self):
        if self.es_nexo and self.estado_actual == self.Estado.FINALIZADO:
            return 'Finalizado · obra de nexo registrada'
        return self.get_estado_actual_display()

    @property
    def titular_display(self):
        return self.titular_nombre or f'Suministro NIS {self.nis}'

    @property
    def secciones_presentacion(self):
        if not self.solicitante_nombre:
            return []  # Las presentaciones históricas mínimas no pueden reconstruirse.
        from .solicitud_email import secciones_solicitud
        datos = {campo: getattr(self, campo) for campo in (
            'propietario_tipo', 'propietario_nombre', 'propietario_dni', 'propietario_cuit',
            'titular_tipo', 'titular_nombre', 'nis', 'potencia_contratada_kw', 'catastro',
            'departamento', 'tecnologia', 'tipo_conexion', 'potencia_inyectada_kw',
            'coordenadas_pilar', 'solicitante_condicion', 'solicitante_nombre',
            'solicitante_dni', 'solicitante_celular')}
        datos.update(titular_dni=self.titular_dni_cuit if self.titular_tipo == 'HUMANA' else '',
                     titular_cuit=self.titular_dni_cuit if self.titular_tipo == 'JURIDICA' else '',
                     solicitante_email=self.titular_email)
        return secciones_solicitud(datos)

    def verificar_documento_consulta(self, documento):
        if self.consulta_documento_hash:
            normalizado = re.sub(r'[.\s-]', '', documento)
            return check_password(normalizado, self.consulta_documento_hash)
        return constant_time_compare(self.titular_dni_cuit, documento)

    def __str__(self):
        return f'{self.numero} · Obra de nexo' if self.es_nexo else self.numero

    def save(self, *args, **kwargs):
        if self.tramite_gger_id:
            self.numero = self.tramite_gger.numero
        elif not self.numero:
            self.numero = 'GGER-' + secrets.token_hex(24).upper()
        super().save(*args, **kwargs)


def documento_path(instance, filename):
    # Los nombres originales y los códigos de acceso nunca se usan como rutas públicas.
    extension = filename.rsplit('.', 1)[-1].lower()
    return f'privados/{uuid.uuid4().hex}.{extension}'


class DocumentoTramite(models.Model):
    class Tipo(models.TextChoices):
        SOLICITUD = 'SOLICITUD', 'Solicitud de factibilidad'
        RESPUESTA = 'RESPUESTA', 'Respuesta de factibilidad'
        PROYECTO = 'PROYECTO', 'Proyecto ejecutivo'
        COPAIPA = 'COPAIPA', 'Dictamen de COPAIPA'
        SECRETARIA = 'SECRETARIA', 'Dictamen de la Secretaría de Minería y Energía'
        RESOLUCION = 'RESOLUCION', 'Resolución del ente regulador'
        CONTRATO = 'CONTRATO', 'Contrato firmado'

    tramite = models.ForeignKey(Tramite, on_delete=models.CASCADE, related_name='documentos')
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    archivo = models.FileField(upload_to=documento_path, storage=private_storage)
    creado_en = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey('accounts.Usuario', null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ['creado_en']
        constraints = [models.UniqueConstraint(fields=['tramite', 'tipo'], name='documento_unico_por_tipo')]


class ObservacionSolicitud(models.Model):
    tramite = models.ForeignKey(Tramite, on_delete=models.CASCADE, related_name='observaciones_solicitud')
    usuario = models.ForeignKey('accounts.Usuario', on_delete=models.PROTECT)
    detalle = models.TextField(max_length=2000)
    creada_en = models.DateTimeField(auto_now_add=True)
    subsanada_en = models.DateTimeField(null=True, blank=True)
    recibida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-creada_en', '-pk']
        constraints = [models.UniqueConstraint(fields=['tramite'], condition=models.Q(subsanada_en__isnull=True), name='una_observacion_solicitud_abierta')]
