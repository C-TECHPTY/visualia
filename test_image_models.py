import base64
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from catalog_core import estimate_output_cost


class ImageModelTests(unittest.TestCase):
    def test_new_models_persist_and_reach_image_edit_api(self):
        for model in ("gpt-image-2.5-sunburst", "gpt-image-2.5-sunburst-2026-09-08"):
            with self.subTest(model=model), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source.png"
                source.write_bytes(b"test image")
                with patch.dict(os.environ, {}, clear=True), patch.object(main, "ENV_PATH", root / ".env"), patch.object(main, "LEGACY_ENV_PATH", root / "missing.env"):
                    main.save_settings("test-key", model, 0.12)
                    self.assertEqual(main.load_settings()[1], model)
                client = Mock()
                client.images.edit.return_value = SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"result").decode())])
                with patch.object(main, "prepare_image_for_api", return_value=source):
                    result = main.generate_edited_image(client, model, source, "edit", "1024x1024", root, "high")
                self.assertEqual(result, b"result")
                self.assertEqual(client.images.edit.call_args.kwargs["model"], model)
                self.assertEqual(estimate_output_cost(model, "high", "1024x1024", 0.12), 0.12)

    def test_default_and_existing_model_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {}, clear=True), patch.object(main, "ENV_PATH", root / ".env"), patch.object(main, "LEGACY_ENV_PATH", root / "missing.env"):
                self.assertEqual(main.load_settings()[1], "gpt-image-2.5-sunburst")
                main.save_settings("test-key", "gpt-image-2-2026-04-21", 0.06)
                self.assertEqual(main.load_settings()[1], "gpt-image-2-2026-04-21")


if __name__ == "__main__":
    unittest.main()
