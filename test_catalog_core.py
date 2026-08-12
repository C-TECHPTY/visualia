import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from catalog_core import (
    ProductJob,
    ReportRow,
    build_product_jobs,
    choose_output_path,
    compose_infographic,
    create_metadata_template,
    validate_output,
    write_report,
)


class CatalogCoreTests(unittest.TestCase):
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

            existing = output / "SKU-1_generado.png"
            existing.touch()
            self.assertEqual(choose_output_path(output, "SKU-1", True).name, "SKU-1_generado_v2.png")

            report = write_report(output, [ReportRow("SKU-1", "a.jpg", "ficha.png", "OK")])
            self.assertTrue(report.exists())

            template = root / "plantilla.csv"
            create_metadata_template(template)
            self.assertTrue(template.exists())


if __name__ == "__main__":
    unittest.main()
