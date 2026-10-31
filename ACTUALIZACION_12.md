# Actualización 12 · Cambios de guardia y control mensual

## Resultado

Se amplió el módulo Flask/PostgreSQL existente. El botón **Cambio de Guardia** abre un selector con Pagada, Con Reemplazante y Emergencia. La ruta normal anterior sigue disponible como histórico, con sus funciones de carga y edición originales.

El intercambio guarda **una operación con cuatro asignaciones**: solicitante libre y reemplazante cubriendo la primera guardia; reemplazante libre y solicitante cubriendo la guardia inversa. Reutiliza las tablas, formularios de detalle, estilos, búsqueda de fichas, adjuntos privados, auditoría, versiones y eliminación lógica existentes. No modifica una programación laboral externa.

Los horarios de una guardia se completan una vez y se reflejan en la persona que la cubre. El servidor verifica ambas parejas, cuatro estados L/G correctos, personas distintas y dos guardias distintas. Admite mañana 06:00–12:00, tarde 12:00–18:00, noche 18:00–06:00 del día siguiente y guardia diurna de fin de semana 06:00–18:00. Las fechas de la guardia inversa pueden ser anteriores o posteriores.

Pagada conserva sus campos, códigos, horarios, validaciones de detalle y almacenamiento. Solo incorpora el control mensual solicitado. Emergencia reutiliza el formulario existente de dos participantes con horarios válidos y un cupo independiente.

## Criterios del control mensual

| Tipo | Límite | Quién consume cupo |
|---|---:|---|
| Con reemplazante | 2 | Ambos participantes, una vez por operación |
| Pagada | 1 | Solicitante |
| Emergencia | 1 | Solicitante |

- El mes y año corresponden a la **fecha inicial de la primera guardia**, guardada en `fecha_cambio`. La guardia inversa no genera un segundo consumo, incluso si pertenece a otro mes. Este criterio aparece en el formulario.
- La fecha inicial de una operación guardada se conserva, igual que antes de esta actualización. Corregir detalles no traslada retrospectivamente el consumo a otro mes.
- No existe un contador que se borre: se consultan operaciones vigentes de ese mes. Esto conserva todos los meses anteriores y comienza cada mes con su propio cupo.
- Las nuevas cargas de Reemplazante y Emergencia requieren seleccionar las fichas de ambos participantes. La identidad vinculada se conserva aunque posteriormente cambie el nombre de una ficha.
- Pagada mantiene la carga manual. Los registros sin ficha se comparan por nombre normalizado: espacios, mayúsculas y normalización Unicode. No se inventan vínculos históricos por coincidencia de nombres; la precisión de los registros manuales depende del nombre documentado y no permite distinguir homónimos sin ficha.
- Los registros pagados históricos vigentes sí se cuentan. Las cargas `NORMAL` anteriores no se reclasifican automáticamente como intercambios nuevos.
- Cancelar un formulario no genera consumo. La anulación administrativa utiliza la eliminación lógica existente; esos registros dejan de contarse y conservan su historial.
- Altas, ediciones que cambian participantes y restauraciones verifican los cupos dentro de la transacción. Un bloqueo transaccional PostgreSQL compartido por esas operaciones impide superar el límite mediante envíos simultáneos.
- La interfaz consulta automáticamente cupos y disponibles al seleccionar personal o cambiar la primera fecha. Impide el envío por cupo agotado y el servidor vuelve a validar. Después de guardar muestra el resumen actualizado.
- Se conserva la idempotencia de `solicitud_id`. También se rechaza un intercambio idéntico enviado desde un formulario nuevo, incluso con los participantes invertidos. La restauración vuelve a verificar cupo y duplicaciones.

## Base de datos y respaldo local

Migración: `0012_guardias_intercambio`, posterior a `0011_carrera_funcionarios`.

No añade ni elimina tablas o columnas. Amplía la restricción de tipos de `cambios_guardia`, la asociación de propietarios de documentos y el mapeo de categorías de su trigger. Mantiene las protecciones anteriores de adjuntos. No actualiza filas históricas, cuentas, permisos ni programación laboral. El downgrade destructivo está bloqueado.

**Aplicada en la base local** mediante `python -m scripts.migrar_actualizacion12`. Antes se verificó un respaldo conjunto de PostgreSQL y los 8 documentos existentes, activos o retirados. Se compararon todas las columnas y filas de todas las tablas de aplicación antes y después: permanecieron iguales.

Respaldo local privado:

```text
.runtime/backups/antes_actualizacion12_20261031_103434_739263/documentos_20261031_103434_781313/
```

Contiene `postgres.dump`, originales, vistas y `manifest.json` con hashes SHA-256. No está versionado.

Para otra instalación que ya esté en la revisión 0011, detener su servidor y ejecutar:

```powershell
.runtime/python/python.exe -s -m scripts.migrar_actualizacion12
```

Después iniciar la aplicación con el procedimiento habitual. Repetir el script con la revisión 0012 aplicada no modifica datos. No usar este script para saltarse actualizaciones anteriores.

## Archivos modificados o nuevos

| Archivo | Cambio |
|---|---|
| `app/administration/guardias.py` | Selector, rutas nuevas, consulta mensual y mensajes por categoría |
| `app/administration/guardia_records.py` | Validación transaccional de cupos, intercambio y duplicaciones; conserva guardado existente |
| `app/administration/guardia_monthly.py` (nuevo) | Conteo, límites, bloqueo y reglas de los nuevos tipos |
| `app/administration/record_lifecycle.py` | Revalidación de cupos y duplicaciones antes de restaurar guardias |
| `app/models/administration.py` | Tipos de cambio permitidos |
| `app/models/documents.py` | Propietarios de adjuntos de las nuevas categorías |
| `app/documents/service.py` | Mapeo documental para Reemplazante y Emergencia |
| `app/employees/lookup.py` | Tickets de búsqueda para las rutas nuevas, con los permisos existentes |
| `app/hospital_services/records.py` | Categorías nuevas en consulta, archivo, expediente, impresión y eliminación |
| `app/hospital_services/excel.py` | Sufijos de hojas para exportar las nuevas categorías; conserva la plantilla principal anterior |
| `app/templates/administration/guardias.html` | Cuatro asignaciones del intercambio e indicadores mensuales |
| `app/templates/administration/guardia_options.html` (nuevo) | Selector de tipo |
| `app/static/js/guardia_monthly.js` (nuevo) | Sincronización de cada pareja y consulta/bloqueo visual de cupos |
| `app/dashboard_modules.py` | Acceso al selector desde el panel |
| `app/templates/includes/sidebar.html` | Acceso al selector desde el menú |
| `app/templates/administration/reposo.html` | Únicamente el enlace de acceso a Cambio de Guardia apunta al selector |
| `migrations/versions/0012_guardias_intercambio.py` (nuevo) | Ampliación compatible de restricciones y asociación documental |
| `scripts/migrar_actualizacion12.py` (nuevo) | Respaldo verificado, migración y comparación de todas las filas históricas |
| `tests/test_guardias_intercambio.py` (nuevo) | 23 escenarios de integración de intercambio, cupos y conservación |
| `tests/test_auth.py` | Expectativa del enlace al selector nuevo |
| `tests/test_reposos.py` | Expectativa del enlace al selector nuevo |
| `ACTUALIZACION_12.md` (nuevo) | Esta documentación |

Los archivos temporales de ejecución, bases de pruebas, capturas y logs están en `.runtime/`, fuera del control de versiones. No se modificaron dependencias ni tecnologías.

## Verificaciones ejecutadas

- Suite completa de PostgreSQL: **365 aprobadas y 14 fallidas**. Todas las pruebas nuevas de guardias aprobaron. Las 14 fallidas se reprodujeron también sobre una copia limpia de la versión anterior, en otra base independiente: no se introdujeron fallos adicionales.
- Regresión de guardias pagadas y normales: creación, edición, adjuntos, fechas independientes, nocturnos, idempotencia, permisos y separación de categorías.
- Intercambio: cuatro asignaciones, turnos permitidos, rechazo de fechas/horarios/estados inválidos, rechazo de intercambio incompleto y fichas faltantes, duplicaciones, edición con conservación de IDs y rechazo de versiones obsoletas.
- Cupos: ambos participantes, tres límites independientes, cambio de mes/año, guardia inversa en otro mes, nombres manuales normalizados, liberación por eliminación y rechazo de restauración que exceda cupo.
- Concurrencia PostgreSQL: dos solicitudes distintas para el último cupo; solo una confirmó y la otra se rechazó, sin detalles parciales.
- Migración desde 0011 y migración de registros antiguos: conservación de filas y relaciones.
- Adjuntos nuevos: almacenamiento privado, consulta y aislamiento por categoría. Exportación Excel del intercambio con cuatro códigos L/G correctos.
- JavaScript: **36 pruebas aprobadas** de la suite existente, más comprobación sintáctica del script nuevo.
- Chrome real sobre base de pruebas: selector, búsqueda de ambos participantes, réplica de horarios, guardado, consulta de cuatro filas, fecha nocturna al día siguiente, segundo intercambio, contador 2/2 y bloqueo visual de ambos participantes. Sin errores JavaScript. Capturas en escritorio y móvil.
- Compilación Python y revisión de espacios/diferencias con Git.

Evidencia local: `.runtime/test_guardia12_full.log`, `.runtime/test_guardia12_baseline.log`, `.runtime/test_guardia12_node.log` y capturas `.runtime/guardia12_*.png`.

### Fallos anteriores conservados fuera de alcance

Doce casos antiguos intentan registrar Vacaciones sin la ficha que ese módulo ya exige. Otro caso de informe completo espera una hoja de Vacaciones que no se genera al fallar esa carga. El caso restante falla al encadenar migraciones laborales antiguas por eventos de triggers pendientes en `funcionarios`. Se conservaron esas funcionalidades y migraciones sin cambios para respetar la instrucción de no alterar otros módulos. La suite completa no debe presentarse como totalmente aprobada.
