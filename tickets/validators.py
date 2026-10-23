from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTOS_PER_REQUEST = 5
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
PHOTO_ERROR = "Файл не подходит: JPG, PNG или WebP до 5 МБ"


def validate_photo(file):
    """Тип проверяется по содержимому, а не по расширению (раздел 10 ТЗ)."""
    if file.size > MAX_PHOTO_BYTES:
        raise ValidationError(PHOTO_ERROR)
    try:
        file.seek(0)
        with Image.open(file) as image:
            image.verify()
            fmt = image.format
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValidationError(PHOTO_ERROR) from exc
    finally:
        file.seek(0)
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError(PHOTO_ERROR)
    return file


def validate_photos(files, max_count=MAX_PHOTOS_PER_REQUEST):
    files = list(files)
    if len(files) > max_count:
        raise ValidationError(f"Не больше {max_count} фото")
    for file in files:
        validate_photo(file)
    return files
