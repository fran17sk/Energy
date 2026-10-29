from datetime import timedelta
from django import forms
from django.utils import timezone
from apps.organismos.models import Organismo


class FiltrosReportesForm(forms.Form):
    circuito = forms.ChoiceField(label='Circuito', required=False, choices=[('GGER', 'GGER'), ('NEXO', 'Obra de nexo')], initial='GGER')
    desde = forms.DateField(label='Desde', widget=forms.DateInput(attrs={'type': 'date'}))
    hasta = forms.DateField(label='Hasta', widget=forms.DateInput(attrs={'type': 'date'}))
    organismo = forms.ModelChoiceField(label='Organismo', queryset=Organismo.objects.all(),
        required=False, empty_label='Todos los organismos')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['organismo'].label_from_instance = lambda org: org.sigla

    @classmethod
    def datos_iniciales(cls):
        hoy = timezone.localdate()
        return {'circuito': 'GGER', 'desde': (hoy - timedelta(days=89)).isoformat(), 'hasta': hoy.isoformat()}

    def clean(self):
        data = super().clean()
        desde, hasta = data.get('desde'), data.get('hasta')
        if desde and hasta:
            if desde > hasta:
                self.add_error('hasta', 'La fecha final debe ser igual o posterior a la inicial.')
            elif (hasta - desde).days > 3660:
                self.add_error('hasta', 'Seleccioná un período de hasta diez años.')
        return data
