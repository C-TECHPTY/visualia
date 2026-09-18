import base64
import io
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

import main
from catalog_core import build_product_jobs, discover_images, enrich_prompt


class ImagePipelineTests(unittest.TestCase):
    names = ["LS24-03763.jpg", "LS24-03764.jpeg", "LS24-03765.png",
             "LS24-03766.PNG", "LS24-03767.webp", "LS24-03768.WEBP",
             "LS24-03769.bmp", "LS24-03770.tif", "LS24-03771.tiff",
             "CARRO LS24-03763_A.PNG", "varias palabras_123-frente.v2.JPG"]

    def sources(self, root):
        for name in self.names:
            Image.new("RGB", (24, 24), "red").save(root / name)

    def test_formats_original_identity_and_actual_api_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.sources(root)
            self.assertEqual(len(discover_images(root)), len(self.names))
            self.assertEqual(main.find_input_images(root), discover_images(root))
            for nested in (False, True):
                jobs = build_product_jobs(root, edit_in_place=nested)
                self.assertEqual(len(jobs), len(self.names))
                for job in jobs:
                    with self.subTest(nested=nested, name=job.original_filename):
                        original = job.original_path.read_bytes()
                        temporary = root / "temporary"
                        temporary.mkdir(exist_ok=True)
                        converted = main.prepare_image_for_api(job.original_path, temporary)
                        self.assertNotEqual(converted.name, job.original_filename)
                        client = Mock()
                        client.images.edit.return_value = SimpleNamespace(data=[SimpleNamespace(
                            b64_json=base64.b64encode(b"result").decode())])
                        prompt = enrich_prompt("Mostrar ITEM", job, False)
                        main.generate_edited_image(client, "test", job.images, prompt,
                                                   "1024x1024", temporary)
                        sent = client.images.edit.call_args.kwargs["prompt"]
                        self.assertIn(f"\nITEM: {job.original_path.stem}\n", sent)
                        self.assertEqual(sent.count("\n\nITEM_REAL:"), 1)
                        self.assertNotIn(converted.name, sent)
                        self.assertEqual(job.item_code, job.original_path.stem)
                        self.assertEqual(job.original_path.read_bytes(), original)
                        converted.unlink()

    def test_collision_resume_failure_and_one_to_one_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            self.sources(source)
            Image.new("RGB", (24, 24), "blue").save(source / "LS24-03763.png")
            (source / "AAA-corrupt.PNG").write_bytes(b"invalid")
            for nested in (False, True):
                jobs = build_product_jobs(source, edit_in_place=nested)
                self.assertEqual(len(jobs), len(self.names) + 2)
                self.assertEqual(len({j.output_key.casefold() for j in jobs}), len(jobs))
                events = queue.Queue()
                kwargs = dict(jobs=jobs, output_folder=root / f"out-{nested}",
                              prompt="Mostrar ITEM", size="1024x1024", quality="low",
                              make_1080=False, make_a4=False, output_style="Imagen IA",
                              demo_mode=True, skip_existing=True, version_existing=False,
                              retry_count=1, progress_queue=events,
                              cancel_event=threading.Event(), fallback_cost=0)
                originals = {j.original_path: j.original_path.read_bytes() for j in jobs}
                with patch("main.load_settings", return_value=("", "demo", 0)), patch(
                        "main.threading.Event.wait", return_value=False):
                    main.process_catalog_jobs(**kwargs)
                    success = [e for e in events.queue if e[0] == "success"]
                    self.assertEqual(len(success), len(jobs) - 1)
                    self.assertEqual(len({e[4] for e in success}), len(success))
                    self.assertEqual([e[1] for e in events.queue if e[0] == "progress"],
                                     list(range(1, len(jobs) + 1)))
                    for event in success:
                        job = next(j for j in jobs if j.primary_image == event[3])
                        self.assertEqual(event[4].stem, job.output_key)
                        self.assertTrue(event[4].is_file())
                    self.assertEqual(len([e for e in events.queue if e[0] == "error"]), 1)
                    main.process_catalog_jobs(**kwargs)
                    self.assertEqual(len([e for e in events.queue if e[0] == "skipped"]), len(jobs) - 1)
                for path, content in originals.items():
                    self.assertEqual(path.read_bytes(), content)

    def test_transparent_png_and_palette_keep_alpha_and_white_jpeg_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for mode in ("RGBA", "P"):
                image = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
                if mode == "P":
                    image = image.convert("P")
                source = root / f"transparent-{mode}.PNG"
                image.save(source)
                prepared = main.prepare_image_for_api(source, root)
                with Image.open(prepared) as converted:
                    self.assertEqual(converted.convert("RGBA").getpixel((0, 0))[3], 0)
                output = root / "result.jpg"
                main.save_final_image(prepared.read_bytes(), output, False)
                with Image.open(output) as converted:
                    self.assertEqual(converted.getpixel((0, 0)), (255, 255, 255))

    def test_preview_sends_original_item(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "LS24-03763.png"
            Image.new("RGB", (24, 24), "red").save(source)
            payload = base64.b64encode(source.read_bytes()).decode()
            client = Mock()
            client.images.edit.return_value = SimpleNamespace(data=[SimpleNamespace(b64_json=payload)])
            with patch("main.load_settings", return_value=("test", "test", 0)), patch(
                    "main.OpenAI", return_value=client):
                main.generate_preview(root, root / "out", "Mostrar ITEM", "1024x1024",
                                      False, queue.Queue(), job=build_product_jobs(root)[0])
            self.assertIn("\nITEM: LS24-03763\n", client.images.edit.call_args.kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()
