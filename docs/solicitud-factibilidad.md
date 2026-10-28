# Solicitud de factibilidad y almacenamiento de datos

## Formulario

La presentación pública tiene seis secciones:

1. Propietario del inmueble: tipo de persona, nombre/razón social y DNI para persona humana o CUIT para jurídica.
2. Titular del suministro: los mismos datos, independientes de los del propietario.
3. Suministro: NIS, potencia contratada con EDESA (kW), catastro y uno de los 23 departamentos de Salta.
4. Equipamiento: sistema fotovoltaico, eólico, biomasa o hidráulico; conexión monofásica 220 V, trifásica 380 V, media tensión 13,2 kV o 33 kV; potencia efectiva a plena carga inyectada en corriente alterna; coordenadas del pilar de medición.
5. Solicitante: titular o apoderado, nombre, DNI, celular y correo para notificaciones. Este correo es el destino de las comunicaciones posteriores, aunque sea distinto del titular.
6. Adjuntos: formulario digital y DNI del titular (o de su representante, si es persona jurídica); al intervenir un apoderado se exigen además su DNI y el poder correspondiente.

El formulario valida los campos condicionales tanto en el navegador como en el servidor. El DNI admite 7 u 8 dígitos y el CUIT 11, normalizando separadores; esto es validación de formato, no acreditación de identidad. Las coordenadas deben tener formato `latitud, longitud`, con punto decimal y valores válidos. Las potencias son positivas.

Se aceptan PDF, JPG y PNG con firma inicial acorde a su extensión. El límite es de 5 MB por archivo y 15 MB entre todos los adjuntos. No hay borradores ni guardado de los campos en localStorage.

## Dirección receptora configurable

En el `.env` de la instalación, junto a `manage.py`:

```dotenv
EDESA_SOLICITUD_EMAIL=correo-designado-por-edesa@example.com
```

Reemplazar el ejemplo por la dirección autorizada. La dirección se valida y no se infiere de `EMAIL_HOST_USER`. También deben estar configuradas las variables SMTP de `.env.example`. Reiniciar los procesos después de cambiar el entorno.

Para Gmail, el transporte habitual usa puerto 587 y `EMAIL_USE_TLS=True`; la contraseña de aplicación se configura de forma privada en `EMAIL_HOST_PASSWORD`, fuera de Git. El envío se hace desde `DEFAULT_FROM_EMAIL`, al destino de EDESA, con `Reply-To` al solicitante. El correo lleva la presentación completa en texto y HTML, el código de referencia y todos los adjuntos aplicables con nombres seguros.

Si el destino no está configurado, SMTP falla o el backend no acepta el mensaje, no se muestra una confirmación de envío ni se conserva un registro incompleto. Los backends de consola y archivo están bloqueados para esta presentación porque volcarían su contenido a logs o disco. El backend en memoria se admite para pruebas y no entrega correos reales.

## Qué se guarda y qué no

Se guardan todos los datos validados del formulario: propietario (tipo de persona, nombre, DNI o CUIT), titular (tipo, nombre y DNI/CUIT), NIS, catastro, departamento, potencia contratada, tecnología, conexión, potencia inyectada, coordenadas y solicitante (condición, nombre, DNI, celular y correo). El correo para notificaciones continúa en `titular_email`, por compatibilidad, y corresponde al solicitante. El documento del titular también mantiene un hash para validar la consulta pública.

Se conservan además el código, estado, organismo, fechas, historial y auditoría. Las vistas institucionales muestran los datos completos en una sección de la presentación; la auditoría identifica al solicitante declarado.

**No se guardan los adjuntos iniciales**: formulario digital, DNI del titular y, cuando corresponda, DNI y poder del apoderado. Se envían por correo a EDESA. No se crean archivos ni filas iniciales en `DocumentoTramite`.

El formulario es un `forms.Form` independiente del modelo, y el registro usa una lista explícita de campos permitidos. El receptor procesa los archivos exclusivamente en RAM mediante un upload handler instalado antes de la comprobación CSRF; una vista interna vuelve a exigir CSRF. Se impiden archivos temporales incluso cuando los handlers generales de Django usarían disco. No se registra el contenido de la presentación en logs ni se utiliza una cola persistente para el correo completo.

La aceptación SMTP y la creación del trámite se coordinan en una transacción. No se conservan adjuntos para reintentos: si el envío falla, el solicitante debe volver a adjuntar los documentos. Como SMTP y la base no comparten una transacción distribuida, un corte después de la aceptación SMTP puede dejar un correo recibido sin una confirmación completa del registro; ante un fallo en ese punto conviene verificar con EDESA antes de reenviar.

El código al solicitante se envía por la bandeja de notificaciones del circuito, después de confirmar la transacción. Si ese segundo correo falla, el trámite sigue válido, el código se muestra en pantalla y el correo del código puede reintentarse. La confirmación usa una cookie firmada, HttpOnly y de diez minutos, que contiene sólo el identificador técnico; no guarda el formulario en sesión ni incluye datos o códigos en la URL. Recargar esa pantalla no reenvía la presentación.

## Continuidad del circuito

El trámite se asigna al ingreso de EDESA. La consulta sigue usando código + NIS + DNI/CUIT del titular, comparando el documento con su hash. Después continúan las recepciones, respuesta de factibilidad, Proyecto Ejecutivo, dictámenes, contrato, inspección y conexión existentes. Los documentos agregados en esas etapas posteriores siguen el almacenamiento privado del circuito; la exclusión de almacenamiento corresponde a la presentación y adjuntos iniciales.

Los trámites anteriores mantienen sus datos y archivos y conservan la consulta habitual. Los creados bajo la política anterior de registro mínimo no recuperan automáticamente los datos que nunca se guardaron: deben consultarse en el correo original de EDESA. La migración añade campos vacíos sin inventar valores ni borrar información.

## Despliegue y comprobaciones

```bash
python manage.py migrate --noinput
python manage.py check
python manage.py test --noinput
```

Configurar `EDESA_SOLICITUD_EMAIL`, las credenciales SMTP y reiniciar Django. En producción, publicar por HTTPS. El proxy y las herramientas de monitoreo tampoco deben registrar cuerpos de formulario ni adjuntos. Si se usa Nginx, desactivar el buffering del cuerpo hacia la aplicación (`proxy_request_buffering off` con HTTP/1.1) y evitar que los cuerpos se vuelquen a temporales; alinear el límite total del proxy con los 16 MB máximos de petición multipart que admite la aplicación. La aplicación por sí sola no controla archivos o logs generados por infraestructura externa.

La suite comprueba campos y adjuntos condicionales, tipos de persona, opciones permitidas, límites, CSRF, ausencia de archivos temporales y guardado de adjuntos, persistencia de todos los datos del formulario, rollback ante fallo SMTP, consulta protegida, continuidad del circuito y no duplicación al recargar la confirmación.
