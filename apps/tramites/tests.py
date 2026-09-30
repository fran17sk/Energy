from django.test import TestCase
from apps.tramites.models import Tramite

class TramiteModelTests(TestCase):
    def test_generates_unique_number(self):
        t = Tramite.objects.create(nis='123', titular_nombre='Juan Pérez', titular_dni_cuit='20123456789', titular_email='juan@example.com')
        self.assertTrue(t.numero.startswith('GGER-'))
