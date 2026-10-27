from __future__ import annotations

import hashlib
import io
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from memorybook.errors import ValidationError
from memorybook.schemas.catalog_projects import ProjectDocumentSchema

POINTS_PER_INCH = 72
SUPPORTED_PROFILES = {"digital", "print"}
FONT_FILES = {
    "DM Sans": ("DMSans-Regular.ttf", "DMSans-Bold.ttf", "DMSans-Italic.ttf", "DMSans-BoldItalic.ttf"),
    "Georgia": ("Georgia.ttf", "Georgia-Bold.ttf", "Georgia-Italic.ttf", "Georgia-BoldItalic.ttf"),
    "Arial": ("Arial.ttf", "Arial-Bold.ttf", "Arial-Italic.ttf", "Arial-BoldItalic.ttf"),
    "Times New Roman": (
        "TimesNewRoman.ttf",
        "TimesNewRoman-Bold.ttf",
        "TimesNewRoman-Italic.ttf",
        "TimesNewRoman-BoldItalic.ttf",
    ),
}
FONT_FALLBACKS = {
    "DM Sans": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
    "Arial": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
    "Georgia": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    "Times New Roman": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
}


class PdfRenderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        asset_id: str | None = None,
        page_label: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.asset_id = asset_id
        self.page_label = page_label


def render_project_pdf(
    document: object,
    assets: dict[str, bytes],
    profile: str,
    *,
    print_specification: dict[str, Any] | None = None,
    minimum_print_dpi: int = 300,
    configured_font_directory: str | None = None,
    maximum_output_bytes: int = 100 * 1024 * 1024,
) -> tuple[bytes, dict[str, Any]]:
    if profile not in SUPPORTED_PROFILES:
        raise PdfRenderError("unsupported_profile", "Choose the digital or print PDF profile.")
    try:
        source = ProjectDocumentSchema.load(document)
    except ValidationError as failure:
        raise PdfRenderError("invalid_document", str(failure)) from failure

    book_size = source.get("book", {}).get("size")
    if not isinstance(book_size, dict):
        raise PdfRenderError("missing_book_dimensions", "Set the book dimensions before generating a PDF.")
    page_width = _dimension(book_size.get("width"), "width")
    page_height = _dimension(book_size.get("height"), "height")
    ordered_pages = _ordered_pages(source)
    cover_page = next((page for page in ordered_pages if page.get("type") == "cover"), None)
    if cover_page is None:
        raise PdfRenderError("missing_cover", "Add a front cover before generating the PDF.")
    interior_pages = [page for page in ordered_pages if page is not cover_page]
    cover_design = (source.get("cover") or {}).get("design") or {}

    specification = print_specification or {}
    bleed = 0.0
    safe_margin = 0.0
    spine_width = 0.0
    if profile == "print":
        bleed = _bounded_dimension(
            specification.get("bleedInches", cover_design.get("bleedInches", 0.125)),
            "bleed",
            minimum=0.125,
            maximum=0.5,
        )
        safe_margin = _bounded_dimension(
            specification.get("safeMarginInches", 0.25),
            "safe margin",
            minimum=0.0,
            maximum=2.0,
        )
        page_count = len(interior_pages)
        default_spine = max(0.08, math.ceil(page_count / 2) * 0.0025)
        spine_width = _bounded_dimension(
            specification.get("spineWidthInches", cover_design.get("spineWidthInches", default_spine)),
            "spine width",
            minimum=0.0,
            maximum=2.0,
        )
        if spine_width <= 0:
            raise PdfRenderError("invalid_spine_width", "A print cover needs a positive spine width.")
        if minimum_print_dpi < 72 or minimum_print_dpi > 1200:
            raise PdfRenderError("invalid_print_dpi", "The configured minimum print resolution is invalid.")

    font_map = _register_fonts(configured_font_directory)
    output = io.BytesIO()
    pdf_canvas = canvas.Canvas(output, pagesize=(page_width * 72, page_height * 72), pageCompression=1)
    pdf_canvas.setTitle(str(source["metadata"]["title"])[:200])
    pdf_canvas.setAuthor("MemoryBook")
    pdf_canvas.setCreator("MemoryBook PDF Generation Engine")

    context = _RenderContext(
        pdf_canvas=pdf_canvas,
        assets=assets,
        profile=profile,
        page_width=page_width,
        page_height=page_height,
        bleed=bleed,
        safe_margin=safe_margin,
        minimum_print_dpi=minimum_print_dpi,
        font_map=font_map,
    )
    if profile == "digital":
        context.start_page(page_width, page_height, 0)
        context.current_page_label = str(cover_page.get("label") or "Cover")
        front_cover = cover_design.get("front") or {}
        cover_background = (cover_page.get("background") or {}).get("color")
        _draw_cover_face(
            context,
            front_cover,
            source,
            "front",
            background_color=cover_background,
        )
        _draw_page(
            context,
            _cover_page_without_duplicate_face_elements(cover_page, front_cover, source),
            page_width,
            page_height,
            offset_x=0,
            offset_y=0,
            paint_background=False,
        )
        pdf_canvas.showPage()
        for page in interior_pages:
            context.start_page(page_width, page_height, 0)
            context.current_page_label = str(page.get("label") or "Untitled page")
            _draw_page(context, page, page_width, page_height, offset_x=0, offset_y=0)
            pdf_canvas.showPage()
        context.start_page(page_width, page_height, 0)
        _draw_cover_face(context, cover_design.get("back") or {}, source, "back")
        pdf_canvas.showPage()
        expected_pages = len(interior_pages) + 2
    else:
        media_width = (2 * page_width + spine_width + 2 * bleed) * 72
        media_height = (page_height + 2 * bleed) * 72
        context.start_page(2 * page_width + spine_width, page_height, bleed)
        context.current_page_label = "Cover"
        back_x = bleed
        spine_x = bleed + page_width
        front_x = spine_x + spine_width
        _draw_cover_face(context, cover_design.get("back") or {}, source, "back", x_offset=back_x, face_width=page_width)
        _draw_spine(context, cover_design.get("spine") or {}, source, x_offset=spine_x, spine_width=spine_width)
        _draw_cover_face(context, cover_design.get("front") or {}, source, "front", x_offset=front_x, face_width=page_width)
        pdf_canvas.showPage()
        for page in interior_pages:
            context.start_page(page_width, page_height, bleed)
            context.current_page_label = str(page.get("label") or "Untitled page")
            _draw_page(context, page, page_width, page_height, offset_x=bleed, offset_y=bleed)
            pdf_canvas.showPage()
        expected_pages = len(interior_pages) + 1

    pdf_canvas.save()
    raw = output.getvalue()
    if len(raw) > maximum_output_bytes:
        raise PdfRenderError("pdf_too_large", "The generated PDF exceeds the allowed file size.")
    validated, page_sizes = _validate_pdf(raw, expected_pages, profile, bleed)
    metadata = {
        "pageCount": expected_pages,
        "profile": profile,
        "checksumSha256": hashlib.sha256(validated).hexdigest(),
        "byteSize": len(validated),
        "pageSizesPoints": page_sizes,
        "bleedInches": bleed,
        "trimSizeInches": {"width": page_width, "height": page_height},
        "spineWidthInches": spine_width if profile == "print" else None,
        "minimumPrintDpi": minimum_print_dpi if profile == "print" else None,
    }
    return validated, metadata


class _RenderContext:
    def __init__(
        self,
        *,
        pdf_canvas: canvas.Canvas,
        assets: dict[str, bytes],
        profile: str,
        page_width: float,
        page_height: float,
        bleed: float,
        safe_margin: float,
        minimum_print_dpi: int,
        font_map: dict[str, tuple[str, str, str, str]],
    ):
        self.canvas = pdf_canvas
        self.assets = assets
        self.profile = profile
        self.page_width = page_width
        self.page_height = page_height
        self.bleed = bleed
        self.safe_margin = safe_margin
        self.minimum_print_dpi = minimum_print_dpi
        self.font_map = font_map
        self.image_cache: dict[str, Image.Image] = {}
        self.current_page_label = "Cover"

    def start_page(self, width: float, height: float, bleed: float) -> None:
        self.page_width = width
        self.page_height = height
        self.bleed = bleed
        self.canvas.setPageSize(((width + 2 * bleed) * 72, (height + 2 * bleed) * 72))

    def image(self, asset_id: object) -> Image.Image:
        if not isinstance(asset_id, str) or asset_id not in self.assets:
            raise PdfRenderError("missing_asset", "A photo in this design is no longer available.")
        if asset_id not in self.image_cache:
            try:
                image = Image.open(io.BytesIO(self.assets[asset_id]))
                image = ImageOps.exif_transpose(image)
                image.load()
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "transparency" in image.info else "RGB")
                self.image_cache[asset_id] = image
            except Exception as failure:
                raise PdfRenderError("invalid_image", "A photo in this design could not be decoded.") from failure
        return self.image_cache[asset_id]


def _draw_page(
    context: _RenderContext,
    page: dict[str, Any],
    width: float,
    height: float,
    offset_x: float,
    offset_y: float,
    *,
    paint_background: bool = True,
) -> None:
    context.current_page_label = str(page.get("label") or "Untitled page")
    if paint_background:
        page_background = page.get("background")
        background_options = page_background if isinstance(page_background, dict) else {}
        if isinstance(page_background, dict):
            page_background = page_background.get("color")
        background_left = 0 if context.profile == "print" else offset_x
        background_bottom = 0 if context.profile == "print" else offset_y
        _fill_rect(
            context.canvas,
            _color(page_background, "#fffdf9"),
            background_left,
            background_bottom,
            (width + 2 * context.bleed) * 72,
            (height + 2 * context.bleed) * 72,
        )
        border_style = background_options.get("borderStyle", "solid")
        border_color = background_options.get("borderColor")
        if border_style != "none" and isinstance(border_color, str):
            context.canvas.saveState()
            context.canvas.setStrokeColor(_color(border_color, "#20352d"))
            context.canvas.setLineWidth(1.5)
            if border_style == "dashed":
                context.canvas.setDash(5, 3)
            elif border_style == "dotted":
                context.canvas.setDash(1, 2)
            border_offset = context.bleed if context.profile == "print" else 0
            inset_x = width * 0.03
            inset_y = height * 0.03
            context.canvas.rect(
                (offset_x + border_offset + inset_x) * 72,
                (offset_y + border_offset + inset_y) * 72,
                (width - inset_x * 2) * 72,
                (height - inset_y * 2) * 72,
                fill=0,
                stroke=1,
            )
            context.canvas.restoreState()
    for element in page.get("elements", []):
        if not isinstance(element, dict):
            continue
        if context.profile == "print" and element.get("type") == "text":
            _validate_safe_margin(element, width, height, context.safe_margin)
        _draw_element(context, element, width, height, offset_x, offset_y)


def _draw_element(context: _RenderContext, element: dict[str, Any], width: float, height: float, offset_x: float, offset_y: float) -> None:
    try:
        x = float(element.get("x", 0)) * width
        y = float(element.get("y", 0)) * height
        box_width = float(element.get("width", 0.01)) * width
        box_height = float(element.get("height", 0.01)) * height
        rotation = float(element.get("rotation", 0))
        opacity = _opacity(element.get("opacity", 1))
    except (TypeError, ValueError, OverflowError) as failure:
        raise PdfRenderError("invalid_element", "A page element has invalid dimensions or rotation.") from failure
    if not all(math.isfinite(value) for value in (x, y, box_width, box_height, rotation)) or box_width <= 0 or box_height <= 0:
        raise PdfRenderError("invalid_element", "A page element has invalid dimensions or rotation.")

    left = offset_x * 72 + x * 72
    bottom = (offset_y + height - y - box_height) * 72
    box_width *= 72
    box_height *= 72
    pdf_canvas = context.canvas
    pdf_canvas.saveState()
    pdf_canvas.translate(left + box_width / 2, bottom + box_height / 2)
    pdf_canvas.rotate(rotation)
    pdf_canvas.translate(-box_width / 2, -box_height / 2)
    pdf_canvas.setFillAlpha(opacity)
    pdf_canvas.setStrokeAlpha(opacity)
    kind = element.get("type")
    if kind == "image":
        image = context.image(element.get("assetId"))
        _draw_image(
            context,
            image,
            box_width,
            box_height,
            0,
            0,
            fit=element.get("fit", "cover"),
            zoom=element.get("zoom", 1),
            crop_x=element.get("cropX", 0.5),
            crop_y=element.get("cropY", 0.5),
            print_width_inches=box_width / 72,
            print_height_inches=box_height / 72,
            asset_id=element.get("assetId") if isinstance(element.get("assetId"), str) else None,
            border_color=element.get("borderColor"),
            border_width=max(0.0, float(element.get("borderWidth", 0)) * width * 72),
            radius=max(0.0, float(element.get("borderRadius", 0)) * min(box_width, box_height)),
        )
        if element.get("shadow"):
            pass
    elif kind == "text":
        _draw_text(context, element, box_width, box_height, 0, 0)
    elif kind == "shape":
        _draw_shape(context, element, box_width, box_height, 0, 0)
    else:
        raise PdfRenderError("invalid_element", "This design contains an unsupported element.")
    pdf_canvas.restoreState()


def _draw_image(
    context: _RenderContext,
    image: Image.Image,
    frame_width: float,
    frame_height: float,
    left: float,
    bottom: float,
    *,
    fit: object,
    zoom: object = 1,
    crop_x: object = 0.5,
    crop_y: object = 0.5,
    print_width_inches: float | None = None,
    print_height_inches: float | None = None,
    border_color: object = None,
    border_width: float = 0,
    radius: float = 0,
    asset_id: str | None = None,
) -> None:
    try:
        zoom_value = float(zoom)
        crop_x_value = float(crop_x)
        crop_y_value = float(crop_y)
    except (TypeError, ValueError) as failure:
        raise PdfRenderError("invalid_image_crop", "A photo has invalid crop settings.") from failure
    if not 0.1 <= zoom_value <= 10 or not 0 <= crop_x_value <= 1 or not 0 <= crop_y_value <= 1:
        raise PdfRenderError("invalid_image_crop", "A photo has invalid crop settings.")
    if fit not in {"cover", "contain"}:
        raise PdfRenderError("invalid_image_fit", "A photo has an unsupported fit mode.")
    scale = (max if fit == "cover" else min)(frame_width / image.width, frame_height / image.height) * zoom_value
    crop_width_px = min(image.width, frame_width / scale)
    crop_height_px = min(image.height, frame_height / scale)
    crop_left = (image.width - crop_width_px) * crop_x_value
    crop_top = (image.height - crop_height_px) * crop_y_value
    if context.profile == "print":
        placed_width_inches = print_width_inches or frame_width / 72
        placed_height_inches = print_height_inches or frame_height / 72
        if crop_width_px / placed_width_inches < context.minimum_print_dpi or crop_height_px / placed_height_inches < context.minimum_print_dpi:
            raise PdfRenderError(
                "low_resolution_image",
                f"A photo is below the required {context.minimum_print_dpi} DPI for print.",
                asset_id=asset_id,
                page_label=context.current_page_label,
            )
    source_left = max(0, int(math.floor(crop_left)))
    source_top = max(0, int(math.floor(crop_top)))
    source_right = min(image.width, max(source_left + 1, int(math.ceil(crop_left + crop_width_px))))
    source_bottom = min(image.height, max(source_top + 1, int(math.ceil(crop_top + crop_height_px))))
    source_box = (source_left, source_top, source_right, source_bottom)
    rendered = image.crop(source_box)
    if fit == "contain":
        drawn_width = image.width * scale
        drawn_height = image.height * scale
        left += (frame_width - drawn_width) / 2
        bottom += (frame_height - drawn_height) / 2
        frame_width, frame_height = drawn_width, drawn_height
    image_buffer = io.BytesIO()
    rendered.save(image_buffer, format="PNG", optimize=True)
    image_buffer.seek(0)
    if radius > 0:
        path = context.canvas.beginPath()
        path.roundRect(left, bottom, frame_width, frame_height, min(radius, frame_width / 2, frame_height / 2))
        context.canvas.clipPath(path, stroke=0, fill=0)
    context.canvas.drawImage(
        ImageReader(image_buffer),
        left,
        bottom,
        width=frame_width if fit == "cover" else rendered.width * scale,
        height=frame_height if fit == "cover" else rendered.height * scale,
        mask="auto",
    )
    if border_width > 0 and border_color:
        context.canvas.setStrokeColor(_color(border_color, "#ffffff"))
        context.canvas.setLineWidth(border_width)
        context.canvas.roundRect(left, bottom, frame_width, frame_height, min(radius, frame_width / 2, frame_height / 2), fill=0, stroke=1)


def _draw_text(context: _RenderContext, element: dict[str, Any], width: float, height: float, left: float, bottom: float) -> None:
    text = element.get("text", "")
    if not isinstance(text, str) or not text:
        return
    font_family = element.get("fontFamily", "DM Sans")
    variant = 1 if str(element.get("fontWeight", "400")).lower() in {"bold", "600", "700", "800", "900"} else 0
    italic = bool(element.get("italic"))
    font_index = 3 if variant and italic else 2 if italic else variant
    font_name = context.font_map.get(str(font_family), FONT_FALLBACKS["DM Sans"])[font_index]
    try:
        font_size = float(element.get("fontSize", 0.03)) * context.page_height * 72
        line_height = float(element.get("lineHeight", 1.2))
        letter_spacing = float(element.get("letterSpacing", 0)) * context.page_width * 72
    except (TypeError, ValueError) as failure:
        raise PdfRenderError("invalid_text_style", "Text has invalid typography settings.") from failure
    if not math.isfinite(font_size) or not 0.1 <= font_size <= 240 or not 0.5 <= line_height <= 4:
        raise PdfRenderError("invalid_text_style", "Text has invalid typography settings.")
    horizontal_inset = min(8.0, width * 0.08)
    text_width = max(1, width - horizontal_inset * 2)
    lines = _wrap_text(text, font_name, font_size, text_width, letter_spacing)
    leading = font_size * line_height
    while len(lines) * leading > height and font_size > 6:
        font_size *= 0.9
        leading = font_size * line_height
        lines = _wrap_text(text, font_name, font_size, text_width, letter_spacing)
    if len(lines) * leading > height + 0.5:
        raise PdfRenderError("text_overflow", "Text does not fit inside its saved text frame.")

    background = element.get("backgroundColor", "transparent")
    if background and background != "transparent":
        context.canvas.setFillColor(_color(background, "#fffdf9"))
        context.canvas.rect(left, bottom, width, height, fill=1, stroke=0)
    context.canvas.setFillColor(_color(element.get("color"), "#1d2824"))
    alignment = element.get("alignment", "left")
    if alignment not in {"left", "center", "right", "justify"}:
        alignment = "left"
    top = bottom + height - max(font_size, (height - len(lines) * leading) / 2)
    underline = bool(element.get("underline"))
    for line in lines:
        line_width = pdfmetrics.stringWidth(line, font_name, font_size) + max(0, len(line) - 1) * letter_spacing
        if alignment == "center":
            line_x = left + (width - line_width) / 2
        elif alignment == "right":
            line_x = left + width - horizontal_inset - line_width
        else:
            line_x = left + horizontal_inset
        baseline = top
        text_object = context.canvas.beginText(line_x, baseline)
        text_object.setFont(font_name, font_size)
        text_object.setCharSpace(letter_spacing)
        text_object.textLine(line)
        context.canvas.drawText(text_object)
        if underline:
            context.canvas.setLineWidth(max(0.5, font_size / 18))
            context.canvas.line(line_x, baseline - font_size * 0.12, line_x + line_width, baseline - font_size * 0.12)
        top -= leading


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float, letter_spacing: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            measured = pdfmetrics.stringWidth(candidate, font_name, font_size) + max(0, len(candidate) - 1) * letter_spacing
            if current and measured > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def _draw_shape(context: _RenderContext, element: dict[str, Any], width: float, height: float, left: float, bottom: float) -> None:
    shape = element.get("shape", "rectangle")
    if shape == "photo-placeholder":
        context.canvas.saveState()
        context.canvas.setFillColor(_color(element.get("fill"), "#edf0eb"))
        context.canvas.setStrokeColor(_color(element.get("stroke"), "#9ba99f"))
        context.canvas.setLineWidth(max(0.75, float(element.get("strokeWidth", 0.001)) * context.page_width * 72))
        context.canvas.setDash(4, 3)
        context.canvas.rect(left, bottom, width, height, fill=1, stroke=1)
        context.canvas.restoreState()
        return
    if shape not in {"rectangle", "circle"}:
        raise PdfRenderError("invalid_shape", "This design contains an unsupported shape.")
    fill = element.get("fill", "#dce8e1")
    stroke = element.get("stroke")
    stroke_width = max(0.0, float(element.get("strokeWidth", 0)) * context.page_width * 72)
    context.canvas.setFillColor(_color(fill, "#dce8e1"))
    if stroke:
        context.canvas.setStrokeColor(_color(stroke, "#17483e"))
        context.canvas.setLineWidth(stroke_width)
    if shape == "circle":
        context.canvas.ellipse(left, bottom, left + width, bottom + height, fill=1, stroke=1 if stroke_width else 0)
    else:
        radius = max(0.0, float(element.get("rx", 0)) * min(width, height))
        context.canvas.roundRect(left, bottom, width, height, min(radius, width / 2, height / 2), fill=1, stroke=1 if stroke_width else 0)


def _draw_cover_face(
    context: _RenderContext,
    face: dict[str, Any],
    document: dict[str, Any],
    side: str,
    *,
    x_offset: float = 0,
    face_width: float | None = None,
    background_color: object | None = None,
) -> None:
    width, height = face_width or context.page_width, context.page_height
    bleed = context.bleed
    left = x_offset * 72
    bottom = bleed * 72
    if context.profile == "digital":
        background_left = left
        background_width = width
        background_y = bottom
        background_height = height
    else:
        background_left = left - bleed * 72 if side == "back" else left
        background_width = width + bleed
        background_y = 0
        background_height = height + 2 * bleed
    _fill_rect(
        context.canvas,
        _color(
            background_color if isinstance(background_color, str) else face.get("backgroundColor"),
            "#e8ece5" if side == "front" else "#f4eee5",
        ),
        background_left,
        background_y,
        background_width * 72,
        background_height * 72,
    )
    if side == "front" and face.get("photoAssetId"):
        image = context.image(face["photoAssetId"])
        photo_left = left if context.profile == "digital" or side == "front" else left - bleed * 72
        photo_bottom = bottom if context.profile == "digital" else 0
        photo_width = width if context.profile == "digital" else width + bleed
        photo_height = height if context.profile == "digital" else height + 2 * bleed
        _draw_image(
            context,
            image,
            photo_width * 72,
            photo_height * 72,
            photo_left,
            photo_bottom,
            fit="cover",
            print_width_inches=photo_width,
            print_height_inches=photo_height,
            asset_id=face.get("photoAssetId") if isinstance(face.get("photoAssetId"), str) else None,
        )
    title = face.get("title") or document["metadata"]["title"]
    if not isinstance(title, str):
        title = str(document["metadata"]["title"])
    text_color = _color(face.get("textColor"), "#20352d")
    font_family = face.get("fontFamily", "Georgia")
    font_name = context.font_map.get(str(font_family), FONT_FALLBACKS["Georgia"])[0]
    title_size = min(36, width * 3.6)
    text_width = width * 72 * 0.78
    lines = _wrap_text(title, font_name, title_size, text_width, 0)
    subtitle = face.get("subtitle") if side == "front" else face.get("description")
    layout = face.get("layout", "center")
    if layout == "lower":
        title_y = bottom + height * 72 * 0.23
    elif layout == "minimal":
        title_y = bottom + height * 72 * 0.14
    else:
        title_y = bottom + height * 72 * 0.45
    context.canvas.saveState()
    context.canvas.setFillColor(text_color)
    for index, line in enumerate(lines[:5]):
        line_width = pdfmetrics.stringWidth(line, font_name, title_size)
        context.canvas.setFont(font_name, title_size)
        context.canvas.drawString(left + (width * 72 - line_width) / 2, title_y - index * title_size * 1.2, line)
    if isinstance(subtitle, str) and subtitle:
        subtitle_font = context.font_map.get(str(font_family), FONT_FALLBACKS["Georgia"])[0]
        subtitle_size = min(14, width * 1.4)
        subtitle_lines = _wrap_text(subtitle, subtitle_font, subtitle_size, text_width, 0)
        sub_y = title_y - len(lines[:5]) * title_size * 1.2 - subtitle_size
        if layout == "minimal":
            sub_y = title_y - (len(lines[:5]) + 1) * title_size * 1.2
        context.canvas.setFont(subtitle_font, subtitle_size)
        for index, line in enumerate(subtitle_lines[:6]):
            line_width = pdfmetrics.stringWidth(line, subtitle_font, subtitle_size)
            context.canvas.drawString(left + (width * 72 - line_width) / 2, sub_y - index * subtitle_size * 1.3, line)
    context.canvas.restoreState()


def _cover_page_without_duplicate_face_elements(
    cover_page: dict[str, Any],
    front_cover: dict[str, Any],
    document: dict[str, Any],
) -> dict[str, Any]:
    title = front_cover.get("title") or document["metadata"]["title"]
    photo_asset_id = front_cover.get("photoAssetId")
    elements = [
        element
        for element in cover_page.get("elements", [])
        if not (
            (
                element.get("type") == "text"
                and element.get("text") == title
            )
            or (
                element.get("type") == "image"
                and photo_asset_id is not None
                and element.get("assetId") == photo_asset_id
            )
        )
    ]
    return {**cover_page, "elements": elements}


def _draw_spine(
    context: _RenderContext,
    face: dict[str, Any],
    document: dict[str, Any],
    *,
    x_offset: float,
    spine_width: float,
) -> None:
    color = _color(face.get("backgroundColor"), "#e8ece5")
    _fill_rect(context.canvas, color, x_offset * 72, 0, spine_width * 72, (context.page_height + 2 * context.bleed) * 72)
    title = face.get("title") or document["metadata"]["title"]
    family = face.get("fontFamily", "Georgia")
    font_name = context.font_map.get(str(family), FONT_FALLBACKS["Georgia"])[0]
    context.canvas.saveState()
    context.canvas.translate((x_offset + spine_width / 2) * 72, (context.bleed + context.page_height / 2) * 72)
    context.canvas.rotate(90)
    context.canvas.setFillColor(_color(face.get("textColor"), "#20352d"))
    context.canvas.setFont(font_name, 10)
    context.canvas.drawCentredString(0, 0, str(title)[:80])
    context.canvas.restoreState()


def _register_fonts(font_directory: str | None) -> dict[str, tuple[str, str, str, str]]:
    fonts = dict(FONT_FALLBACKS)
    if not font_directory:
        return fonts
    directory = Path(font_directory).expanduser().resolve()
    if not directory.is_dir():
        raise PdfRenderError("font_directory_unavailable", "The configured licensed font directory is unavailable.", retryable=True)
    for family, filenames in FONT_FILES.items():
        registered = []
        try:
            for index, filename in enumerate(filenames):
                path = directory / filename
                if not path.is_file():
                    raise FileNotFoundError(filename)
                name = f"MemoryBook_{re.sub(r'[^A-Za-z0-9]', '', family)}_{index}"
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                registered.append(name)
        except (OSError, ValueError):
            continue
        if len(registered) == 4:
            fonts[family] = tuple(registered)
    return fonts


def _validate_pdf(raw: bytes, expected_pages: int, profile: str, bleed: float) -> tuple[bytes, list[dict[str, float]]]:
    if not raw.startswith(b"%PDF-"):
        raise PdfRenderError("invalid_pdf", "PDF validation failed.")
    try:
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted or len(reader.pages) != expected_pages or expected_pages < 1:
            raise PdfRenderError("invalid_pdf", "PDF validation failed.")
        writer = PdfWriter()
        page_sizes = []
        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
                raise PdfRenderError("invalid_pdf", "PDF validation found invalid page dimensions.")
            if profile == "print":
                bleed_points = bleed * 72
                media = page.mediabox
                page.cropbox = RectangleObject((float(media.left), float(media.bottom), float(media.right), float(media.top)))
                page.bleedbox = RectangleObject((float(media.left), float(media.bottom), float(media.right), float(media.top)))
                page.trimbox = RectangleObject((
                    float(media.left) + bleed_points,
                    float(media.bottom) + bleed_points,
                    float(media.right) - bleed_points,
                    float(media.top) - bleed_points,
                ))
            page_sizes.append({"width": round(width, 2), "height": round(height, 2)})
            writer.add_page(page)
        writer.add_metadata({
            "/Title": str(reader.metadata.title or "MemoryBook")[:200],
            "/Creator": "MemoryBook PDF Generation Engine",
            "/Keywords": f"MemoryBook,{profile},version-1",
        })
        validated = io.BytesIO()
        writer.write(validated)
        final_bytes = validated.getvalue()
        check = PdfReader(io.BytesIO(final_bytes), strict=True)
        if len(check.pages) != expected_pages or not final_bytes.endswith(b"%%EOF\n"):
            raise PdfRenderError("invalid_pdf", "PDF validation failed after production metadata was applied.")
        return final_bytes, page_sizes
    except PdfRenderError:
        raise
    except Exception as failure:
        raise PdfRenderError("invalid_pdf", "PDF validation failed.") from failure


def _ordered_pages(document: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {page["id"]: page for page in document["pages"]}
    return [by_id[page_id] for page_id in document["pageOrder"]]


def _dimension(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as failure:
        raise PdfRenderError("missing_book_dimensions", f"The book {label} must be provided in inches.") from failure
    if not math.isfinite(result) or not 2 <= result <= 20:
        raise PdfRenderError("invalid_book_dimensions", f"The book {label} must be between 2 and 20 inches.")
    return result


def _bounded_dimension(value: object, label: str, *, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as failure:
        raise PdfRenderError("invalid_print_specification", f"The print {label} is invalid.") from failure
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise PdfRenderError("invalid_print_specification", f"The print {label} is outside the supported range.")
    return result


def _validate_safe_margin(element: dict[str, Any], width: float, height: float, margin: float) -> None:
    try:
        x = float(element.get("x", 0)) * width
        y = float(element.get("y", 0)) * height
        w = float(element.get("width", 0)) * width
        h = float(element.get("height", 0)) * height
    except (TypeError, ValueError) as failure:
        raise PdfRenderError("invalid_element", "Text position is invalid for print.") from failure
    if x < margin or y < margin or x + w > width - margin or y + h > height - margin:
        raise PdfRenderError("unsafe_text_position", "Move text inside the print safe margin before generating this file.")


def _opacity(value: object) -> float:
    try:
        opacity = float(value)
    except (TypeError, ValueError) as failure:
        raise PdfRenderError("invalid_opacity", "An element has invalid opacity.") from failure
    if not math.isfinite(opacity) or not 0 <= opacity <= 1:
        raise PdfRenderError("invalid_opacity", "An element has invalid opacity.")
    return opacity


def _color(value: object, fallback: str) -> HexColor:
    color = value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback
    return HexColor(color)


def _fill_rect(pdf_canvas: canvas.Canvas, color: HexColor, x: float, y: float, width: float, height: float) -> None:
    pdf_canvas.saveState()
    pdf_canvas.setFillColor(color)
    pdf_canvas.rect(x, y, width, height, fill=1, stroke=0)
    pdf_canvas.restoreState()
