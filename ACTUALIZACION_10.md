# Actualización 10 — Funcionarios y fichas personales

Se agrega el módulo **Funcionario** sobre la aplicación existente. No se reconstruye el sistema, no se importan datos de identidad externos ni se asocian registros históricos por semejanzas de nombres. El catálogo de funcionarios comienza vacío hasta que una cuenta autorizada registre fichas reales.

## Instalación y migración en Windows

1. Detén el servidor con Ctrl+C en su consola. Conserva `.env`, `instance/`, PostgreSQL y el almacenamiento S3/volumen existente.
2. Desde PowerShell, dentro del proyecto:

```powershell
Set-Location 'C:\Users\vi852\Desktop\Sistema de carga de documentos'
& .runtime/python/python.exe -s -m pip install -r requirements.txt
& .runtime/python/python.exe -s -m scripts.migrar_actualizacion10
& .runtime/python/python.exe -s -m flask --app run db check
```

Puedes sustituir el Python portátil por el de tu `.venv`. La dependencia directa nueva es `python-dateutil`; ya estaba instalada como dependencia del almacenamiento S3, y ahora queda declarada expresamente.

El script exige la actualización 9 y crea un respaldo privado en `.runtime/backups/antes_actualizacion10_FECHA/`. Incluye `postgres.dump`, los originales y vistas documentales activos y retirados, y un manifiesto SHA-256. Verifica `pg_restore --list` y cada objeto **antes** de migrar. Si no puede completar/verificar el respaldo, no aplica cambios al esquema. Ejecuta el procedimiento con el servidor detenido para mantener consistente la comparación.

La revisión nueva es `0009_funcionarios`. Después de migrar compara todas las columnas anteriores, incluyendo contraseñas, cuentas, servicios, registros, adjuntos y auditorías, y verifica las protecciones anteriores. `scripts.initialize` e `iniciar.ps1` detectan esta transición y usan el mismo respaldo. No restablecen la contraseña ni modifican la protección de `victor`.

3. Inicia normalmente:

```powershell
& .runtime/python/python.exe -s -m waitress --listen=127.0.0.1:5000 run:app
```

No ejecutes `create_all`, `drop_all`, reinicios de tablas ni restauraciones sobre la base de uso. La migración conserva columnas y filas anteriores. No ofrece un downgrade destructivo automático.

## Buscar, registrar y consultar

Superadministrador y Jefatura ven **Funcionario** en el Dashboard y el menú lateral. El botón abre **BÚSQUEDA DE FUNCIONARIOS**. La búsqueda se envía por POST con CSRF; el número de cédula no se incorpora a la URL ni se consulta en servicios externos.

Se aceptan de 1 a 12 dígitos ASCII positivos, con o sin puntos de miles. Se eliminan los puntos y ceros iniciales para comparar; `1.234.567`, `1234567` y `001234567` identifican la misma ficha. Esta validación es de formato y unicidad local: no certifica la identidad ante un organismo público. No acepta cero, letras, espacios interiores, guiones ni separadores mal formados.

Si existe, se abre la ficha por su ID interno. Si no existe, aparece el mensaje solicitado y **+ REGISTRAR NUEVO FUNCIONARIO**. El botón conserva la cédula normalizada mediante otro POST, sin guardar datos personales en cookies ni cadenas de consulta. También se puede abrir directamente el formulario de alta.

Campos obligatorios: nombres, apellidos, cédula, nacimiento, dirección, fecha exacta de ingreso, cantidad de vínculos y servicio hospitalario. La fotografía es opcional. La cantidad de vínculos acepta enteros de cero en adelante. No se implementan contratos, salarios ni detalles laborales adicionales.

La ficha muestra fotografía/avatar, nombre completo, cédula, datos personales e institucionales, creador y último editor. Los botones autorizados permiten editar, cambiar foto, consultar historial y regresar al buscador o panel principal. No hay eliminación física de fichas en esta etapa.

## Edad, año de ingreso y antigüedad

No se almacenan edad, antigüedad ni año de ingreso como valores fijos. Se calculan en Python a partir de las fechas guardadas y la fecha actual en `America/Asuncion`.

- Edad: años completos mediante `dateutil.relativedelta`.
- Año de ingreso: `fecha_ingreso.year`; el formulario lo muestra en un campo de solo lectura.
- Antigüedad: años, meses y días de calendario con `relativedelta`, sin dividir por 365 ni por 30.

Ejemplos al 22/10/2026: nacimiento 15/05/1990 → **36 años**; ingreso 10/03/2015 → **11 años, 7 meses y 12 días**. Los finales de mes y años bisiestos siguen las reglas de calendario de `relativedelta`; por ejemplo, 31/01/2024 a 29/02/2024 equivale a un mes. Para nacimientos del 29/02, la biblioteca considera el 28/02 como aniversario en años no bisiestos. Si la institución establece otra regla, puede centralizarse en `app/employees/rules.py`.

No se aceptan fechas futuras ni ingreso anterior al nacimiento. Si solo se conoce el año, el formulario solicita la fecha completa y no inventa día o mes. Al consultar otra vez se recalculan los datos. La ficha abierta también se recarga cuando el reloj institucional cambia de día, sin depender de la zona horaria del dispositivo; esa recarga no se aplica a formularios de edición.

## Fotografías personales privadas

Se reutilizan validación, almacenamiento local privado/S3, originales, vistas sin metadatos, auditoría, compensación ante errores, conciliación y respaldo de la actualización 9. No es necesario contratar otro almacenamiento para las fichas.

- Una fotografía activa por funcionario, con límite inicial de 8 MB usando `DOCUMENT_MAX_BYTES`.
- JPG/JPEG, PNG y WEBP estáticos, verificados por decodificación completa con Pillow. HEIC necesita conversión previa.
- Selector, cámara en dispositivos táctiles compatibles, vista previa y posibilidad de quitar la selección antes de guardar.
- Avatar institucional con ícono cuando no hay foto.
- La vista de la ficha se entrega por una ruta Flask autorizada, con `no-store`; nunca desde `static` o una URL pública S3.

Al reemplazar una imagen se retira lógicamente la anterior, se guarda la nueva y se actualiza la referencia de la ficha dentro de la misma transacción PostgreSQL. Si falla, se conserva el estado anterior y se compensan los objetos nuevos. Los archivos anteriores se mantienen privados con su motivo, usuario y fecha de retiro. No se agrega una descarga pública ni una galería accesible para Operadores/Supervisores.

En Railway sigue siendo obligatorio configurar S3 o un volumen persistente declarado. El usuario todavía no ha configurado un bucket: se conserva el almacenamiento privado local existente. Consulta `ACTUALIZACION_9.md` antes de desplegar o cambiar de backend. Cambiar una variable de entorno no traslada fotografías antiguas.

## Permisos y búsqueda desde formularios administrativos

| Rol | Ficha completa, domicilio, nacimiento y foto | Alta / edición / foto | Historial de ficha | Búsqueda operativa mínima |
|---|---|---|---|---|
| Superadministrador | Sí | Sí | Sí | Sí |
| Jefatura | Sí | Sí | Sí | Sí |
| Operador | No | No | No | Solo desde formularios autorizados |
| Supervisor | No | No | No | Solo desde formularios autorizados |

Los permisos `employees.read`, `employees.manage`, `employees.history` y `employees.lookup` están centralizados en Python. Acceder directamente a una URL no evita la autorización. Sin sesión se exige login; un rol sin permiso recibe 403 y no modifica datos. Se conserva el control de primer acceso y la revocación de sesiones existentes.

Los seis formularios administrativos muestran una búsqueda **opcional** por cédula. Cambio de Guardia normal y pagada tienen una para el solicitante y otra para el reemplazante. Un resultado devuelve exclusivamente el ID interno y el nombre completo; no entrega dirección, nacimiento, fotografía, servicio ni una ficha completa.

El endpoint es POST, exige sesión y CSRF, y valida un contexto firmado de un formulario administrativo de esa sesión, con vencimiento de 30 minutos. Permite 30 búsquedas por usuario y minuto mediante un contador PostgreSQL compartido que no almacena cédulas. No ofrece listados generales ni búsqueda parcial de nombres para roles de carga.

Al encontrar al funcionario, se completa el nombre y se guarda su ID cuando el usuario confirma la carga. El servicio administrativo sigue seleccionándose expresamente; no se sustituye automáticamente por el servicio actual de la ficha. **QUITAR VÍNCULO** conserva el nombre como texto y elimina la asociación propuesta; editar manualmente el nombre también quita el vínculo en el navegador. El backend vuelve a comprobar ID y nombre si se envía una asociación.

La carga manual anterior continúa disponible: no obliga a crear fichas para conservar o registrar datos administrativos. Los registros históricos reciben relaciones NULL. No se buscan coincidencias por nombres ni se cambian sus textos. Una modificación posterior del nombre de la ficha no reescribe los nombres documentados en registros ya guardados. Si se edita un registro vinculado, se permite conservar su nombre histórico y la misma relación; cambiar la asociación requiere una selección explícita.

## Estructura e integridad PostgreSQL

Nueva tabla `funcionarios`: campos solicitados, más `usuario_modificacion_id`, `solicitud_id` para reenvíos seguros y `version` para evitar sobrescrituras concurrentes. Tiene cédula canónica única, vínculos no negativos, fechas coherentes, servicio real y creadores/editores con FK. Los triggers validan servicio activo al asignarlo y preservan identidad y auditoría inicial. Un servicio posteriormente inactivo puede conservarse al corregir otros datos de la ficha; no puede seleccionarse para una nueva asignación.

`documentos_adjuntos` incorpora `funcionario_id`. Su CHECK exige un único propietario y un índice único parcial permite solo una foto personal activa. Las referencias y metadatos originales siguen siendo inmutables. La referencia `foto_ruta` de la ficha está protegida por FK y triggers diferidos que comprueban propietario, actividad y coincidencia de la fotografía al confirmar la transacción. No se puede vincular por error la foto de otra ficha desde una operación SQL.

Relaciones opcionales nuevas, sin backfill:

- Justificativos, Reposos, Vacaciones y Comisionados: `funcionario_id`.
- Cambios de Guardia: `solicitante_funcionario_id` y `reemplazante_funcionario_id`, también para PAGADA. Un CHECK impide usar la misma ficha en ambos puestos.

Las relaciones usan RESTRICT y no borran registros. Los informes Excel anteriores mantienen su estructura y no incorporan domicilios, nacimientos ni fotografías personales.

## Historial, respaldo y privacidad

El historial registra creador/editor, fecha, operación, ID de ficha, campos modificados y referencias de fotografías. No replica los valores anteriores de domicilios, cédulas o fechas de nacimiento en logs o descripciones de actividad. Los valores actuales permanecen en la ficha protegida. Los cambios de servicio quedan trazados con las referencias anterior/nueva.

Los comandos existentes incluyen automáticamente las fotos personales y sus versiones retiradas:

```powershell
& .runtime/python/python.exe -s -m scripts.respaldar_documentos
& .runtime/python/python.exe -s -m flask --app run conciliar-documentos --verificar
```

Respalda PostgreSQL y objetos juntos; conserva copias cifradas fuera del servidor. Para recuperar, usa una base nueva aislada, repón los objetos con sus mismas claves en un almacenamiento privado, verifica el manifiesto y ejecuta la conciliación antes de probar las fichas. No restaures por encima de la base de uso sin el procedimiento institucional correspondiente. La protección HTTPS/cookies seguras en producción permanece vigente.

## Pruebas manuales

1. Con `victor` o Jefatura abre Funcionario. Busca una cédula no registrada: debe mostrar el mensaje de ausencia y el botón de alta, sin datos inventados.
2. Registra una ficha real autorizada, servicio y fecha exacta de ingreso. Prueba cero y dos vínculos; no debe aceptar negativos, decimales ni fechas futuras.
3. Busca su cédula con y sin puntos. Debe abrir la misma ficha; intentar otra alta con la misma cédula normalizada devuelve conflicto sin duplicarla.
4. Comprueba edad, año y antigüedad según la fecha del reloj de Paraguay. Un año de ingreso aislado no debe convertirse en una fecha ficticia.
5. Carga una foto válida. Prueba una extensión falsa, HEIC no convertido y dos fotos: deben rechazarse sin una ficha parcial.
6. Edita la dirección, reemplaza la foto y revisa historial, actor y fecha. La foto anterior se conserva retirada. Con dos sesiones, una edición obsoleta debe devolver 409.
7. Cierra sesión y reinicia conservando `instance/`/bucket/volumen. Comprueba la ficha y su foto.
8. Con Operador/Supervisor verifica que no aparezca el botón Funcionario ni se abran directamente fichas, edición, historial o fotos (403).
9. Con esos roles abre un formulario administrativo y busca por cédula: debe completar solo el nombre. Guarda y comprueba la relación desde una cuenta autorizada; no debe permitir elegir la misma persona como solicitante y reemplazante.
10. Cambia posteriormente el nombre de una ficha: los textos históricos deben conservarse. Comprueba también login, Dashboard, los seis módulos, adjuntos, carpetas y Excel anteriores.

## Pruebas automatizadas y entrega

Usa una base `TEST_DATABASE_URL` dedicada terminada en `_test`; las fotografías de prueba se guardan en un almacenamiento aislado. No uses la base real con fixtures:

```powershell
& .runtime/python/python.exe -s -m pytest -q
node --test tests/*.test.cjs
```

El ZIP completo es `entregables/fuentes_actualizacion10.zip`; `entregables/ARCHIVOS_ACTUALIZACION_10.md` identifica archivos nuevos/modificados. Se excluyen `.env`, `instance/`, bases PostgreSQL, fotografías privadas, respaldos y datos de prueba. `VALIDACION.md` recoge los resultados verificados y sus límites.

Validación final local del 22/10/2026: **323 pruebas Python y 33 JavaScript aprobadas**. Incluye 56 pruebas específicas del módulo Funcionario. La migración real, la comparación de datos históricos, `flask db check`, `pip check`, la inicialización idempotente, la conciliación y la prueba HTTP del servidor finalizaron correctamente. No se cargaron fichas ficticias en la base de uso.
