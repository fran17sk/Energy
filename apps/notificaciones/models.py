from django.db import models

class Notificacion(models.Model):
    class Canal(models.TextChoices):
        INTERNA = 'INTERNA', 'Interna'
        EMAIL = 'EMAIL', 'Correo electrónico'

    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        ENVIADA = 'ENVIADA', 'Enviada'
        ERROR = 'ERROR', 'Error'

    tramite = models.ForeignKey('tramites.Tramite', on_delete=models.CASCADE, related_name='notificaciones')
    organismo = models.ForeignKey('organismos.Organismo', on_delete=models.CASCADE, null=True, blank=True)
    usuario = models.ForeignKey('accounts.Usuario', on_delete=models.CASCADE, null=True, blank=True)
    canal = models.CharField(max_length=10, choices=Canal.choices)
    asunto = models.CharField(max_length=200)
    mensaje = models.TextField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    creado_en = models.DateTimeField(auto_now_add=True)
    enviado_en = models.DateTimeField(null=True, blank=True)

    destinatario = models.EmailField(blank=True)
    evento = models.CharField(max_length=40, blank=True)
    documento = models.ForeignKey('tramites.DocumentoTramite', null=True, blank=True, on_delete=models.PROTECT)
    intentos = models.PositiveIntegerField(default=0)
