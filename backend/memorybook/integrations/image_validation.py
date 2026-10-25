from __future__ import annotations

import warnings
from io import BytesIO
from typing import BinaryIO

from PIL import Image, ImageOps, UnidentifiedImageError

from memorybook.errors import ValidationError

IMAGE_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
MAX_IMAGE_PIXELS = 40_000_000


def validate_and_sanitize_image(stream: BinaryIO, mime_type: str) -> tuple[BytesIO, int, int]:
    expected_format = IMAGE_FORMATS.get(mime_type)
    if expected_format is None:
        raise ValidationError("Unsupported image type.", {"mimeType": "unsupported"})

    try:
        stream.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as source:
                if source.format != expected_format:
                    raise ValidationError(
                        "The image contents do not match the selected file type.",
                        {"file": "invalid_content"},
                    )
                width, height = source.size
                if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                    raise ValidationError(
                        "Image dimensions exceed the supported pixel limit.",
                        {"file": "dimensions_too_large"},
                    )
                source.verify()

            stream.seek(0)
            with Image.open(stream) as source:
                source.load()
                image = ImageOps.exif_transpose(source)
                output = BytesIO()
                if expected_format == "JPEG":
                    if image.mode not in {"L", "RGB"}:
                        image = image.convert("RGB")
                    image.save(output, format=expected_format, quality=95, optimize=True)
                elif expected_format == "WEBP":
                    image.save(output, format=expected_format, quality=95, method=4)
                else:
                    image.save(output, format=expected_format, optimize=True)
                output_size = output.tell()
                if output_size <= 0 or output_size > 15 * 1024 * 1024:
                    raise ValidationError("Processed image must not exceed 15 MB.", {"size": "invalid"})
                output.seek(0)
                return output, image.width, image.height
    except ValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as failure:
        raise ValidationError(
            "The image is corrupted, unsupported, or unsafe to decode.",
            {"file": "invalid_content"},
        ) from failure
    finally:
        stream.seek(0)
