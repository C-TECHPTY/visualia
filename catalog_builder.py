"""Local catalog-page composition and persistent catalog templates."""
from __future__ import annotations

import json
import os
import tempfile
from io import BytesIO
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from catalog_core import ProductJob, discover_images, load_product_source
from product_sources import header, product_key


PAGE_SIZE = (1240, 1754)
DEFAULT_CATALOG_TEMPLATE = {
    "name": "Animal Planet",
    "title": "Accesorios para Mascotas",
    "subtitle": "Calidad, bienestar y felicidad en cada detalle",
    "footer": "Mascotas más felices · Animal Planet Pets",
    "columns": 2,
    "rows": 3,
    "display_fields": [
        "DESCRIPCION", "Cub.", "MARCA", "DISPONIBLE", "Precio",
        "EMPAQUE", "UM", "CTN", "CBARRA",
    ],
    "primary_color": "#0867B2",
    "background_color": "#FFFFFF",
    "logo_path": "",
    "header_image_path": "",
}


@dataclass(frozen=True)
class CatalogTemplate:
    name: str
    title: str
    subtitle: str
    footer: str
    columns: int = 2
    rows: int = 3
    primary_color: str = "#0867B2"
    background_color: str = "#FFFFFF"
    logo_path: str = ""
    header_image_path: str = ""
    display_fields: tuple[str, ...] = (
        "DESCRIPCION", "Cub.", "MARCA", "DISPONIBLE", "Precio",
        "EMPAQUE", "UM", "CTN", "CBARRA",
    )

    @classmethod
    def from_dict(cls, data: dict) -> "CatalogTemplate":
        values = dict(data)
        values["display_fields"] = tuple(values.get("display_fields", cls.display_fields))
        template = cls(**values)
        validate_template(template)
        return template


@dataclass(frozen=True)
class CatalogProduct:
    job: ProductJob
    name: str
    item: str
    description: str
    price: str
    details: tuple[tuple[str, str], ...] = ()


def validate_template(template: CatalogTemplate) -> None:
    for label, value in (("nombre", template.name), ("título", template.title)):
        if not value.strip():
            raise ValueError(f"El {label} de la plantilla no puede estar vacío.")
    if not (1 <= template.columns <= 3 and 1 <= template.rows <= 4):
        raise ValueError("La plantilla debe tener entre 1 y 3 columnas y entre 1 y 4 filas.")
    if not template.display_fields or any(not field.strip() for field in template.display_fields):
        raise ValueError("Indica al menos una columna para mostrar en las fichas del catálogo.")
    for label, value in (("principal", template.primary_color), ("fondo", template.background_color)):
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError(f"El color {label} debe tener formato hexadecimal, por ejemplo #0867B2.")
        try:
            int(value[1:], 16)
        except ValueError as exc:
            raise ValueError(f"El color {label} debe tener formato hexadecimal, por ejemplo #0867B2.") from exc
    if template.logo_path and not Path(template.logo_path).is_file():
        raise ValueError("El logo guardado en la plantilla no existe. Selecciona uno nuevo o quítalo.")
    if template.header_image_path and not Path(template.header_image_path).is_file():
        raise ValueError("La imagen de encabezado guardada en la plantilla no existe. Selecciona una nueva o quítala.")


def load_catalog_templates(path: Path) -> dict[str, CatalogTemplate]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("El archivo debe contener una lista de plantillas.")
        templates = {name: CatalogTemplate.from_dict(value) for name, value in raw.items()}
        if any(name != template.name for name, template in templates.items()):
            raise ValueError("El nombre de cada plantilla debe coincidir con su nombre guardado.")
        return templates
    except (ValueError, TypeError, OSError) as exc:
        raise ValueError(f"No se pudieron leer las plantillas de catálogo: {exc}") from exc


def save_catalog_templates(path: Path, templates: dict[str, CatalogTemplate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({name: asdict(value) for name, value in templates.items()}, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def build_catalog_products(
    folder: Path,
    metadata_path: Path | None = None,
    metadata_options: dict | None = None,
) -> list[CatalogProduct]:
    if not folder.is_dir():
        raise ValueError("Selecciona una carpeta válida con las imágenes de los productos.")
    images = discover_images(folder)
    if not images:
        raise ValueError("No se encontraron imágenes de productos en la carpeta seleccionada.")
    metadata = load_product_source(metadata_path, **(metadata_options or {}))
    products: list[CatalogProduct] = []
    seen: set[str] = set()
    for image in images:
        key = product_key(image.stem)
        if key in seen:
            raise ValueError(
                f"Hay más de una imagen para el mismo producto ({image.stem}). "
                "Deja una imagen por ITEM/SKU o prepara primero las imágenes con el modo Por prefijo/SKU."
            )
        seen.add(key)
        row = metadata.get(key, {})
        description = _metadata_value(row, "descripcion", "descripción", "caracteristicas", "características")
        name = _metadata_value(row, "producto", "nombre", "name") or description or image.stem.replace("_", " ")
        item = _metadata_value(row, "item", "sku", "codigo", "archivo", "file", "producto id") or image.stem
        price = _metadata_value(row, "precio", "price", "pvp", "precio venta", "precio de venta")
        details = tuple(row.items())
        products.append(CatalogProduct(ProductJob(image.stem, [image], row), name, item, description, price, details))
    return products


def _metadata_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(header(name), "").strip()
        if value:
            return value
    return ""


def product_detail_lines(product: CatalogProduct, template: CatalogTemplate) -> list[str]:
    lines = [f"DESCRIPCION: {product.description}"] if product.description and product.name != product.description else []
    values = {header(label): value for label, value in product.details}
    price_fields = {"precio", "price", "pvp", "precio venta", "precio de venta"}
    for field in template.display_fields:
        normalized = header(field)
        value = values.get(normalized, "")
        if value and normalized not in {"descripcion", *price_fields}:
            lines.append(f"{field.strip()}: {value}")
    return lines


def product_title(product: CatalogProduct) -> str:
    if product.description and product.name == product.description:
        return f"DESCRIPCION: {product.name}"
    return product.name


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\segoeui.ttf")
        if bold else (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf")
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int, lines: int) -> list[str]:
    result: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > width:
            result.append(current)
            current = word
            if len(result) == lines:
                break
        else:
            current = candidate
    if current and len(result) < lines:
        result.append(current)
    if len(result) == lines and " ".join(result).strip() != text.strip() and result:
        last = result[-1]
        while last and draw.textlength(last + "...", font=font) > width:
            last = last[:-1]
        result[-1] = last.rstrip() + "..."
    return result


def render_catalog_page(
    products: Iterable[CatalogProduct],
    template: CatalogTemplate,
    page_number: int,
    page_count: int,
) -> Image.Image:
    validate_template(template)
    page_products = list(products)
    capacity = template.columns * template.rows
    if not page_products or len(page_products) > capacity:
        raise ValueError(f"Una página debe contener entre 1 y {capacity} productos.")

    width, height = PAGE_SIZE
    image = Image.new("RGB", PAGE_SIZE, template.background_color)
    draw = ImageDraw.Draw(image)
    margin = 44
    header_height = 210
    draw.rectangle((0, 0, width, 16), fill=template.primary_color)

    logo_width = 170 if template.logo_path else 0
    if template.logo_path:
        with Image.open(template.logo_path) as source:
            logo = ImageOps.contain(ImageOps.exif_transpose(source).convert("RGBA"), (logo_width, 125))
        image.paste(logo, (margin, 42), logo)

    text_x = margin + (logo_width + 24 if template.logo_path else 0)
    title_font = _font(42, True)
    subtitle_font = _font(22)
    draw.text((text_x, 54), template.title, fill=template.primary_color, font=title_font)
    draw.text((text_x, 112), template.subtitle, fill="#505B66", font=subtitle_font)
    if template.header_image_path:
        with Image.open(template.header_image_path) as source:
            banner = ImageOps.fit(
                ImageOps.exif_transpose(source).convert("RGB"),
                (300, 160),
                Image.Resampling.LANCZOS,
            )
        image.paste(banner, (width - margin - banner.width, 38))
    draw.text((width - margin, 28), f"PÁG. {page_number} / {page_count}", anchor="ra",
              fill=template.primary_color, font=_font(17, True))
    draw.line((margin, header_height, width - margin, header_height), fill=template.primary_color, width=3)

    footer_height = 66
    grid_top = header_height + 24
    grid_bottom = height - footer_height - 24
    gap = 18
    cell_width = (width - 2 * margin - gap * (template.columns - 1)) // template.columns
    cell_height = (grid_bottom - grid_top - gap * (template.rows - 1)) // template.rows

    for index, product in enumerate(page_products):
        row_index, column_index = divmod(index, template.columns)
        left = margin + column_index * (cell_width + gap)
        top = grid_top + row_index * (cell_height + gap)
        right, bottom = left + cell_width, top + cell_height
        draw.rounded_rectangle((left, top, right, bottom), radius=16, outline="#D5DDE5", width=2, fill="#FFFFFF")
        image_box = (left + 14, top + 12, right - 14, top + int(cell_height * 0.52))
        with Image.open(product.job.primary_image) as source:
            product_image = ImageOps.contain(
                ImageOps.exif_transpose(source).convert("RGB"),
                (image_box[2] - image_box[0], image_box[3] - image_box[1]),
                Image.Resampling.LANCZOS,
            )
        image_x = image_box[0] + (image_box[2] - image_box[0] - product_image.width) // 2
        image_y = image_box[1] + (image_box[3] - image_box[1] - product_image.height) // 2
        image.paste(product_image, (image_x, image_y))

        text_left = left + 18
        text_right = right - 18
        text_top = image_box[3] + 8
        name_font = _font(21, True)
        item_font = _font(16)
        description_font = _font(16)
        for line in _fit_text(draw, product_title(product), name_font, cell_width - 36, 2):
            draw.text((text_left, text_top), line, fill="#12385B", font=name_font)
            text_top += 26
        draw.text((text_left, text_top + 2), f"ITEM: {product.item}", fill="#4B5563", font=item_font)
        text_top += 28

        price_box_width = 0
        if product.price:
            price_font = _font(20, True)
            price_text = f"PRECIO: {product.price}"
            price_box_width = int(draw.textlength(price_text, font=price_font)) + 30
            price_box = (text_right - price_box_width, bottom - 50, text_right, bottom - 14)
            draw.rounded_rectangle(price_box, radius=12, fill=template.primary_color)
            draw.text(((price_box[0] + price_box[2]) // 2, price_box[1] + 18),
                      price_text, anchor="mm", fill="#FFFFFF", font=price_font)
        details = product_detail_lines(product, template)
        details_text = "   |   ".join(details)
        available_height = max(1, bottom - 12 - text_top)
        detail_font_size = min(16, max(10, available_height // 20))
        detail_font = _font(detail_font_size)
        detail_lines = _fit_text(
            draw, details_text, detail_font, cell_width - 36, max(1, available_height // (detail_font_size + 4))
        )
        for line in detail_lines:
            draw.text((text_left, text_top), line, fill="#4B5563", font=detail_font)
            text_top += detail_font_size + 4

    footer_y = height - footer_height
    draw.rectangle((0, footer_y, width, height), fill=template.primary_color)
    draw.text((margin, footer_y + 22), template.footer, fill="#FFFFFF", font=_font(19, True))
    return image


def generate_catalog_pdf(
    products: list[CatalogProduct],
    template: CatalogTemplate,
    output_path: Path,
) -> int:
    validate_template(template)
    if not products:
        raise ValueError("No hay productos para exportar.")
    capacity = template.columns * template.rows
    page_count = (len(products) + capacity - 1) // capacity
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", dir=output_path.parent, delete=False) as handle:
            temporary = Path(handle.name)
        document = canvas.Canvas(str(temporary), pagesize=A4, pageCompression=1)
        page_width, page_height = A4
        for index in range(page_count):
            page_products = products[index * capacity:(index + 1) * capacity]
            rendered = render_catalog_page(page_products, template, index + 1, page_count)
            buffer = BytesIO()
            try:
                rendered.save(buffer, format="PNG")
                buffer.seek(0)
                document.drawImage(
                    ImageReader(buffer),
                    0,
                    0,
                    width=page_width,
                    height=page_height,
                    preserveAspectRatio=False,
                )
                document.showPage()
            finally:
                buffer.close()
                rendered.close()
        document.save()
        if temporary.stat().st_size == 0:
            raise OSError("El archivo PDF generado está vacío.")
        os.replace(temporary, output_path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return page_count
