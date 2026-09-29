"""Persistent, atomic storage for user-authored prompts only."""
import json
import os
import tempfile
from pathlib import Path


def load_prompts(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise ValueError("Formato de biblioteca inválido")
        return data
    except (ValueError, OSError) as exc:
        raise ValueError(f"No se pudo leer la biblioteca de prompts: {exc}") from exc


def save_prompts(path: Path, prompts: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(prompts, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
