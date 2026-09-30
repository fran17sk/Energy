from django.contrib.auth.models import AbstractUser
from django.db import models

class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        ADMINISTRADOR = 'ADMIN', 'Administrador'
        RESPONSABLE = 'RESP', 'Responsable de organismo'
        OPERADOR = 'OPER', 'Operador'
        CONSULTA = 'CONS', 'Consulta'

    organismo = models.ForeignKey('organismos.Organismo', on_delete=models.PROTECT, null=True, blank=True, related_name='usuarios')
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.CONSULTA)

    def __str__(self):
        return self.get_full_name() or self.username
