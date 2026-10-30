"""Informes XlsxWriter en memoria. El libro de referencia nunca se importa.

Las tres áreas A:E, G:I y K:P mantienen la disposición original. Las hojas
complementarias conservan cobertura, categoría, participantes y auditoría.
"""
from datetime import date, datetime, time
from io import BytesIO
import math
import re
import xlsxwriter
from app.dashboard_clock import PARAGUAY_TIMEZONE
from app.hospital_services.catalog import SHEET_NAMES
from app.hospital_services.records import CATEGORIES, matching_details

EMPTY = 'Sin registros en el período seleccionado'
AUDIT_HEADERS = ['ID del registro', 'Usuario de carga', 'Fecha y hora de carga (Paraguay)',
    'Último editor', 'Última modificación (Paraguay)', 'Versión', 'DOCUMENTOS ADJUNTOS', 'Cantidad de fotografías']
SUFFIXES = {'justificativos': 'JUST', 'reposos': 'REPOSOS', 'guardias': 'GUARDIAS',
    'pagadas': 'PAGADAS', 'vacaciones': 'VACACIONES', 'comisionados': 'COMISIONADOS'}


def worksheet_name(label, used):
    clean = re.sub(r"[\[\]:*?/\\]", '-', label).strip(" '") or 'Servicio'
    if clean.casefold() == 'history':
        clean = 'SERVICIO_HISTORY'
    candidate = clean[:31]
    index = 2
    while candidate.casefold() in used:
        tail = f'_{index}'
        candidate = clean[:31 - len(tail)] + tail
        index += 1
    used.add(candidate.casefold())
    return candidate


class ExcelReport:
    def __init__(self, form):
        self.form = form
        self.output = BytesIO()
        # Texto introducido por personas nunca se interpreta como fórmula o URL.
        self.book = xlsxwriter.Workbook(self.output, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
        self.book.set_properties({'title': 'Informe administrativo por servicios', 'author': 'Departamento de Enfermería - Hospital Regional CDE'})
        base = {'font_name': 'Arial', 'font_size': 10, 'valign': 'vcenter', 'border': 1, 'border_color': '#8C939B', 'text_wrap': True}
        self.fmt = {k: self.book.add_format({**base, **v}) for k, v in {
            'body': {}, 'alt': {'bg_color': '#F0F2F4'}, 'date': {'num_format': 'dd/mm/yyyy'},
            'stamp': {'num_format': 'dd/mm/yyyy hh:mm:ss'}, 'time': {'num_format': 'hh:mm'},
            'header': {'bold': True, 'bg_color': '#FFFF00', 'align': 'center'},
            'section': {'bold': True, 'bg_color': '#D9E2F3', 'align': 'center'},
            'group': {'bold': True, 'bg_color': '#D1D5DB'},
        }.items()}
        self.title = self.book.add_format({'font_name': 'Arial', 'font_size': 14, 'bold': True, 'valign': 'vcenter'})
        self.context = self.book.add_format({'font_name': 'Arial', 'font_size': 10, 'valign': 'vcenter', 'text_wrap': True})
        self.used = set()
        self.row_heights = {}

    def sheet(self, name, service, columns):
        sheet = self.book.add_worksheet(name)
        self.row_heights[name] = {}
        sheet.hide_gridlines(2)
        sheet.set_landscape()
        sheet.set_paper(9)  # A4
        sheet.set_margins(0.25, 0.25, 0.4, 0.4)
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(0, 6)
        sheet.freeze_panes(7, 1)
        sheet.set_header('&LHospital Regional CDE&R' + service.codigo)
        sheet.set_footer('&LDocumento de uso administrativo&R Página &P de &N')
        sheet.set_column(0, columns - 1, 19)
        sheet.merge_range(0, 0, 0, columns - 1, 'DEPARTAMENTO DE ENFERMERÍA', self.title)
        sheet.merge_range(1, 0, 1, columns - 1, 'HOSPITAL REGIONAL CDE', self.context)
        sheet.merge_range(2, 0, 2, columns - 1, f'Servicio: {service.nombre}', self.context)
        period = f'Período: {self.form.desde.data:%d/%m/%Y} al {self.form.hasta.data:%d/%m/%Y}'
        sheet.merge_range(3, 0, 3, columns - 1, period, self.context)
        sheet.set_row(0, 25)
        sheet.set_row(2, 23)
        sheet.set_row(3, 23)
        return sheet

    def value(self, sheet, row, col, value, alt=False):
        fmt = self.fmt['alt' if alt else 'body']
        if isinstance(value, datetime):
            local = value.astimezone(PARAGUAY_TIMEZONE).replace(tzinfo=None) if value.tzinfo else value
            sheet.write_datetime(row, col, local, self.fmt['stamp'])
        elif isinstance(value, date):
            sheet.write_datetime(row, col, datetime.combine(value, time()), self.fmt['date'])
        elif isinstance(value, time):
            sheet.write_datetime(row, col, value, self.fmt['time'])
        elif value is None:
            sheet.write_blank(row, col, None, fmt)
        else:
            sheet.write(row, col, value, fmt)

    def write_row(self, sheet, row, col, values, widths=None, alt=False):
        height = 24
        for i, value in enumerate(values):
            self.value(sheet, row, col + i, value, alt)
            if isinstance(value, str):
                width = widths[i] if widths else 19
                lines = sum(max(1, math.ceil(len(part) / max(5, width - 2))) for part in value.split('\n'))
                height = max(height, lines * 13 + 8)
        # En el libro principal otros bloques comparten esta misma fila.
        heights = self.row_heights[sheet.name]
        existing = heights.get(row, 0)
        heights[row] = max(existing, height)
        sheet.set_row(row, max(existing, height))

    def main(self, sheet, item):
        data = item['records']
        widths = [17, 12, 17, 8, 14, 2, 17, 14, 22, 2, 17, 12, 12, 8, 22, 15]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)
        blocks = [(0, 4, 'CAMBIO DE GUARDIA', ['Nombre y Apellido', 'Fecha de cambio', 'Nombre y Apellido (S/R)', 'Código', 'Horario']),
                  (6, 8, 'JUSTIFICATIVO', ['Nombre y Apellido', 'Fecha del día libre / inasistencia', 'Motivo']),
                  (10, 15, 'REPOSO', ['Nombre y Apellido', 'Fecha desde', 'Fecha hasta', 'Total de días', 'Diagnóstico', 'Fecha de entrega al Departamento'])]
        for start, end, label, headers in blocks:
            sheet.merge_range(5, start, 5, end, label, self.fmt['section'])
            sheet.write_row(6, start, headers, self.fmt['header'])
        sheet.set_row(5, 24)
        sheet.set_row(6, 48)
        row = 7
        guards = sorted(data.get('guardias', []) + data.get('pagadas', []), key=lambda r: (min(d.fecha_guardia for d in matching_details(r, self.form.desde.data, self.form.hasta.data)), r.id))
        for record in guards:
            label = f'CAMBIO #{record.id} · {record.tipo_cambio}\nS: {record.solicitante} / R: {record.reemplazante}'
            sheet.merge_range(row, 0, row, 4, label, self.fmt['group'])
            heights = self.row_heights[sheet.name]
            group_height = 15 * sum(max(1, math.ceil(len(line) / 60)) for line in label.split('\n')) + 12
            heights[row] = max(44, group_height, heights.get(row, 0))
            sheet.set_row(row, heights[row])
            row += 1
            for detail in matching_details(record, self.form.desde.data, self.form.hasta.data):
                hours = f'{detail.hora_inicio:%H:%M} a {detail.hora_fin:%H:%M}' + (' (+1 día)' if detail.finaliza_dia_siguiente else '')
                self.write_row(sheet, row, 0, [record.solicitante, detail.fecha_guardia,
                    f'{detail.funcionario} ({detail.participante})', detail.codigo or '', hours], widths[:5], record.id % 2 == 0)
                row += 1
        if not guards:
            sheet.merge_range(7, 0, 7, 4, EMPTY if any(k in data for k in ('guardias', 'pagadas')) else 'Categoría no incluida en este informe', self.fmt['body'])
        last = max(8, row)
        for key, start, end, field_names in [('justificativos', 6, 8, ('nombres_apellidos', 'fecha_inasistencia', 'motivo')),
                ('reposos', 10, 15, tuple(k for k, _ in CATEGORIES['reposos'].fields))]:
            rows = data.get(key, [])
            for index, record in enumerate(rows):
                self.write_row(sheet, 7 + index, start, [getattr(record, field) for field in field_names], widths[start:end + 1], index % 2 == 1)
            if not rows:
                sheet.merge_range(7, start, 7, end, EMPTY if key in data else 'Categoría no incluida en este informe', self.fmt['body'])
            last = max(last, 7 + len(rows))
        sheet.print_area(0, 0, last - 1, 15)

    @staticmethod
    def audit_values(record):
        return [record.id, record.usuario_registro.username, record.fecha_creacion,
            record.usuario_modificacion.username if record.usuario_modificacion else '', record.fecha_modificacion, record.version,
            'Sí' if record.documentos_count else 'No', record.documentos_count]

    def complementary(self, item, key, rows):
        service, category = item['service'], CATEGORIES[key]
        base = SHEET_NAMES.get(service.codigo, service.codigo)
        suffix = SUFFIXES[key]
        name = worksheet_name(base[:30 - len(suffix)] + '_' + suffix, self.used)
        if category.kind:
            headers = ['ID del cambio', 'Solicitante (S)', 'Reemplazante (R)', 'Tipo de cambio', 'Funcionario correspondiente',
                'Participante (S/R)', 'Fecha de guardia', 'Hora de inicio', 'Hora de finalización', 'Fecha de finalización',
                'Código original', 'ID del detalle', 'Orden del detalle', 'Fecha original de carga de guardia',
                'Hora de inicio original', 'Hora de finalización original'] + AUDIT_HEADERS[1:]
        else:
            headers = [label for _, label in category.fields] + AUDIT_HEADERS
        sheet = self.sheet(name, service, len(headers))
        sheet.merge_range(5, 0, 5, len(headers) - 1, category.label, self.fmt['section'])
        sheet.write_row(6, 0, headers, self.fmt['header'])
        sheet.set_row(6, 48)
        # Complementos más cómodos para leer/imprimir que la plantilla de tres bloques.
        if category.kind:
            print_widths = [10, 24, 24, 12, 24, 10, 14, 12, 12, 14, 10]
            print_last = 10
        else:
            print_widths = [38 if field in ('motivo', 'diagnostico') else 25 if field in ('nombres_apellidos', 'lugar') else 12 if field == 'total_dias' else 16 for field, _ in category.fields] + [10]
            print_last = len(category.fields)
        for col in range(len(headers)):
            sheet.set_column(col, col, print_widths[col] if col < len(print_widths) else 24)
        sheet.merge_range(4, 0, 4, len(headers) - 1,
            'La auditoría y los datos originales se conservan en las columnas adicionales a la derecha del área de impresión.', self.context)
        sheet.set_row(4, 24)
        row = 7
        for index, record in enumerate(rows):
            if category.kind:
                for detail in matching_details(record, self.form.desde.data, self.form.hasta.data):
                    values = [record.id, record.solicitante, record.reemplazante, record.tipo_cambio, detail.funcionario,
                        detail.participante, detail.fecha_guardia, detail.hora_inicio, detail.hora_fin, detail.fecha_fin,
                        detail.codigo or '', detail.id, detail.orden, record.fecha_cambio, record.hora_inicio, record.hora_fin]
                    self.write_row(sheet, row, 0, values + self.audit_values(record)[1:], alt=index % 2 == 1)
                    row += 1
            else:
                values = [getattr(record, field) for field, _ in category.fields]
                if key == 'justificativos' and record.fecha_cobertura is None:
                    values[3] = 'SIN COBERTURA'
                self.write_row(sheet, row, 0, values + self.audit_values(record), alt=index % 2 == 1)
                row += 1
        if row == 7:
            sheet.merge_range(row, 0, row, len(headers) - 1, EMPTY, self.fmt['body'])
            row += 1
        sheet.autofilter(6, 0, row - 1, len(headers) - 1)
        sheet.print_area(0, 0, row - 1, print_last)

    def build(self, data):
        # Reservar primero todos los nombres principales evita colisiones con sufijos.
        sheets = [(self.sheet(worksheet_name(SHEET_NAMES.get(item['service'].codigo, item['service'].codigo), self.used),
                              item['service'], 16), item) for item in data]
        for sheet, item in sheets:
            self.main(sheet, item)
        for item in data:
            for key, rows in item['records'].items():
                if rows or self.form.categoria.data != 'completo':
                    self.complementary(item, key, rows)
        self.book.close()
        self.output.seek(0)
        return self.output


def generate_excel(form, data):
    return ExcelReport(form).build(data)
