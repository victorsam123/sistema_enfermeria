"""Rellena la plantilla oficial sin reconstruir membretes, textos ni firma."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from flask import current_app

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
MONTHS = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre')


def normalized_reason(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value or '') if not unicodedata.combining(c)).casefold()


def excluded_reason(value):
    reason = normalized_reason(value)
    return bool(re.search(r'capacit|llegad\w*\s+tard|tardanza|(?:no|sin|falta\s+de|falta)\s+(?:marc|registr\w*\s+(?:la\s+)?entrada)|omisi\w*\s+(?:de\s+)?marc', reason))


def positive_reason(value):
    return bool(re.search(r'compensatori|compensacion|horas?\s+extra|servicios?\s+extra', normalized_reason(value))) and not excluded_reason(value)


def _write_text(element, value):
    texts = element.findall('.//w:t', NS)
    if texts:
        texts[0].text = value
        for node in texts[1:]:
            node.text = ''
    else:
        paragraph = element.find('w:p', NS)
        if paragraph is None:
            paragraph = ET.SubElement(element, f'{{{W}}}p')
        run = ET.SubElement(paragraph, f'{{{W}}}r')
        properties = paragraph.find('w:pPr/w:rPr', NS)
        if properties is not None:
            run.append(deepcopy(properties))
        ET.SubElement(run, f'{{{W}}}t').text = value


def render_compensatory_note(rows, number, issued_on, template_path=None):
    if not rows:
        raise ValueError('Selecciona al menos un justificativo para generar la nota.')
    template = Path(template_path) if template_path else Path(current_app.root_path) / 'assets/nota_dia_compensatorio.docx'
    with ZipFile(template) as archive:
        parts = {info.filename: (info, archive.read(info.filename)) for info in archive.infolist()}
    info, original = parts['word/document.xml']
    for _, (prefix, uri) in ET.iterparse(BytesIO(original), events=('start-ns',)):
        if not re.fullmatch(r'ns\d+', prefix):
            ET.register_namespace(prefix, uri)
    xml = original.decode('utf-8')
    # Solo los dos párrafos editables; el resto del XML de cuerpo se conserva.
    patterns = list(re.finditer(r'<w:p(?:\s[^>]*)?>.*?</w:p>', xml, re.S))
    replacements = []
    for match, value in zip(patterns[:2], (f'NOTA N.ª  {number}',
            f'Ciudad del Este, {issued_on.day} {MONTHS[issued_on.month - 1]} de {issued_on.year}')):
        # Los fragmentos heredan los namespaces de la raíz original.
        root_start = re.search(r'<w:document\b[^>]*>', xml).group()
        wrapper = root_start + match.group() + '</w:document>'
        paragraph = ET.fromstring(wrapper)[0]
        _write_text(paragraph, value)
        replacements.append((match.start(), match.end(), ET.tostring(paragraph, encoding='unicode')))
    for start, end, value in reversed(replacements):
        xml = xml[:start] + value + xml[end:]
    match = re.search(r'<w:tbl(?:\s[^>]*)?>.*?</w:tbl>', xml, re.S)
    root_start = re.search(r'<w:document\b[^>]*>', xml).group()
    table = ET.fromstring(root_start + match.group() + '</w:document>')[0]
    stored_rows = table.findall('w:tr', NS)
    header, model = stored_rows[0], stored_rows[1]
    border_model = model.find('w:tc/w:tcPr/w:tcBorders', NS)
    header_properties = header.find('w:trPr', NS)
    if header_properties is None:
        header_properties = ET.Element(f'{{{W}}}trPr')
        header.insert(0, header_properties)
    if header_properties.find('w:tblHeader', NS) is None:
        ET.SubElement(header_properties, f'{{{W}}}tblHeader')
    for row in stored_rows[1:]:
        table.remove(row)
    for values in rows:
        row = deepcopy(model)
        props = row.find('w:trPr', NS)
        if props is None:
            props = ET.Element(f'{{{W}}}trPr')
            row.insert(0, props)
        ET.SubElement(props, f'{{{W}}}cantSplit')
        height = props.find('w:trHeight', NS)
        if height is not None:
            height.set(f'{{{W}}}hRule', 'atLeast')
        for cell, value in zip(row.findall('w:tc', NS), [values[k] for k in
                ('name', 'cedula', 'worked_dates', 'worked_hours', 'service', 'free_dates', 'free_hours')]):
            borders = cell.find('w:tcPr/w:tcBorders', NS)
            if borders is not None and border_model is not None:
                for border in borders:
                    if border.get(f'{{{W}}}val') == 'nil':
                        reference = border_model.find(border.tag)
                        if reference is not None:
                            border.attrib.clear()
                            border.attrib.update(reference.attrib)
            no_wrap = cell.find('w:tcPr/w:noWrap', NS)
            if no_wrap is not None:
                cell.find('w:tcPr', NS).remove(no_wrap)
            _write_text(cell, str(value))
        table.append(row)
    xml = xml[:match.start()] + ET.tostring(table, encoding='unicode') + xml[match.end():]
    # El ejemplo completado elimina los párrafos vacíos de la plantilla antes
    # de la firma. Se retiran solo los vacíos contiguos, sin tocar la firma.
    closing = xml.find('Se expide la presente nota como documento de respaldo')
    if closing >= 0:
        closing_end = xml.find('</w:p>', closing) + len('</w:p>')
        tail = xml[closing_end:]
        while True:
            blank = re.match(r'\s*(<w:p(?:\s[^>]*)?>.*?</w:p>)', tail, re.S)
            if not blank:
                break
            if any(tag in blank.group(1) for tag in ('<w:drawing', '<w:pict', '<mc:AlternateContent')):
                break
            node = ET.fromstring(root_start + blank.group(1) + '</w:document>')[0]
            if node.findall('.//w:t', NS) or node.findall('.//w:drawing', NS) or node.findall('.//w:pict', NS):
                break
            tail = tail[blank.end():]
        xml = xml[:closing_end] + tail
    parts['word/document.xml'] = (info, xml.encode('utf-8'))
    result = BytesIO()
    with ZipFile(result, 'w') as archive:
        for item, content in parts.values():
            archive.writestr(item, content)
    return result.getvalue()
