from pathlib import Path
from django import forms
from django.core.exceptions import ValidationError

class ConsultaTramiteForm(forms.Form):
    numero = forms.CharField(max_length=64, label='Número de trámite')
    nis = forms.CharField(max_length=40, label='NIS')
    dni_cuit = forms.CharField(max_length=30, label='DNI / CUIT')


def validar_documento(archivo):
    if archivo.size > 10 * 1024 * 1024:
        raise ValidationError('El archivo no puede superar los 10 MB.')
    extension = Path(archivo.name).suffix.lower()
    cabecera = archivo.read(8)
    archivo.seek(0)
    valido = (
        (extension == '.pdf' and cabecera.startswith(b'%PDF-')) or
        (extension in {'.jpg', '.jpeg'} and cabecera.startswith(b'\xff\xd8\xff')) or
        (extension == '.png' and cabecera.startswith(b'\x89PNG\r\n\x1a\n'))
    )
    if not valido:
        raise ValidationError('Adjuntá un PDF, JPG o PNG válido.')


class DocumentoForm(forms.Form):
    archivo = forms.FileField(label='Documento', validators=[validar_documento],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}))


class AccionTramiteForm(forms.Form):
    accion = forms.ChoiceField(choices=[])
    etapa = forms.CharField(widget=forms.HiddenInput)
    archivo = forms.FileField(required=False, label='Documento', validators=[validar_documento],
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png'}))
    recorrido = forms.ChoiceField(label='Recorrido definido por la factibilidad', required=False, choices=[('', 'Seleccioná el recorrido'), ('GGER', 'Sólo proyecto GGER · sin obra de nexo'), ('CON_NEXO', 'Proyecto GGER + proyecto de obra de nexo')])
    expediente = forms.CharField(max_length=100, required=False, label='Número de expediente administrativo')
    fecha = forms.DateTimeField(required=False, label='Fecha y hora',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'step': '1'}))
    observacion = forms.CharField(max_length=2000, required=False, label='Detalle / indicaciones',
        widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, acciones=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['accion'].choices = acciones
        self.fields['accion'].label = 'Actuación'
        codigos = {codigo for codigo, _ in acciones}
        if len(acciones) == 1:
            self.fields['accion'].widget = forms.HiddenInput()
            self.fields['accion'].initial = acciones[0][0]
        if not codigos.intersection({'respuesta', 'copaipa', 'dictamen', 'resolucion', 'contrato'}):
            self.fields.pop('archivo')
        if 'respuesta' not in codigos:
            self.fields.pop('recorrido')
        else:
            self.fields['recorrido'].required = True
            self.fields['recorrido'].help_text = 'Los proyectos se presentan y tramitan por separado. La conexión del GGER queda bloqueada hasta finalizar el nexo.'
        if 'expediente' not in codigos:
            self.fields.pop('expediente')
        if not codigos.intersection({'programar', 'inspeccionar', 'conectar'}):
            self.fields.pop('fecha')

        required_messages = {
            'archivo': 'Esta actuación requiere un documento.',
            'expediente': 'Ingresá el número de expediente.',
            'fecha': 'Ingresá la fecha y hora de la actuación.',
        }
        for name, message in required_messages.items():
            if name in self.fields:
                self.fields[name].required = True
                self.fields[name].error_messages['required'] = message
        if 'convocar' in codigos:
            self.fields['observacion'].required = True
            self.fields['observacion'].error_messages['required'] = 'Indicá la oficina y las instrucciones para firmar el contrato.'
        if codigos == {'recibir'}:
            self.fields.pop('observacion')
