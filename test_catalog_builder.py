import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from catalog_builder import (
    CatalogTemplate,
    DEFAULT_CATALOG_TEMPLATE,
    build_catalog_products,
    generate_catalog_pdf,
    load_catalog_templates,
    product_detail_lines,
    product_title,
    render_catalog_page,
    save_catalog_templates,
)


class CatalogBuilderTests(unittest.TestCase):
    def test_catalog_template_round_trips(self):
        template = CatalogTemplate.from_dict(DEFAULT_CATALOG_TEMPLATE)
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "catalog_templates.json"
            save_catalog_templates(path, {template.name: template})
            self.assertEqual(load_catalog_templates(path), {template.name: template})

    def test_template_storage_rejects_corrupted_data(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "catalog_templates.json"
            path.write_text('{"Animal Planet": {"columns": 0}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_catalog_templates(path)

    def test_product_images_match_verified_csv_data(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "images"
            source.mkdir()
            Image.new("RGB", (320, 240), "#168fe9").save(source / "AP-77030BE.jpg")
            metadata = root / "products.csv"
            with metadata.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["ITEM", "Producto", "Descripcion", "Precio"])
                writer.writerow(["AP-77030BE", "Comedero de acero", "Base antideslizante", "$24.900"])

            products = build_catalog_products(source, metadata)

            self.assertEqual(len(products), 1)
            self.assertEqual(products[0].name, "Comedero de acero")
            self.assertEqual(products[0].item, "AP-77030BE")
            self.assertEqual(products[0].description, "Base antideslizante")
            self.assertEqual(products[0].price, "$24.900")

    def test_all_requested_catalog_columns_are_mapped_and_csv_uses_windows_encoding(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "images"
            source.mkdir()
            Image.new("RGB", (320, 240), "#168fe9").save(source / "AP-77-220.jpg")
            metadata = root / "products.csv"
            metadata.write_bytes(
                (
                    "ITEM;DESCRIPCION;Cub.;MARCA;DISPONIBLE;Precio;EMPAQUE;UM;CTN;CBARRA\r\n"
                    "AP-77-220;Plato para mascota;0.45;Animal Planet;240;14.900;24;PZ;10;7453028199042\r\n"
                ).encode("cp1252")
            )

            products = build_catalog_products(source, metadata)

            self.assertEqual(products[0].description, "Plato para mascota")
            self.assertEqual(product_title(products[0]), "DESCRIPCION: Plato para mascota")
            self.assertEqual(products[0].price, "14.900")
            self.assertEqual(
                product_detail_lines(products[0], CatalogTemplate.from_dict(DEFAULT_CATALOG_TEMPLATE)),
                [
                    "Cub.: 0.45",
                    "MARCA: Animal Planet",
                    "DISPONIBLE: 240",
                    "EMPAQUE: 24",
                    "UM: PZ",
                    "CTN: 10",
                    "CBARRA: 7453028199042",
                ],
            )

    def test_catalog_pdf_contains_one_page_per_capacity_and_keeps_source_images(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "images"
            source.mkdir()
            for index in range(3):
                Image.new("RGB", (320, 240), (20 + index, 100, 200)).save(source / f"AP-{index}.jpg")
            originals = {path.name: path.read_bytes() for path in source.iterdir()}
            products = build_catalog_products(source)
            template = CatalogTemplate(
                name="Test",
                title="Catálogo",
                subtitle="Bienestar",
                footer="Animal Planet",
                columns=1,
                rows=2,
            )
            preview = render_catalog_page(products[:2], template, 1, 2)
            self.assertEqual(preview.size, (1240, 1754))
            output = root / "catalog.pdf"

            page_count = generate_catalog_pdf(products, template, output)

            self.assertEqual(page_count, 2)
            pdf_data = output.read_bytes()
            self.assertTrue(pdf_data.startswith(b"%PDF"))
            self.assertGreaterEqual(pdf_data.count(b"/Type /Page"), 2)
            self.assertEqual(originals, {path.name: path.read_bytes() for path in source.iterdir()})

    def test_duplicate_product_images_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            source = Path(name)
            Image.new("RGB", (100, 100), "white").save(source / "SKU-1_frente.jpg")
            Image.new("RGB", (100, 100), "white").save(source / "SKU-1_detalle.jpg")
            with self.assertRaisesRegex(ValueError, "más de una imagen"):
                build_catalog_products(source)


if __name__ == "__main__":
    unittest.main()
