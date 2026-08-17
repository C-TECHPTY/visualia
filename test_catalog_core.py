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
    enrich_prompt,
    estimate_output_cost,
    validate_output,
    write_report,
)


class CatalogCoreTests(unittest.TestCase):
    def test_excel_all_columns_are_added_to_prompt(self):
        job = ProductJob(
            key="SKU-100",
            images=[Path("SKU-100.jpg")],
            metadata={
                "codigo": "SKU-100",
                "producto": "Juego de sábanas",
                "descripcion": "Estampado geométrico",
                "tamaño": "Queen",
                "pz": "4 piezas",
                "medidas": "228 x 254 cm",
                "material": "Microfibra",
                "lavado": "Ciclo delicado",
            },
        )
        prompt = enrich_prompt("Crear catálogo", job)
        self.assertIn("Descripción: Estampado geométrico", prompt)
        self.assertIn("Tamaño: Queen", prompt)
        self.assertIn("Piezas/cantidad: 4 piezas", prompt)
        self.assertIn("Medidas: 228 x 254 cm", prompt)
        self.assertIn("Material: Microfibra", prompt)
        self.assertIn("Lavado: Ciclo delicado", prompt)
        self.assertIn("no los cambies", prompt)

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
        marked = Image.new("RGB", (1024, 1536), "white")
        for x, color in ((0, (255, 0, 0)), (1023, (0, 0, 255))):
            for y in range(1536):
                marked.putpixel((x, y), color)
        for y, color in ((0, (0, 255, 0)), (1535, (255, 255, 0))):
            for x in range(1024):
                marked.putpixel((x, y), color)
        marked.save(source, "PNG")
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "catalogo.jpg"
            save_final_image(source.getvalue(), output, False, True)
            with Image.open(output) as image:
                self.assertEqual(image.size, (2480, 3508))
                self.assertAlmostEqual(image.info["dpi"][0], 300, delta=1)
                # A4 adds a white safety margin instead of cropping the source edges.
                self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
                center = image.crop((80, 100, 2400, 3408))
                colors = center.getcolors(maxcolors=center.width * center.height)
                self.assertIsNotNone(colors)
                dominant = sorted(colors, reverse=True)[:10]
                self.assertTrue(any(red > 120 and green < 100 for _, (red, green, _blue) in dominant))
                self.assertTrue(any(blue > 120 and red < 100 for _, (red, _green, blue) in dominant))

    def test_catalogo_a4_tonka_preset(self):
        prompt = PROMPT_PRESETS["Catálogo A4 Tonka"]
        self.assertIn("BUILT TO LAST!", prompt)
        self.assertIn("No inventar edades", prompt)
        self.assertIn("encabezado y footer íntegros", prompt)

    def test_gpt_image_mini_official_output_costs(self):
        self.assertEqual(estimate_output_cost("gpt-image-1-mini", "low", "1024x1024", 99), 0.005)
        self.assertEqual(estimate_output_cost("gpt-image-1-mini", "medium", "1024x1024", 99), 0.011)
        self.assertEqual(estimate_output_cost("gpt-image-1-mini", "high", "1024x1024", 99), 0.036)
        self.assertEqual(estimate_output_cost("gpt-image-1-mini", "high", "1536x1024", 99), 0.052)

    def test_gpt_image_2_output_costs(self):
        self.assertEqual(estimate_output_cost("gpt-image-2", "low", "1024x1024", 99), 0.006)
        self.assertEqual(estimate_output_cost("gpt-image-2", "medium", "1024x1024", 99), 0.053)
        self.assertEqual(estimate_output_cost("gpt-image-2", "high", "1024x1024", 99), 0.211)
        self.assertEqual(
            estimate_output_cost("gpt-image-2-2026-04-21", "high", "1024x1536", 99),
            0.165,
        )

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
