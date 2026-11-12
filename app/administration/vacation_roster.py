from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path
import re
import math
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


def render_roster_workbook(rows, template_path=None, service_name=None):
    template = Path(template_path) if template_path else Path(current_app.root_path) / 'assets' / TEMPLATE_NAME
    with zipfile.ZipFile(template, 'r') as source:
        contents = {item.filename: (item, source.read(item.filename)) for item in source.infolist()}
    sheet_item, sheet_xml = contents['xl/worksheets/sheet1.xml']
    for _, (prefix, uri) in ET.iterparse(BytesIO(sheet_xml), events=('start-ns',)):
        ET.register_namespace(prefix or '', uri)
    root = ET.fromstring(sheet_xml)
    sheet_data = root.find(f'{{{MAIN_NS}}}sheetData')
    # Conservar los títulos oficiales. El nombre del servicio ocupa la celda
    # L6 libre de la plantilla, sin sustituir el título A6:K6 ni combinar datos.
    if service_name:
        service_cell = next(c for c in _row_template(sheet_data, 6) if c.get('r') == 'L6')
        _set_cell(service_cell, service_name)
    for row_number in range(9, 34):
        row = _row_template(sheet_data, row_number)
        for cell in row.findall(f'{{{MAIN_NS}}}c'):
            _set_cell(cell, None)
    styles_item, styles_xml = contents['xl/styles.xml']
    styles = ET.fromstring(styles_xml)
    xfs = styles.find(f'{{{MAIN_NS}}}cellXfs')
    wrapped = {}
    widths = {i: 12 for i in range(1, 13)}
    for column in root.findall(f'{{{MAIN_NS}}}cols/{{{MAIN_NS}}}col'):
        for number in range(int(column.get('min')), min(12, int(column.get('max'))) + 1):
            widths[number] = float(column.get('width', '12'))
    for index, row in enumerate(rows):
        values = [row['order'], row['name'], row['cedula'], row['rubro'], row['career'],
            row['entry'], row['seniority'], row['start'], row['end'], row['days'],
            row['links'], row['observation']]
        _write_row(sheet_data, index + 9, values)
        written = _row_template(sheet_data, index + 9)
        for cell in written.findall(f'{{{MAIN_NS}}}c'):
            original_style = int(cell.get('s', '0'))
            column = re.match(r'[A-Z]+', cell.get('r')).group()
            # La plantilla asigna por error formato de fecha a TOTAL DE DÍAS.
            # Corregir solo esa celda de datos para que 15 no sea 15/01/1900.
            style_key = (original_style, column == 'J')
            if style_key not in wrapped:
                style = deepcopy(xfs[original_style])
                if column == 'J':
                    style.set('numFmtId', '0')
                    style.set('applyNumberFormat', '1')
                alignment = style.find(f'{{{MAIN_NS}}}alignment')
                if alignment is None:
                    alignment = ET.SubElement(style, f'{{{MAIN_NS}}}alignment')
                alignment.set('wrapText', '1')
                style.set('applyAlignment', '1')
                wrapped[style_key] = len(xfs)
                xfs.append(style)
            cell.set('s', str(wrapped[style_key]))
        lines = max((math.ceil(len(str(value)) / max(6, widths[i] - 2))
            for i, value in enumerate(values, start=1) if isinstance(value, str)), default=1)
        written.set('ht', str(max(16, 14 * lines + 4)))
        written.set('customHeight', '1')

    last_row = max(9, len(rows) + 8)
    for row in list(sheet_data):
        if int(row.get('r')) > last_row:
            sheet_data.remove(row)
    xfs.set('count', str(len(xfs)))
    # Conservar namespaces declarados por Excel en la raíz (mc:Ignorable).
    original_styles = styles_xml.decode('utf-8')
    original_xfs = re.search(r'<cellXfs\b[^>]*>.*?</cellXfs>', original_styles, re.S)
    new_xfs = ET.tostring(xfs, encoding='unicode')
    new_xfs = re.sub(r'ns\d+:', '', new_xfs)
    contents['xl/styles.xml'] = (styles_item, (original_styles[:original_xfs.start()] + new_xfs
        + original_styles[original_xfs.end():]).encode('utf-8'))

    dimension = root.find(f'{{{MAIN_NS}}}dimension')
    if dimension is not None:
        dimension.set('ref', f'A1:L{last_row}')
    setup = root.find(f'{{{MAIN_NS}}}pageSetup')
    setup.set('orientation', 'landscape')  # Autorizado: mismo formato que PAI.
    setup.set('fitToWidth', '1')
    setup.set('fitToHeight', '0')
    setup.attrib.pop('scale', None)
    sheet_properties = root.find(f'{{{MAIN_NS}}}sheetPr')
    if sheet_properties is None:
        sheet_properties = ET.Element(f'{{{MAIN_NS}}}sheetPr')
        root.insert(0, sheet_properties)
    fit = sheet_properties.find(f'{{{MAIN_NS}}}pageSetUpPr')
    if fit is None:
        fit = ET.SubElement(sheet_properties, f'{{{MAIN_NS}}}pageSetUpPr')
    fit.set('fitToPage', '1')
    # Parchar solo estructuras editables y mantener las demás partes exactas.
    updated_sheet = sheet_xml.decode('utf-8')
    for local_name, element in [('sheetData', sheet_data), ('dimension', dimension),
            ('pageSetup', setup), ('sheetPr', sheet_properties)]:
        if element is None:
            continue
        pattern = rf'<{local_name}\b[^>]*(?:/>|>.*?</{local_name}>)'
        serialized = ET.tostring(element, encoding='unicode')
        if re.search(pattern, updated_sheet, re.S):
            updated_sheet = re.sub(pattern, lambda _: serialized, updated_sheet, count=1, flags=re.S)
        elif local_name == 'sheetPr':
            start = re.search(r'<worksheet\b[^>]*>', updated_sheet).end()
            updated_sheet = updated_sheet[:start] + serialized + updated_sheet[start:]
    # Los filtros acompañan las filas reales sin modificar columnas.
    updated_sheet = re.sub(r'(<autoFilter\b[^>]*ref=")[^"]+', rf'\g<1>A7:L{last_row}', updated_sheet)
    contents['xl/worksheets/sheet1.xml'] = (sheet_item, updated_sheet.encode('utf-8'))
    workbook_item, workbook_xml = contents['xl/workbook.xml']
    workbook = workbook_xml.decode('utf-8')
    workbook = re.sub(r'(<definedName\b[^>]*name="_xlnm\._FilterDatabase"[^>]*>)[^<]+',
        lambda m: m.group(1) + f"'GRAL.'!$A$7:$L${last_row}", workbook)
    additions = (f'<definedName name="_xlnm.Print_Area" localSheetId="0">\'GRAL.\'!$A$1:$L${last_row}</definedName>'
        '<definedName name="_xlnm.Print_Titles" localSheetId="0">\'GRAL.\'!$1:$8</definedName>')
    workbook = workbook.replace('</definedNames>', additions + '</definedNames>')
    contents['xl/workbook.xml'] = (workbook_item, workbook.encode('utf-8'))
    # La imagen fuente es nítida pero el anclaje original la estira en alto.
    # Mantener esquina superior y ancho; recuperar su proporción real, sin
    # modificar píxeles, letras, colores ni posición horizontal.
    drawing_item, drawing_xml = contents['xl/drawings/drawing1.xml']
    drawing = drawing_xml.decode('utf-8')
    extent = re.search(r'<a:ext\s+cx="(\d+)"\s+cy="(\d+)"', drawing)
    if extent:
        from PIL import Image
        with Image.open(BytesIO(contents['xl/media/image1.jpeg'][1])) as image:
            width, height = image.size
        natural_height = round(int(extent.group(1)) * height / width)
        delta = natural_height - int(extent.group(2))
        drawing = drawing[:extent.start(2)] + str(natural_height) + drawing[extent.end(2):]
        end_anchor = re.search(r'<xdr:to>.*?<xdr:rowOff>(\d+)</xdr:rowOff>', drawing, re.S)
        drawing = drawing[:end_anchor.start(1)] + str(int(end_anchor.group(1)) + delta) + drawing[end_anchor.end(1):]
        contents['xl/drawings/drawing1.xml'] = (drawing_item, drawing.encode('utf-8'))

    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as destination:
        for item, payload in contents.values():
            destination.writestr(item, payload)
    output.seek(0)
    return output
