from django.contrib.auth.forms import AuthenticationForm


class AccesoInstitucionalForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'login-input', 'placeholder': 'Ingresá tu usuario',
            'autocomplete': 'username', 'autocapitalize': 'none',
            'spellcheck': 'false', 'aria-describedby': 'username-errors',
        })
        self.fields['password'].widget.attrs.update({
            'class': 'login-input', 'placeholder': 'Ingresá tu contraseña',
            'autocomplete': 'current-password', 'aria-describedby': 'password-errors',
        })
