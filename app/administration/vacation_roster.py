from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

from flask import current_app

from app.employees.careers import CAREER_RUBROS
from app.employees.rules import seniority

MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
XML_NS = 'http://www.w3.org/XML/1998/namespace'
TEMPLATE_NAME = 'planilla_vacaciones_2026_2027.xlsx'


def build_roster_rows(records, seniority_date):
    rows = []
    for order, record in enumerate(records, start=1):
        employee = record.funcionario
        links = sorted((link for link in employee.vinculos if link.activo),
            key=lambda link: (link.fecha_ingreso, link.numero_vinculo)) if employee else []
        entry = links[0].fecha_ingreso if links else None
        try:
            years, months, days = seniority(entry, seniority_date) if entry else (None, None, None)
            seniority_label = f'{years} años, {months} meses, {days} días' if years is not None else ''
        except ValueError:
            seniority_label = ''
        career = employee.carrera if employee and employee.carrera else ''
        rows.append({
            'order': order,
            'name': employee.nombre_completo if employee else record.nombres_apellidos,
            'cedula': employee.cedula if employee else '',
            'rubro': CAREER_RUBROS.get(career, ''),
            'career': career,
            'entry': entry,
            'seniority': seniority_label,
            'start': record.fecha_inicio,
            'end': record.fecha_termino,
            'days': record.total_dias,
            'links': ', '.join(str(link.numero_vinculo) for link in links),
            'observation': '',
        })
    return rows


def _column_name(number):
    result = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _excel_serial(value):
    return (value - date(1899, 12, 30)).days


def _set_cell(cell, value):
    for child in list(cell):
        cell.remove(child)
    cell.attrib.pop('t', None)
    if value is None or value == '':
        return
    if isinstance(value, date):
        value = _excel_serial(value)
    if isinstance(value, str):
        cell.set('t', 'inlineStr')
        inline = ET.SubElement(cell, f'{{{MAIN_NS}}}is')
        text = ET.SubElement(inline, f'{{{MAIN_NS}}}t')
        text.set(f'{{{XML_NS}}}space', 'preserve')
        text.text = value
    else:
        node = ET.SubElement(cell, f'{{{MAIN_NS}}}v')
        node.text = str(value)


def _row_template(sheet_data, row_number):
    return next((row for row in sheet_data.findall(f'{{{MAIN_NS}}}row')
        if row.get('r') == str(row_number)), None)


def _ensure_row(sheet_data, row_number):
    row = _row_template(sheet_data, row_number)
    if row is not None:
        return row
    template = _row_template(sheet_data, 9 if row_number % 2 else 10)
    row = deepcopy(template)
    row.set('r', str(row_number))
    for cell in row.findall(f'{{{MAIN_NS}}}c'):
        column = re.match(r'[A-Z]+', cell.get('r')).group()
        cell.set('r', f'{column}{row_number}')
        _set_cell(cell, None)
    sheet_data.append(row)
    return row


def _write_row(sheet_data, row_number, values):
    row = _ensure_row(sheet_data, row_number)
    cells = {re.match(r'[A-Z]+', cell.get('r')).group(): cell
        for cell in row.findall(f'{{{MAIN_NS}}}c')}
    for column_number, value in enumerate(values, start=1):
        column = _column_name(column_number)
        cell = cells[column]
        _set_cell(cell, value)


def render_roster_workbook(rows, template_path=None):
    template = Path(template_path) if template_path else Path(current_app.root_path) / 'assets' / TEMPLATE_NAME
    with zipfile.ZipFile(template, 'r') as source:
        contents = {item.filename: (item, source.read(item.filename)) for item in source.infolist()}
    sheet_item, sheet_xml = contents['xl/worksheets/sheet1.xml']
    for _, (prefix, uri) in ET.iterparse(BytesIO(sheet_xml), events=('start-ns',)):
        ET.register_namespace(prefix or '', uri)
    root = ET.fromstring(sheet_xml)
    sheet_data = root.find(f'{{{MAIN_NS}}}sheetData')
    header_row = _row_template(sheet_data, 7)
    header_cells = {cell.get('r'): cell for cell in header_row.findall(f'{{{MAIN_NS}}}c')}
    _set_cell(header_cells['C7'], 'C.I. Nº')
    _set_cell(header_cells['G7'], 'ANTIGÜEDAD')
    for row_number in range(9, 34):
        row = _row_template(sheet_data, row_number)
        for cell in row.findall(f'{{{MAIN_NS}}}c'):
            _set_cell(cell, None)
    for index, row in enumerate(rows):
        values = [row['order'], row['name'], row['cedula'], row['rubro'], row['career'],
            row['entry'], row['seniority'], row['start'], row['end'], row['days'],
            row['links'], row['observation']]
        _write_row(sheet_data, index + 9, values)

    dimension = root.find(f'{{{MAIN_NS}}}dimension')
    last_row = max(33, len(rows) + 8)
    if dimension is not None:
        dimension.set('ref', f'A1:L{last_row}')
    contents['xl/worksheets/sheet1.xml'] = (
        sheet_item, ET.tostring(root, encoding='utf-8', xml_declaration=True))

    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as destination:
        for item, payload in contents.values():
            destination.writestr(item, payload)
    output.seek(0)
    return output
