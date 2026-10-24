# Circuito de Generación Distribuida

## Operación

El cliente registra la **solicitud de factibilidad**, con PDF/JPG/PNG obligatorio (hasta 10 MB). El sistema genera un código aleatorio de 192 bits, registra la solicitud en EDESA y envía el código al correo del titular. Debe guardarse y tratarse como una credencial. Los códigos antiguos se conservan para no interrumpir expedientes existentes.

| Etapa | Responsable | Recepción y condición de avance |
| --- | --- | --- |
| Solicitud de factibilidad | EDESA | Al abrirla un gestor de EDESA, se registra recibido con usuario/organismo/fecha/hora y se abre Respuesta de factibilidad pendiente. |
| Respuesta de factibilidad | EDESA | Requiere archivo. Se envía al correo del titular como adjunto. Si SMTP falla, queda pendiente de envío y no habilita el proyecto. |
| Presentación de Proyecto Ejecutivo | Cliente / EDESA | Después del envío de la respuesta queda pendiente del cliente. El cliente verifica código, NIS y DNI/CUIT y adjunta el proyecto. Queda Proyecto enviado y aparece como tarea de EDESA. Al abrir EDESA se registra recibido. |
| Previsado | EDESA | Marca previsado y remite a COPAIPA. |
| Recepción y visado | COPAIPA | Al abrir se registra recibido. Adjunta dictamen de aprobación y el trámite queda visado y se remite a la Secretaría. |
| Recepción y expediente | Secretaría de Minería y Energía | Al abrir se registra recibido. Primero debe asociar el número de expediente administrativo. |
| Dictamen | Secretaría de Minería y Energía | Con expediente asociado, adjunta dictamen. La sección queda aprobada y se remite a ENRESP. |
| Recepción y resolución | ENRESP | Al abrir se registra recibido. Adjunta resolución, queda aprobado por el ente y vuelve a EDESA. |
| Recepción final y contrato | EDESA | Se registra una recepción distinta de las anteriores. Envía al cliente una convocatoria con oficina e instrucciones para firmar. Sólo tras el envío del correo permite adjuntar el contrato firmado. |
| Inspección | EDESA | Con contrato adjunto, programa fecha/hora futura; luego registra la inspección efectivamente realizada. |
| Conexión | EDESA | Registra fecha/hora de conexión, posterior a la inspección. El trámite queda finalizado y visible para todas las partes. |

Las recepciones ocurren sólo al abrir el **detalle** con un gestor del organismo responsable; listar, buscar o abrir desde otro organismo no acusa recepción. Cada apertura institucional queda registrada además como `CONSULTA_EXPEDIENTE`. Los roles `OPER`, `RESP` y `ADMIN`, con organismo asignado, pueden actuar sólo en etapas de su organismo. El rol `CONS` es de lectura. Un superusuario sin organismo tampoco actúa en nombre de EDESA u otro organismo: debe tener organismo y rol de gestión para hacerlo.

Todos los organismos pueden ver todos los estados, documentos y el registro cronológico. El administrador de Django puede consultar estos registros pero no editar estados, borrar el historial ni saltar transiciones desde el admin. La administración de usuarios y organismos permite asignar los accesos correspondientes.

## Seguimiento del cliente y archivos

La consulta usa código + NIS + DNI/CUIT mediante POST. Al validar se concede acceso al expediente por 30 minutos en la sesión. No se incluyen los datos de acceso en URLs. Un intento de consulta inválido revoca el acceso anterior. Los documentos se descargan como adjuntos mediante vistas autorizadas, nunca desde URLs estáticas. Sólo se permite presentar un proyecto en el estado correspondiente y se rechazan duplicados.

Las solicitudes y documentos nuevos se guardan en `PRIVATE_MEDIA_ROOT` (por defecto `private_uploads/`). Esta carpeta y el directorio `media/` anterior **no deben publicarse con Nginx, CDN ni ningún servidor estático**. La aplicación ya no publica `/media/`. `STATIC_ROOT` sigue siendo exclusivo de CSS/JS y recursos públicos. Los archivos tienen permisos 0600 y los directorios nuevos 0700.

Las cargas admiten PDF, JPG o PNG; se comprueban extensión, firma inicial y tamaño máximo. El límite del servidor/proxy debe permitir una carga de 10 MB más el formulario. La consulta incluye un límite de 15 intentos por minuto por IP en la caché de Django. En producción con varios workers debe complementarse con un límite compartido en el proxy o una caché compartida; no confiar en cabeceras de IP sin un proxy confiable.

## Registro y consistencia

Cada recepción, documento institucional, expediente, convocatoria, inspección y conexión deja un evento de auditoría con usuario, organismo y fecha/hora. Las presentaciones públicas registran la identidad del titular que verificó sus datos; no crean una cuenta institucional. La auditoría conserva además el nombre de usuario y sigla del organismo al momento del evento, aunque luego cambie la cuenta. Se guardan fechas conscientes de zona horaria y se muestran en hora local de Salta, con segundos en el registro de eventos. La fecha informada de inspección/conexión es independiente del instante en que el usuario la registra.

Las transiciones usan transacciones y bloqueo de fila en PostgreSQL. Un formulario viejo no permite repetir o saltar una actuación. Las etapas antiguas de salida se mantienen para preservar historial y quedan fuera del circuito activo. No se inventan documentos ni aprobaciones de expedientes anteriores.

## Correo

Configurar en el entorno de despliegue (valores secretos fuera de Git):

- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`.
- `EMAIL_USE_TLS=True` cuando corresponda al servidor SMTP.
- `DEFAULT_FROM_EMAIL` con un remitente autorizado por el proveedor.
- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` (valor predeterminado).

Los mensajes de alta incluyen el código. La respuesta de factibilidad se adjunta al correo y también queda disponible en el expediente. La convocatoria al contrato incluye las instrucciones ingresadas por EDESA. Se notifica también la inspección programada y la finalización.

Cada envío se conserva en `Notificacion`: destinatario, evento, documento, usuario emisor, estado, intentos y fecha/hora de aceptación. El correo se intenta después de confirmar la transacción. Si el servidor no lo acepta, se registra `ERROR` sin perder la actuación ni el documento. El organismo actual puede reintentar desde el expediente. Para reintentos periódicos configurar un cron/timer con:

```bash
cd /ruta/Energy
.venv/bin/python manage.py reenviar_notificaciones
```

El comando omite correos ya enviados. `ENVIADA` significa aceptación por el backend SMTP, no recepción ni lectura por el cliente. Un corte de proceso después de la aceptación SMTP y antes de confirmar la base puede causar un reenvío; el cliente puede usar el mismo código/documento. El backend en memoria se usa exclusivamente en pruebas; SMTP real requiere credenciales y validación del despliegue.

## Actualización

Respaldar la base y los archivos existentes antes del despliegue, y detener los procesos que ejecuten versiones anteriores mientras se aplican las migraciones.

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check
python manage.py test --noinput
```

La migración configura los organismos y las etapas operativas, conserva los códigos antiguos y copia las solicitudes anteriores desde `MEDIA_ROOT` a `PRIVATE_MEDIA_ROOT`. Si falta un archivo previo, detiene la migración indicando el ID del trámite para restaurarlo desde el respaldo. No elimina los originales; deben quedar fuera de cualquier publicación de archivos. Algunas etapas antiguas redundantes se trasladan a la recepción del organismo siguiente, dejando evento de migración. Los expedientes sin etapa se asignan al ingreso de EDESA; no se envían correos históricos durante la migración.

Después de desplegar, verificar un correo real con un destinatario de prueba autorizado y el remitente configurado. Asignar a cada usuario institucional su organismo y rol. Para comprobar el circuito local sin enviar correos externos, usar temporalmente `EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend` sólo en un entorno de prueba.
