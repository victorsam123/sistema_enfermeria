"""Validación por decodificación completa, límites y vistas sin metadatos."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
import warnings
import unicodedata
from PIL import Image, ImageOps, UnidentifiedImageError
from flask import current_app, g
from flask_wtf.file import MultipleFileField
from wtforms.validators import ValidationError
from app.documents.storage import DocumentError

FORMATS = {'JPEG': ('jpg', 'image/jpeg', {'jpg', 'jpeg'}), 'PNG': ('png', 'image/png', {'png'}),
           'WEBP': ('webp', 'image/webp', {'webp'})}


@dataclass(frozen=True)
class Photo:
    name: str
    original: bytes
    extension: str
    mime: str
    digest: str
    preview: bytes


def prepare_photo(upload):
    maximum = current_app.config['DOCUMENT_MAX_BYTES']
    raw = upload.stream.read(maximum + 1)
    if not raw or len(raw) > maximum:
        raise DocumentError(f'Cada fotografía debe contener datos y pesar hasta {maximum // (1024 * 1024)} MB.')
    basename = unicodedata.normalize('NFKC', (upload.filename or '').replace('\\', '/').split('/')[-1])
    name = ''.join(c for c in basename if c.isprintable())[:180] or 'documento'
    extension = PurePath(basename).suffix.lower().lstrip('.')
    if extension not in {'jpg', 'jpeg', 'png', 'webp'}:
        raise DocumentError('Solo se admiten JPG, JPEG, PNG y WEBP. HEIC debe convertirse antes de cargarlo.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as check:
                fmt = check.format
                if fmt not in FORMATS or extension not in FORMATS[fmt][2]:
                    raise DocumentError('El contenido real de la imagen no coincide con un formato permitido.')
                if check.width * check.height > current_app.config['DOCUMENT_MAX_PIXELS']:
                    raise DocumentError('La resolución de la fotografía es demasiado grande.')
                if getattr(check, 'n_frames', 1) != 1:
                    raise DocumentError('Adjunta fotografías estáticas; no se admiten imágenes animadas.')
                check.verify()
            with Image.open(BytesIO(raw)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((current_app.config['DOCUMENT_PREVIEW_EDGE'],) * 2, Image.Resampling.LANCZOS)
                # Quita EXIF, GPS, comentarios y perfiles de las vistas servidas.
                rgb = Image.new('RGB', oriented.size, 'white')
                if 'A' in oriented.getbands():
                    rgb.paste(oriented.convert('RGB'), mask=oriented.getchannel('A'))
                else:
                    rgb.paste(oriented.convert('RGB'))
                output = BytesIO()
                rgb.save(output, 'JPEG', quality=90, optimize=True)
    except DocumentError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise DocumentError('No se pudo verificar la fotografía. El archivo está dañado o no es una imagen admitida.') from exc
    ext, mime, _ = FORMATS[fmt]
    return Photo(name, raw, ext, mime, sha256(raw).hexdigest(), output.getvalue())


def validate_photos(form, field):
    files = [f for f in (field.data or []) if getattr(f, 'filename', '')]
    if len(files) > current_app.config['DOCUMENT_MAX_FILES']:
        raise ValidationError(f"Se permiten hasta {current_app.config['DOCUMENT_MAX_FILES']} fotografías por registro.")
    try:
        field.prepared = [prepare_photo(f) for f in files]
        if len({p.digest for p in field.prepared}) != len(field.prepared):
            raise DocumentError('Hay fotografías repetidas en la selección.')
    except DocumentError as exc:
        raise ValidationError(str(exc)) from exc
    g.document_photos = field.prepared


def photos_field():
    return MultipleFileField('Seleccionar fotografías', validators=[validate_photos])
