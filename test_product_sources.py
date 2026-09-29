import tempfile
import unittest
from pathlib import Path
from openpyxl import Workbook
from product_sources import load_product_source
from prompt_library import load_prompts, save_prompts
from catalog_core import build_product_jobs, enrich_prompt


class ProductSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def workbook(self, name, rows):
        book = Workbook()
        for row in rows:
            book.active.append(row)
        path = self.root / name
        book.save(path)
        book.close()
        return path

    def test_general_excel_title_multiple_sheets_and_identifiers(self):
        path = self.workbook("products.xlsx", [["Catálogo"], ["ITEM", "SKU", "Producto", "Características", "EAN"], ["A.01", "ALT01", "Vaso", "Vidrio", "000123"]])
        rows = load_product_source(path)
        self.assertEqual(rows["a.01"]["caracteristicas"], "Vidrio")
        self.assertEqual(rows["alt01"]["ean"], "000123")

    def test_custom_header_and_sheet(self):
        path = self.workbook("products.xlsx", [["Notas"], ["Referencia propia", "Producto"], ["01", "Vaso"]])
        rows = load_product_source(path, sheet_name="Sheet", key_column="Referencia propia", header_row=2)
        self.assertIn("01", rows)
        with self.assertRaisesRegex(ValueError, "No existe la hoja"):
            load_product_source(path, sheet_name="Inexistente")

    def test_multiple_sheets_horizontal_individual_and_duplicate_rows(self):
        path = self.root / "products.xlsx"
        book = Workbook()
        book.active.append(["Portada"])
        sheet = book.create_sheet("Productos")
        sheet.append(["SKU", "Producto"])
        sheet.append(["001", "Vaso"])
        book.save(path)
        self.assertEqual(load_product_source(path)["001"]["producto"], "Vaso")
        sheet.append(["001", "Plato"])
        book.save(path)
        book.close()
        with self.assertRaisesRegex(ValueError, "duplicado"):
            load_product_source(path)
        folder = self.root / "individual"
        folder.mkdir()
        individual = self.workbook("002.xlsx", [["Producto", "Material", "EAN"], ["Plato", "Vidrio", "000123"]])
        individual.rename(folder / individual.name)
        self.assertEqual(load_product_source(folder)["002"]["ean"], "000123")

    def test_product_facts_reach_preview_and_batch_api(self):
        import base64
        import queue
        import threading
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from PIL import Image
        import main
        source = self.root / "images"
        source.mkdir()
        fichas = self.root / "fichas"
        fichas.mkdir()
        for code in ("001", "002"):
            Image.new("RGB", (32, 32), "red").save(source / f"{code}.png")
            (fichas / f"{code}.txt").write_text(f"SKU: {code}\nMaterial: Material-{code}", encoding="utf-8")
        jobs = build_product_jobs(source, metadata_path=fichas)
        client = Mock()
        payload = base64.b64encode((source / "001.png").read_bytes()).decode()
        client.images.edit.return_value = SimpleNamespace(data=[SimpleNamespace(b64_json=payload)])
        with patch("main.load_settings", return_value=("test", "test", 0)), patch("main.OpenAI", return_value=client):
            main.generate_preview(source, self.root / "preview", "Fondo azul", "1024x1024", False, queue.Queue(), job=jobs[0])
            self.assertIn("Material-001", client.images.edit.call_args.kwargs["prompt"])
            client.reset_mock()
            events = queue.Queue()
            main.process_catalog_jobs(jobs=jobs, output_folder=self.root / "out", prompt="Fondo azul",
                size="1024x1024", quality="low", make_1080=False, make_a4=False,
                output_style="Imagen IA", demo_mode=False, skip_existing=False, version_existing=False,
                retry_count=0, progress_queue=events, cancel_event=threading.Event(), fallback_cost=0)
            self.assertEqual(client.images.edit.call_count, 2)
            for code, call in zip(("001", "002"), client.images.edit.call_args_list):
                self.assertIn("Fondo azul", call.kwargs["prompt"])
                self.assertIn(f"Material-{code}", call.kwargs["prompt"])
            self.assertEqual(len([e for e in events.queue if e[0] == "success"]), 2)

    def test_folder_txt_vertical_excel_and_image_matching(self):
        folder = self.root / "fichas"
        folder.mkdir()
        (folder / "001.txt").write_text("ITEM: 001\nProducto: Vaso\nCaracterísticas: Resistente\nEAN: 000123\nInformación adicional", encoding="utf-8")
        path = self.workbook("002.xlsx", [["Ficha técnica"], ["Producto", "Plato"], ["Material", "Cerámica"], ["Peso", "200 g"]])
        path.rename(folder / path.name)
        images = self.root / "images"
        images.mkdir()
        (images / "001_frente.jpg").touch()
        (images / "002.jpg").touch()
        (images / "003.jpg").touch()
        jobs = build_product_jobs(images, metadata_path=folder)
        self.assertEqual(jobs[0].metadata["ean"], "000123")
        self.assertEqual(jobs[1].metadata["material"], "Cerámica")
        self.assertFalse(jobs[2].metadata)
        prompt = enrich_prompt("Diseño azul, mostrar EAN", jobs[0], catalog_details=False)
        self.assertIn("Diseño azul", prompt)
        self.assertIn("EAN: 000123", prompt)
        self.assertIn("Características: Resistente", prompt)

    def test_duplicate_and_conflicting_sheets_are_blocked(self):
        folder = self.root / "fichas"
        folder.mkdir()
        (folder / "001.txt").write_text("ITEM: 002\nProducto: Vaso", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Conflicto"):
            load_product_source(folder)
        (folder / "001.txt").write_text("ITEM: 001", encoding="utf-8")
        (folder / "sub").mkdir()
        (folder / "sub" / "001.txt").write_text("Producto: Vaso", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicado"):
            load_product_source(folder)

    def test_excel_number_format_preserves_zeroes_and_zero_value(self):
        path = self.root / "products.xlsx"
        book = Workbook()
        book.active.append(["ITEM", "EAN", "Peso"])
        book.active.append([1, 123, 0])
        book.active["A2"].number_format = "000"
        book.active["B2"].number_format = "000000"
        book.save(path)
        book.close()
        row = load_product_source(path)["001"]
        self.assertEqual(row["ean"], "000123")
        self.assertEqual(row["peso"], "0")

    def test_reference_only_and_selected_fields(self):
        from catalog_core import ProductJob
        job = ProductJob("001", [Path("001.jpg")], {"producto": "Vaso", "peso": "10 g"})
        job.data_usage = "Solo referencia"
        self.assertIn("No añadas textos", enrich_prompt("Fondo blanco", job))
        job.data_usage = "Campos seleccionados"
        job.visible_fields = "Peso"
        self.assertIn("si existen: Peso", enrich_prompt("Fondo blanco", job))

    def test_prompt_library_persists_updates_and_rejects_corruption(self):
        path = self.root / "library" / "prompts.json"
        self.assertEqual(load_prompts(path), {})
        save_prompts(path, {"Catálogo": "Texto original\nCon acentos"})
        self.assertEqual(load_prompts(path)["Catálogo"], "Texto original\nCon acentos")
        save_prompts(path, {"Catálogo": "Actualizado", "Copia": "Actualizado"})
        self.assertEqual(len(load_prompts(path)), 2)
        path.write_text("[123]", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_prompts(path)


if __name__ == "__main__":
    unittest.main()
