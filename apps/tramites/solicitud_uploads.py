"""Recepción de adjuntos exclusivamente en RAM; nunca utiliza archivos temporales."""
from io import BytesIO
from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from .solicitud_forms import MAX_ARCHIVO, MAX_ADJUNTOS

MAX_SOLICITUD_BYTES = 16 * 1024 * 1024


class SolicitudMemoryUploadHandler(FileUploadHandler):
    def __init__(self, request):
        super().__init__(request)
        self.total = 0

    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        if content_length is not None and content_length > MAX_SOLICITUD_BYTES:
            raise RequestDataTooBig('La solicitud supera el tamaño permitido.')

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.file = BytesIO()
        self.size = 0

    def receive_data_chunk(self, raw_data, start):
        self.size += len(raw_data)
        self.total += len(raw_data)
        if self.size > MAX_ARCHIVO or self.total > MAX_ADJUNTOS:
            self.request.solicitud_upload_error = 'Cada archivo puede pesar hasta 5 MB y los adjuntos hasta 15 MB en total.'
            self.file.close()
            raise StopUpload(connection_reset=True)
        self.file.write(raw_data)
        return None

    def file_complete(self, file_size):
        self.file.seek(0)
        return InMemoryUploadedFile(self.file, self.field_name, self.file_name, self.content_type,
            file_size, self.charset, self.content_type_extra)
