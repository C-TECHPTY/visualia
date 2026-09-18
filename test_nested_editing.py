import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from catalog_core import build_product_jobs
from main import generate_preview, process_catalog_jobs


class NestedEditingTests(unittest.TestCase):
    def test_nested_batch_preserves_sources_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals = {}
            for folder in ("A", "B/deeper", "A/EDITADAS"):
                path = root / folder / "foto.jpg"
                path.parent.mkdir(parents=True)
                Image.new("RGB", (32, 32), "red").save(path)
                originals[path] = path.read_bytes()
            Image.new("RGB", (32, 32)).save(root / "foto.png")
            jobs = build_product_jobs(root, edit_in_place=True)
            self.assertEqual(len(jobs), 3)
            self.assertEqual(len({job.key for job in jobs}), 3)
            self.assertTrue(all(len(job.images) == 1 for job in jobs))
            self.assertEqual(len(build_product_jobs(root)), 1)
            events = queue.Queue()
            report_folder = root / "editadas"
            kwargs = dict(jobs=jobs, output_folder=report_folder, prompt="test",
                          size="1024x1024", quality="low", make_1080=False,
                          make_a4=False, output_style="Imagen IA", demo_mode=True,
                          skip_existing=True, version_existing=False, retry_count=0,
                          progress_queue=events, cancel_event=threading.Event(),
                          fallback_cost=0, output_format="JPG")
            with patch("main.load_settings", return_value=("", "demo", 0)):
                process_catalog_jobs(**kwargs)
                for job in jobs:
                    output = job.output_folder / "foto.jpg"
                    self.assertTrue(output.exists())
                    with Image.open(output) as image:
                        image.verify()
                skipped_before = sum(event[0] == "skipped" for event in events.queue)
                process_catalog_jobs(**kwargs)
                self.assertEqual(sum(event[0] == "skipped" for event in events.queue) - skipped_before, 3)
                kwargs["skip_existing"] = False
                process_catalog_jobs(**kwargs)
                self.assertTrue(all((job.output_folder / "foto_v2.jpg").exists() for job in jobs))
                generate_preview(root, report_folder, "test", "1024x1024", False,
                                 events, demo_mode=True, job=jobs[0])
            previews = [event for event in events.queue if event[0] == "preview_done"]
            self.assertEqual(previews[0][2].parent, jobs[0].output_folder)
            self.assertFalse(any(event[0] == "error" for event in events.queue))
            self.assertEqual(len(build_product_jobs(root, edit_in_place=True)), 3)
            for path, content in originals.items():
                self.assertEqual(path.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
