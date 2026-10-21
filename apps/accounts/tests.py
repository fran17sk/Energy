from django.contrib.auth import get_user_model
from django.test import TestCase


class AccesoInstitucionalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = 'institutional-test-password'
        cls.user = get_user_model().objects.create_user(username='operador', password=cls.password)

    def test_login_redirige_al_destino_solicitado(self):
        response = self.client.post('/acceso/', {
            'username': self.user.username, 'password': self.password,
            'next': '/institucional/tramites/',
        })
        self.assertRedirects(response, '/institucional/tramites/', fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_login_rechaza_redireccion_a_otro_sitio(self):
        response = self.client.post('/acceso/', {
            'username': self.user.username, 'password': self.password,
            'next': 'https://example.com/',
        })
        self.assertRedirects(response, '/institucional/', fetch_redirect_response=False)

    def test_credenciales_invalidas_muestran_error_sin_iniciar_sesion(self):
        response = self.client.post('/acceso/', {'username': 'operador', 'password': 'incorrecta'})
        self.assertContains(response, 'No pudimos iniciar sesión.')
        self.assertContains(response, 'value="operador"')
        self.assertNotContains(response, 'value="incorrecta"')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_usuario_inactivo_no_puede_ingresar(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post('/acceso/', {'username': 'operador', 'password': self.password})
        self.assertContains(response, 'No pudimos iniciar sesión.')
        self.assertNotIn('_auth_user_id', self.client.session)
