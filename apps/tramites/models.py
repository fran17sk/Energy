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
    numero = models.CharField(max_length=64, unique=True, editable=False)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(auto_now=True)
    presentacion_por_correo = models.BooleanField(default=False)
    consulta_documento_hash = models.CharField(max_length=128, blank=True, editable=False)

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
        indexes = [
            models.Index(fields=['nis']),
            models.Index(fields=['titular_dni_cuit']),
            models.Index(fields=['organismo_actual', 'estado_actual']),
        ]

    @property
    def titular_display(self):
        return self.titular_nombre or f'Suministro NIS {self.nis}'

    def verificar_documento_consulta(self, documento):
        if self.consulta_documento_hash:
            normalizado = re.sub(r'[.\s-]', '', documento)
            return check_password(normalizado, self.consulta_documento_hash)
        return constant_time_compare(self.titular_dni_cuit, documento)

    def __str__(self):
        return self.numero

    def save(self, *args, **kwargs):
        if not self.numero:
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
