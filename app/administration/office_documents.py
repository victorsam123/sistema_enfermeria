"""PDF del archivo oficial real, con motores nativos; nunca una imitación HTML."""
from io import BytesIO
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from threading import Lock
from flask import current_app, send_file

_conversion_lock = Lock()


class OfficeConversionError(ValueError):
    pass


def convert_to_pdf(content, extension):
    if extension not in ('.docx', '.xlsx'):
        raise OfficeConversionError('Formato no permitido para impresión.')
    root = Path(current_app.instance_path) / 'impresion_temporal'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with _conversion_lock, tempfile.TemporaryDirectory(prefix='documento-', dir=root) as folder:
        folder = Path(folder)
        source, target = folder / ('documento' + extension), folder / 'documento.pdf'
        source.write_bytes(content)
        os.chmod(source, 0o600)
        if os.name == 'nt':
            command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(Path(__file__).with_name('office_to_pdf.ps1')),
                '-InputPath', str(source), '-OutputPath', str(target)]
        else:
            executable = shutil.which('libreoffice') or shutil.which('soffice')
            if not executable:
                raise OfficeConversionError('La conversión PDF requiere LibreOffice en el servidor. La descarga del documento original sigue disponible.')
            command = [executable, '-env:UserInstallation=' + (folder / 'perfil').as_uri(),
                '--headless', '--convert-to', 'pdf', '--outdir', str(folder), str(source)]
        try:
            # Office puede heredar los pipes del proceso PowerShell. Si el
            # motor se bloquea, communicate() podría esperar esos pipes aun
            # después del timeout. No se necesita su salida para validar el PDF.
            result = subprocess.run(command, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OfficeConversionError('No se pudo completar la conversión a PDF. Comprueba el motor de impresión y vuelve a intentarlo.') from exc
        if result.returncode or not target.is_file():
            current_app.logger.error('Motor PDF no disponible; código %s', result.returncode)
            raise OfficeConversionError('No se pudo generar el PDF con el motor de Office. En Windows ejecuta el servidor en la sesión que dispone de Word y Excel; en Linux instala LibreOffice.')
        pdf = target.read_bytes()
        if not pdf.startswith(b'%PDF-'):
            raise OfficeConversionError('El motor no devolvió un PDF válido.')
        return pdf


def private_download(content, filename, mimetype, attachment=True):
    response = send_file(BytesIO(content), download_name=filename, mimetype=mimetype,
        as_attachment=attachment, max_age=0)
    response.headers['Cache-Control'] = 'no-store, private, max-age=0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
