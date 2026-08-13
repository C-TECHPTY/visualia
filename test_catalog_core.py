import csv
import tempfile
import io
import unittest
from pathlib import Path

from PIL import Image

from main import save_final_image

from catalog_core import (
    PROMPT_PRESETS,
    ProductJob,
    ReportRow,
    build_product_jobs,
    choose_output_path,
    compose_infographic,
    create_metadata_template,
    estimate_output_cost,
    validate_output,
    write_report,
)


class CatalogCoreTests(unittest.TestCase):
    def test_producto_en_uso_premium_prompt(self):
        prompt = PROMPT_PRESETS["Producto en uso premium"]
        self.assertIn("set de sábanas", prompt)
        self.assertIn("¿Cómo se verá", prompt)
        self.assertNotIn("Ã", prompt)
        self.assertGreater(len(prompt), 10000)

    def test_save_jpg_output(self):
        source = io.BytesIO()
        Image.new("RGBA", (320, 240), (255, 0, 0, 128)).save(source, "PNG")
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "producto.jpg"
            save_final_image(source.getvalue(), output, True)
            with Image.open(output) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.size, (1080, 1080))

    def test_save_a4_300_dpi_output(self):
        source = io.BytesIO()
        Image.new("RGB", (1024, 1536), "white").save(source, "PNG")
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "catalogo.jpg"
            save_final_image(source.getvalue(), output, False, True)
            with Image.open(output) as image:
                self.assertEqual(image.size, (2480, 3508))
                self.assertAlmostEqual(image.info["dpi"][0], 300, delta=1)

    def test_catalogo_a4_tonka_preset(self):
        prompt = PROMPT_PRESETS["Catálogo A4 Tonka"]
        self.assertIn("BUILT TO LAST!", prompt)
        self.assertIn("No inventar edades", prompt)

    def test_gpt_image_mini_official_output_costs(self):
        self.assertEqual(estimate_output_cost("gpt-image-1-mini", "low", "1024x1024", 99), 0.005)
        self.assertEqual(estimate_output_cost("gpt-image-1-mini", "medium", "1024x1024", 99), 0.011)
        self.assertEqual(estimate_output_cost("gpt-image-1-mini", "high", "1024x1024", 99), 0.036)
        self.assertEqual(estimate_output_cost("gpt-image-1-mini", "high", "1536x1024", 99), 0.052)

    def test_gpt_image_2_output_costs(self):
        self.assertEqual(estimate_output_cost("gpt-image-2", "low", "1024x1024", 99), 0.006)
        self.assertEqual(estimate_output_cost("gpt-image-2", "medium", "1024x1024", 99), 0.053)
        self.assertEqual(estimate_output_cost("gpt-image-2", "high", "1024x1024", 99), 0.211)

    def test_grouping_metadata_composition_and_report(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "entrada"
            output = root / "salida"
            source.mkdir()
            output.mkdir()
            for filename in ("SKU-1_frente.jpg", "SKU-1_detalle.jpg", "SKU-2.jpg"):
                Image.new("RGB", (640, 480), "white").save(source / filename)

            metadata = root / "productos.csv"
            with metadata.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["codigo", "producto", "marca", "beneficio1"])
                writer.writerow(["SKU-1", "Organizador", "Marca Uno", "Facil de instalar"])

            jobs = build_product_jobs(source, "Por prefijo/SKU", metadata)
            self.assertEqual([job.key for job in jobs], ["SKU-1", "SKU-2"])
            self.assertEqual(len(jobs[0].images), 2)
            self.assertEqual(jobs[0].metadata["producto"], "Organizador")

            ai_base = output / "base.png"
            Image.new("RGB", (1024, 1024), "#eeeeee").save(ai_base)
            final = output / "ficha.png"
            compose_infographic(ai_base, final, jobs[0])
            self.assertEqual(validate_output(final, (1080, 1080)), [])

            existing = output / "SKU-1.png"
            existing.touch()
            self.assertEqual(choose_output_path(output, "SKU-1", True).name, "SKU-1_v2.png")
            self.assertEqual(choose_output_path(output, "SKU-2", False, "JPG").name, "SKU-2.jpg")
            (output / "SKU-2.jpg").touch()
            self.assertEqual(choose_output_path(output, "SKU-2", True, "JPG").name, "SKU-2_v2.jpg")

            report = write_report(output, [ReportRow("SKU-1", "a.jpg", "ficha.png", "OK")])
            self.assertTrue(report.exists())

            template = root / "plantilla.csv"
            create_metadata_template(template)
            self.assertTrue(template.exists())


if __name__ == "__main__":
    unittest.main()
