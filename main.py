import base64
import hashlib
import io
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    Y,
    BooleanVar,
    IntVar,
    StringVar,
    Text,
    Tk,
    Toplevel,
    filedialog,
    messagebox,
)
from tkinter import ttk

from dotenv import load_dotenv, set_key
from openai import OpenAI
from PIL import Image, ImageDraw, ImageOps, ImageTk

from catalog_core import (
    GROUPING_OPTIONS,
    OUTPUT_STYLE_OPTIONS,
    OUTPUT_FORMAT_OPTIONS,
    PROMPT_PRESETS,
    QUALITY_API_VALUES,
    QUALITY_OPTIONS,
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


APP_NAME = "Generador de Imágenes por Lote"
BRAND_NAME = "VISUALIA"
APP_AUTHOR = "Creado por NELSON SANCHEZ DILLON"
APP_VERSION = "1.3.5"
GITHUB_REPOSITORY = "C-TECHPTY/visualia"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
API_SIZES = ("1024x1024", "1536x1024", "1024x1536")
BATCH_LIMIT_OPTIONS = ("1", "5", "10", "Todas")
FINAL_SOCIAL_SIZE = (1080, 1080)
A4_PRINT_SIZE = (2480, 3508)
A4_SAFE_MARGIN = (90, 110)
DEFAULT_ESTIMATED_COST = 0.06
MODEL_OPTIONS = ("Económico · gpt-image-1-mini", "Profesional · gpt-image-2")
MODEL_API_VALUES = {
    "Económico · gpt-image-1-mini": "gpt-image-1-mini",
    "Profesional · gpt-image-2": "gpt-image-2",
}


def application_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative_path: str) -> Path:
    """Resolve bundled visual resources both in source and PyInstaller builds."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / relative_path


def user_data_folder() -> Path:
    """Return a writable per-user folder, including after Program Files installation."""
    base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Visualia"


ENV_PATH = user_data_folder() / ".env"
LEGACY_ENV_PATH = application_folder() / ".env"


def load_settings() -> tuple[str, str, float]:
    """Load API and cost estimate settings from .env."""
    # Preserve existing portable/source configuration while preferring the installed user's settings.
    if LEGACY_ENV_PATH.exists():
        load_dotenv(LEGACY_ENV_PATH, override=False)
    load_dotenv(ENV_PATH, override=True)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini").strip()
    if model not in MODEL_API_VALUES.values():
        model = "gpt-image-1-mini"
    cost_text = os.getenv("ESTIMATED_COST_PER_IMAGE_USD", str(DEFAULT_ESTIMATED_COST)).strip()

    try:
        estimated_cost = float(cost_text)
    except ValueError:
        estimated_cost = DEFAULT_ESTIMATED_COST

    return api_key, model, max(0.0, estimated_cost)


def save_settings(api_key: str, model: str, estimated_cost: float) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), "OPENAI_API_KEY", api_key.strip(), quote_mode="never")
    safe_model = model if model in MODEL_API_VALUES.values() else "gpt-image-1-mini"
    set_key(str(ENV_PATH), "OPENAI_IMAGE_MODEL", safe_model, quote_mode="never")
    set_key(
        str(ENV_PATH),
        "ESTIMATED_COST_PER_IMAGE_USD",
        f"{max(0.0, estimated_cost):.4f}",
        quote_mode="never",
    )


def load_budget() -> tuple[bool, float, float]:
    load_dotenv(ENV_PATH, override=True)
    enabled = os.getenv("LOCAL_BUDGET_ENABLED", "false").lower() == "true"
    try:
        loaded = max(0.0, float(os.getenv("LOCAL_BUDGET_LOADED_USD", "0")))
        remaining = max(0.0, float(os.getenv("LOCAL_BUDGET_REMAINING_USD", str(loaded))))
    except ValueError:
        return False, 0.0, 0.0
    return enabled, loaded, min(loaded, remaining)


def save_budget(enabled: bool, loaded: float, remaining: float) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), "LOCAL_BUDGET_ENABLED", str(enabled).lower(), quote_mode="never")
    set_key(str(ENV_PATH), "LOCAL_BUDGET_LOADED_USD", f"{max(0.0, loaded):.4f}", quote_mode="never")
    set_key(str(ENV_PATH), "LOCAL_BUDGET_REMAINING_USD", f"{max(0.0, remaining):.4f}", quote_mode="never")


def version_tuple(value: str) -> tuple[int, ...]:
    clean = value.strip().lower().lstrip("v").split("-", 1)[0]
    try:
        return tuple(int(part) for part in clean.split("."))
    except ValueError:
        return (0,)


def fetch_latest_release() -> dict:
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"Visualia/{APP_VERSION}"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)


def find_input_images(input_folder: Path) -> list[Path]:
    """Return supported images in stable alphabetical order."""
    return sorted(
        path
        for path in input_folder.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def prepare_image_for_api(source_path: Path, temp_dir: Path, index: int = 0) -> Path:
    """Convert every input to PNG before sending it to the Image API."""
    destination = temp_dir / f"{source_path.stem}_{index}_api.png"
    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        image.save(destination, "PNG")
    return destination


def save_final_image(image_bytes: bytes, output_path: Path, make_1080: bool, make_a4: bool = False) -> None:
    """Save generated bytes as the selected PNG/JPG format."""
    if not make_1080 and not make_a4 and output_path.suffix.lower() == ".png":
        output_path.write_bytes(image_bytes)
        return

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
        temp_file.write(image_bytes)
        temp_name = temp_file.name

    try:
        with Image.open(temp_name) as image:
            image = ImageOps.exif_transpose(image)
            if make_a4:
                # Preserve the complete generated page. The former ImageOps.fit cropped the
                # top and bottom when converting the API's 2:3 image to the A4 ratio.
                margin_x, margin_y = A4_SAFE_MARGIN
                inner_size = (A4_PRINT_SIZE[0] - margin_x * 2, A4_PRINT_SIZE[1] - margin_y * 2)
                page = Image.new("RGB", A4_PRINT_SIZE, "white")
                content = ImageOps.contain(
                    image.convert("RGB"), inner_size, method=Image.Resampling.LANCZOS
                )
                position = (
                    (A4_PRINT_SIZE[0] - content.width) // 2,
                    (A4_PRINT_SIZE[1] - content.height) // 2,
                )
                page.paste(content, position)
                final_image = page
            elif make_1080:
                final_image = ImageOps.fit(
                    image, FINAL_SOCIAL_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
                )
            else:
                final_image = image
            if output_path.suffix.lower() in {".jpg", ".jpeg"}:
                final_image.convert("RGB").save(output_path, "JPEG", quality=95, subsampling=0, optimize=True, dpi=(300, 300) if make_a4 else (96, 96))
            else:
                final_image.save(output_path, "PNG", dpi=(300, 300) if make_a4 else (96, 96))
    finally:
        Path(temp_name).unlink(missing_ok=True)


def make_demo_image_bytes(source_path: Path, size: str) -> bytes:
    """Create a visibly marked local result without calling any AI service."""
    width, height = (int(value) for value in size.split("x", 1))
    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        demo_image = ImageOps.fit(
            image,
            (width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )

    banner_height = max(56, height // 12)
    draw = ImageDraw.Draw(demo_image)
    draw.rectangle((0, height - banner_height, width, height), fill="#17365d")
    draw.text(
        (24, height - banner_height + 18),
        "MODO DEMOSTRACION - SIN IA / SIN COSTO",
        fill="white",
    )
    output = io.BytesIO()
    demo_image.save(output, "PNG")
    return output.getvalue()


def make_display_image(image_path: Path, max_size: tuple[int, int] = (640, 640)) -> ImageTk.PhotoImage:
    """Create a Tk-compatible preview image without changing the saved file."""
    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGBA")
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)


def generated_output_path(output_folder: Path, source_path: Path, output_format: str = "PNG") -> Path:
    extension = ".jpg" if output_format.upper() == "JPG" else ".png"
    return output_folder / f"{source_path.stem}{extension}"


def preview_output_path(output_folder: Path, source_path: Path, output_format: str = "PNG") -> Path:
    extension = ".jpg" if output_format.upper() == "JPG" else ".png"
    return output_folder / f"{source_path.stem}_preview{extension}"


def generate_edited_image(
    client: OpenAI,
    model: str,
    source_path: Path | list[Path],
    prompt: str,
    size: str,
    temp_dir: Path,
    quality: str = "auto",
) -> bytes:
    """Send one image to the OpenAI Image API and return generated image bytes."""
    source_paths = source_path if isinstance(source_path, list) else [source_path]
    api_image_paths = [prepare_image_for_api(path, temp_dir, index) for index, path in enumerate(source_paths)]
    with ExitStack() as stack:
        image_files = [stack.enter_context(path.open("rb")) for path in api_image_paths]
        result = client.images.edit(
            model=model,
            image=image_files if len(image_files) > 1 else image_files[0],
            prompt=prompt,
            size=size,
            quality=quality,
            output_format="png",
        )

    encoded_image = result.data[0].b64_json
    if not encoded_image:
        raise RuntimeError("La API no devolvio una imagen en base64.")
    return base64.b64decode(encoded_image)


def process_catalog_jobs(
    jobs: list[ProductJob],
    output_folder: Path,
    prompt: str,
    size: str,
    quality: str,
    make_1080: bool,
    make_a4: bool,
    output_style: str,
    demo_mode: bool,
    skip_existing: bool,
    version_existing: bool,
    retry_count: int,
    progress_queue: queue.Queue,
    cancel_event: threading.Event,
    fallback_cost: float,
    output_format: str = "PNG",
) -> None:
    api_key, model, _ = load_settings()
    if not demo_mode and not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en el archivo .env.")
    output_folder.mkdir(parents=True, exist_ok=True)
    client = None if demo_mode else OpenAI(api_key=api_key)
    display_model = "MODO DEMOSTRACION (sin IA)" if demo_mode else model
    progress_queue.put(("start", len(jobs), display_model, 0))
    report_rows: list[ReportRow] = []
    errors: list[str] = []
    unit_cost = 0.0 if demo_mode else estimate_output_cost(model, quality, size, fallback_cost)

    with tempfile.TemporaryDirectory() as temp_name:
        temp_dir = Path(temp_name)
        for index, job in enumerate(jobs, start=1):
            if cancel_event.is_set():
                progress_queue.put(("cancelled", index - 1, len(jobs)))
                break

            populated_columns = sum(1 for value in job.metadata.values() if value.strip())
            progress_queue.put(("metadata", job.key, bool(job.metadata), populated_columns))

            existing_path = choose_output_path(output_folder, job.key, False, output_format)
            if skip_existing and existing_path.exists():
                progress_queue.put(("skipped", job.key, existing_path.name))
                report_rows.append(
                    ReportRow(job.key, "; ".join(str(path) for path in job.images), str(existing_path), "OMITIDO")
                )
                progress_queue.put(("progress", index))
                continue

            output_path = choose_output_path(output_folder, job.key, version_existing, output_format)
            job_prompt = enrich_prompt(prompt, job)
            progress_queue.put(
                ("status", f"Procesando {job.key} ({index}/{len(jobs)})...", job.primary_image)
            )
            started = time.monotonic()
            last_error: Exception | None = None

            for attempt in range(retry_count + 1):
                try:
                    if demo_mode:
                        image_bytes = make_demo_image_bytes(job.primary_image, size)
                    else:
                        image_bytes = generate_edited_image(
                            client, model, job.images, job_prompt, size, temp_dir, quality
                        )

                    if output_style == "Infografia con texto exacto":
                        base_path = temp_dir / f"{index}_base.png"
                        save_final_image(image_bytes, base_path, False)
                        if make_a4:
                            composed_path = temp_dir / f"{index}_composed.png"
                            compose_infographic(base_path, composed_path, job)
                            save_final_image(composed_path.read_bytes(), output_path, False, True)
                        else:
                            compose_infographic(base_path, output_path, job)
                    else:
                        save_final_image(image_bytes, output_path, make_1080, make_a4)

                    expected_size = A4_PRINT_SIZE if make_a4 else (1080, 1080) if make_1080 or output_style == "Infografia con texto exacto" else None
                    issues = validate_output(output_path, expected_size)
                    if issues:
                        progress_queue.put(("validation", job.key, "; ".join(issues)))
                    elapsed = time.monotonic() - started
                    report_rows.append(
                        ReportRow(
                            job.key,
                            "; ".join(str(path) for path in job.images),
                            str(output_path),
                            "OK" if not issues else "REVISAR",
                            "; ".join(issues),
                            display_model,
                            quality,
                            size,
                            unit_cost,
                            elapsed,
                        )
                    )
                    progress_queue.put(
                        ("success", job.primary_image.name, output_path.name, job.primary_image, output_path)
                    )
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    error_text = str(exc)
                    if "insufficient_quota" in error_text or "no credits" in error_text.lower():
                        break
                    if attempt < retry_count:
                        wait_seconds = 2 ** attempt
                        progress_queue.put(
                            ("retry", job.key, attempt + 1, retry_count, wait_seconds, error_text)
                        )
                        if cancel_event.wait(wait_seconds):
                            break

            if cancel_event.is_set() and last_error is not None:
                report_rows.append(
                    ReportRow(
                        job.key,
                        "; ".join(str(path) for path in job.images),
                        str(output_path),
                        "CANCELADO",
                        str(last_error),
                        display_model,
                        quality,
                        size,
                        0.0,
                        time.monotonic() - started,
                    )
                )
                progress_queue.put(("cancelled", index - 1, len(jobs)))
                break

            if last_error is not None:
                error_message = f"{job.key}: {last_error}"
                errors.append(error_message)
                report_rows.append(
                    ReportRow(
                        job.key,
                        "; ".join(str(path) for path in job.images),
                        str(output_path),
                        "ERROR",
                        str(last_error),
                        display_model,
                        quality,
                        size,
                        0.0,
                        time.monotonic() - started,
                    )
                )
                progress_queue.put(("error", error_message))
            progress_queue.put(("progress", index))

    report_path = write_report(output_folder, report_rows)
    progress_queue.put(("report", report_path))
    if not cancel_event.is_set():
        progress_queue.put(("done", errors))


def process_images(
    images: list[Path],
    output_folder: Path,
    prompt: str,
    size: str,
    make_1080: bool,
    progress_queue: queue.Queue,
    already_done: int = 0,
    demo_mode: bool = False,
) -> None:
    """Process a specific image list and report progress through a thread-safe queue."""
    api_key, model, _ = load_settings()
    if not demo_mode and not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en el archivo .env.")

    output_folder.mkdir(parents=True, exist_ok=True)
    client = None if demo_mode else OpenAI(api_key=api_key)
    if demo_mode:
        model = "MODO DEMOSTRACION (sin IA)"
    errors: list[str] = []
    total = already_done + len(images)

    progress_queue.put(("start", total, model, already_done))

    with tempfile.TemporaryDirectory() as temp_name:
        temp_dir = Path(temp_name)
        for local_index, image_path in enumerate(images, start=1):
            current_index = already_done + local_index
            try:
                progress_queue.put(
                    ("status", f"Procesando {image_path.name} ({current_index}/{total})...", image_path)
                )
                if demo_mode:
                    image_bytes = make_demo_image_bytes(image_path, size)
                else:
                    image_bytes = generate_edited_image(client, model, image_path, prompt, size, temp_dir)
                output_path = generated_output_path(output_folder, image_path)
                save_final_image(image_bytes, output_path, make_1080)
                progress_queue.put(("success", image_path.name, output_path.name, image_path, output_path))
            except Exception as exc:
                error_message = f"{image_path.name}: {exc}"
                errors.append(error_message)
                progress_queue.put(("error", error_message))
            finally:
                progress_queue.put(("progress", current_index))

    progress_queue.put(("done", errors))


def process_batch(
    input_folder: Path,
    output_folder: Path,
    prompt: str,
    size: str,
    make_1080: bool,
    progress_queue: queue.Queue,
    skip_first_image: Path | None = None,
    max_images: int | None = None,
    demo_mode: bool = False,
) -> None:
    images = find_input_images(input_folder)
    if not images:
        raise RuntimeError("No se encontraron imagenes JPG, PNG o WEBP en la carpeta de entrada.")

    if max_images is not None:
        images = images[:max_images]

    already_done = 0
    if skip_first_image:
        images = [image for image in images if image != skip_first_image]
        already_done = 1

    process_images(images, output_folder, prompt, size, make_1080, progress_queue, already_done, demo_mode)


def generate_preview(
    input_folder: Path,
    output_folder: Path,
    prompt: str,
    size: str,
    make_1080: bool,
    progress_queue: queue.Queue,
    demo_mode: bool = False,
    job: ProductJob | None = None,
    quality: str = "auto",
    output_style: str = "Imagen IA",
    output_format: str = "PNG",
    make_a4: bool = False,
) -> None:
    """Generate one paid preview from the first image."""
    api_key, model, _ = load_settings()
    if not demo_mode and not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY en el archivo .env.")

    images = find_input_images(input_folder)
    if not images:
        raise RuntimeError("No se encontraron imagenes JPG, PNG o WEBP en la carpeta de entrada.")

    output_folder.mkdir(parents=True, exist_ok=True)
    source_path = job.primary_image if job else images[0]
    preview_path = preview_output_path(output_folder, source_path, output_format)
    client = None if demo_mode else OpenAI(api_key=api_key)
    if demo_mode:
        model = "MODO DEMOSTRACION (sin IA)"

    progress_queue.put(("preview_start", model, source_path.name))
    if job:
        populated_columns = sum(1 for value in job.metadata.values() if value.strip())
        progress_queue.put(("metadata", job.key, bool(job.metadata), populated_columns))
    with tempfile.TemporaryDirectory() as temp_name:
        if demo_mode:
            image_bytes = make_demo_image_bytes(source_path, size)
        else:
            reference_images = job.images if job else source_path
            effective_prompt = enrich_prompt(prompt, job) if job else prompt
            image_bytes = generate_edited_image(
                client, model, reference_images, effective_prompt, size, Path(temp_name), quality
            )
        if output_style == "Infografia con texto exacto" and job:
            base_path = Path(temp_name) / "preview_base.png"
            save_final_image(image_bytes, base_path, False)
            if make_a4:
                composed_path = Path(temp_name) / "preview_composed.png"
                compose_infographic(base_path, composed_path, job)
                save_final_image(composed_path.read_bytes(), preview_path, False, True)
            else:
                compose_infographic(base_path, preview_path, job)
        else:
            save_final_image(image_bytes, preview_path, make_1080, make_a4)

    progress_queue.put(("preview_done", source_path, preview_path))


class BatchImageGeneratorApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        icon_path = resource_path("assets/visualia.ico")
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except Exception:
                pass
        self.root.geometry("1420x900")
        self.root.minsize(1050, 760)

        self.colors = {
            "bg": "#f6f7fc",
            "panel": "#ffffff",
            "ink": "#08123f",
            "muted": "#66719a",
            "primary": "#5547ff",
            "secondary": "#12bce7",
            "success": "#168fe9",
            "log": "#070f43",
        }
        self.root.configure(bg=self.colors["bg"])

        self.input_folder = StringVar()
        self.output_folder = StringVar()
        self.size = StringVar(value=API_SIZES[0])
        saved_model = load_settings()[1]
        self.image_model = StringVar(
            value=next(label for label, value in MODEL_API_VALUES.items() if value == saved_model)
        )
        self.batch_limit = StringVar(value=BATCH_LIMIT_OPTIONS[-1])
        self.make_1080 = BooleanVar(value=True)
        self.make_a4 = BooleanVar(value=False)
        self.demo_mode = BooleanVar(value=False)
        self.show_viewer = BooleanVar(value=True)
        self.grouping = StringVar(value=GROUPING_OPTIONS[0])
        self.quality = StringVar(value=QUALITY_OPTIONS[0])
        self.output_format = StringVar(value=OUTPUT_FORMAT_OPTIONS[0])
        self.output_style = StringVar(value=OUTPUT_STYLE_OPTIONS[0])
        self.prompt_preset = StringVar(value="Personalizado")
        self.metadata_file = StringVar()
        self.skip_existing = BooleanVar(value=True)
        self.version_existing = BooleanVar(value=True)
        self.retry_count = IntVar(value=2)
        self.status = StringVar(value="Selecciona carpetas, escribe un prompt y genera el lote.")
        self.counter_text = StringVar(value="Imagenes: 0 | Estimado lote: $0.00 | Vista previa: $0.00")
        self.budget_text = StringVar(value="Presupuesto local: no configurado")

        self.estimated_cost = load_settings()[2]
        self.budget_enabled, self.budget_loaded, self.budget_remaining = load_budget()
        self.preview_source_path: Path | None = None
        self.preview_generated_path: Path | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.preview_job: ProductJob | None = None
        self.viewer_window: Toplevel | None = None
        self.viewer_before_label: ttk.Label | None = None
        self.viewer_after_label: ttk.Label | None = None
        self.viewer_caption: ttk.Label | None = None
        self.viewer_before_photo: ImageTk.PhotoImage | None = None
        self.viewer_after_photo: ImageTk.PhotoImage | None = None
        self.brand_photo: ImageTk.PhotoImage | None = None

        self.progress_queue: queue.Queue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()

        self._build_ui()
        self._update_counter()
        self.root.after(150, self._poll_progress_queue)
        self.root.after(2500, lambda: self._check_for_updates(silent=True))

    def _build_ui(self) -> None:
        self._configure_styles()

        main = ttk.Frame(self.root, padding=22, style="App.TFrame")
        main.pack(fill=BOTH, expand=True)

        header = ttk.Frame(main, padding=20, style="Hero.TFrame")
        header.pack(fill=X, pady=(0, 16))

        brand = ttk.Frame(header, style="Hero.TFrame")
        brand.pack(side=LEFT, padx=(0, 28))
        logo_path = resource_path("assets/visualia-logo.png")
        if logo_path.exists():
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((84, 84), Image.Resampling.LANCZOS)
            self.brand_photo = ImageTk.PhotoImage(logo)
            ttk.Label(brand, image=self.brand_photo, style="Hero.TLabel").pack(side=LEFT, padx=(0, 12))
        ttk.Label(brand, text=BRAND_NAME, style="Brand.TLabel").pack(side=LEFT)

        separator = ttk.Separator(header, orient="vertical")
        separator.pack(side=LEFT, fill=Y, padx=(0, 28))
        title_area = ttk.Frame(header, style="Hero.TFrame")
        title_area.pack(side=LEFT, fill=BOTH, expand=True)
        ttk.Label(title_area, text=APP_NAME, style="HeroTitle.TLabel").pack(anchor="w")
        ttk.Label(
            title_area,
            text="Edicion inteligente por lote para catalogo, Amazon e Instagram",
            style="HeroSubtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(title_area, text=APP_AUTHOR, style="HeroAuthor.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(header, text="✦  IMAGENES · CATALOGO · IA", style="HeroBadge.TLabel").pack(side=RIGHT)

        top_grid = ttk.Frame(main, style="App.TFrame")
        top_grid.pack(fill=X)

        folder_card = ttk.Frame(top_grid, padding=16, style="Card.TFrame")
        folder_card.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 12))
        self._folder_row(folder_card, "Carpeta de entrada", self.input_folder, self._select_input_folder)
        self._folder_row(folder_card, "Carpeta de salida", self.output_folder, self._select_output_folder)

        stats_card = ttk.Frame(top_grid, padding=16, style="Card.TFrame")
        stats_card.pack(side=RIGHT, fill=BOTH)
        ttk.Label(stats_card, textvariable=self.counter_text, style="Counter.TLabel").pack(anchor="w")
        ttk.Label(stats_card, textvariable=self.budget_text, style="Budget.TLabel").pack(anchor="w", pady=(7, 0))
        ttk.Button(stats_card, text="Ajustar saldo", command=self._show_budget_settings).pack(anchor="w", pady=(8, 0))
        ttk.Label(
            stats_card,
            text="El costo es aproximado. El cobro real aparece en el panel de uso de OpenAI.",
            style="Muted.TLabel",
            wraplength=280,
        ).pack(anchor="w", pady=(8, 0))

        prompt_card = ttk.Frame(main, padding=16, style="Card.TFrame")
        prompt_card.pack(fill=BOTH, expand=True, pady=(16, 0))
        ttk.Label(prompt_card, text="✧  Prompt personalizado", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.prompt_text = Text(
            prompt_card,
            height=9,
            wrap="word",
            font=("Segoe UI", 10),
            bg="#fbfdff",
            fg=self.colors["ink"],
            insertbackground=self.colors["primary"],
            relief="solid",
            bd=1,
            padx=10,
            pady=10,
        )
        self.prompt_text.pack(fill=BOTH, expand=True)

        options = ttk.Frame(main, padding=16, style="Card.TFrame")
        options.pack(fill=X, pady=(16, 0))

        ttk.Label(options, text="Tamano API", style="Field.TLabel").pack(side=LEFT)
        size_selector = ttk.Combobox(options, textvariable=self.size, values=API_SIZES, state="readonly", width=14)
        size_selector.pack(side=LEFT, padx=(8, 20))
        size_selector.bind("<<ComboboxSelected>>", lambda _event: self._update_counter())

        ttk.Label(options, text="Modelo", style="Field.TLabel").pack(side=LEFT)
        model_selector = ttk.Combobox(
            options, textvariable=self.image_model, values=MODEL_OPTIONS, state="readonly", width=27
        )
        model_selector.pack(side=LEFT, padx=(8, 20))
        model_selector.bind("<<ComboboxSelected>>", self._on_model_changed)

        ttk.Label(options, text="Calidad", style="Field.TLabel").pack(side=LEFT)
        quality_selector = ttk.Combobox(
            options, textvariable=self.quality, values=QUALITY_OPTIONS, state="readonly", width=9
        )
        quality_selector.pack(side=LEFT, padx=(8, 20))
        quality_selector.bind("<<ComboboxSelected>>", lambda _event: self._update_counter())

        ttk.Label(options, text="Formato", style="Field.TLabel").pack(side=LEFT)
        format_selector = ttk.Combobox(
            options, textvariable=self.output_format, values=OUTPUT_FORMAT_OPTIONS, state="readonly", width=6
        )
        format_selector.pack(side=LEFT, padx=(8, 20))

        ttk.Label(options, text="Cantidad", style="Field.TLabel").pack(side=LEFT)
        limit_selector = ttk.Combobox(
            options,
            textvariable=self.batch_limit,
            values=BATCH_LIMIT_OPTIONS,
            state="readonly",
            width=8,
        )
        limit_selector.pack(side=LEFT, padx=(8, 20))
        limit_selector.bind("<<ComboboxSelected>>", lambda _event: self._update_counter())

        ttk.Checkbutton(
            options,
            text="Salida final 1080x1080 para Amazon/Instagram",
            variable=self.make_1080,
            command=self._toggle_social_output,
        ).pack(side=LEFT)

        ttk.Checkbutton(
            options,
            text="Página A4 vertical 300 dpi",
            variable=self.make_a4,
            command=self._toggle_a4_output,
        ).pack(side=LEFT, padx=(16, 0))

        ttk.Checkbutton(
            options,
            text="Modo demostracion (sin API)",
            variable=self.demo_mode,
            command=self._update_counter,
        ).pack(side=LEFT, padx=(16, 0))

        actions = ttk.Frame(main, style="App.TFrame")
        actions.pack(fill=X, pady=(16, 10))

        self.preview_button = ttk.Button(
            actions,
            text="✧  Generar vista previa",
            command=self._start_preview,
            style="Primary.TButton",
        )
        self.preview_button.pack(side=LEFT)

        self.generate_button = ttk.Button(
            actions,
            text="➤  Generar lote",
            command=self._start_batch,
            style="Success.TButton",
        )
        self.generate_button.pack(side=LEFT, padx=(8, 0))

        self.refresh_button = ttk.Button(actions, text="↻  Actualizar conteo", command=self._update_counter)
        self.refresh_button.pack(side=LEFT, padx=(8, 0))

        self.advanced_button = ttk.Button(actions, text="⚙  Opciones avanzadas", command=self._show_advanced_options)
        self.advanced_button.pack(side=LEFT, padx=(8, 0))

        self.cancel_button = ttk.Button(actions, text="Detener", command=self._cancel_batch, state="disabled")
        self.cancel_button.pack(side=LEFT, padx=(8, 0))

        # The viewer toggle lives in Advanced Options to keep this row compact.

        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.pack(side=LEFT, fill=X, expand=True, padx=(14, 0))

        ttk.Label(main, textvariable=self.status, style="Status.TLabel").pack(anchor="w", pady=(0, 8))

        ttk.Label(main, text="▣  Registro y errores", style="LogTitle.TLabel").pack(anchor="w", pady=(10, 6))
        log_frame = ttk.Frame(main, padding=10, style="LogCard.TFrame")
        log_frame.pack(fill=BOTH, expand=True)

        self.log_text = Text(
            log_frame,
            height=10,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            bg=self.colors["log"],
            fg="#dbeafe",
            insertbackground="#dbeafe",
            relief="flat",
            padx=10,
            pady=10,
        )
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        self.log_text.configure(state="normal")
        self.log_text.insert("1.0", "Esperando iniciar proceso...\n")
        self.log_text.configure(state="disabled")

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Hero.TFrame", background="#ffffff")
        style.configure("Hero.TLabel", background="#ffffff")
        style.configure("Card.TFrame", background=self.colors["panel"], relief="solid", borderwidth=1)
        style.configure("LogCard.TFrame", background=self.colors["log"], relief="solid", borderwidth=1)
        style.configure(
            "HeroTitle.TLabel",
            background="#ffffff",
            foreground=self.colors["ink"],
            font=("Segoe UI", 22, "bold"),
        )
        style.configure(
            "Brand.TLabel",
            background="#ffffff",
            foreground=self.colors["ink"],
            font=("Segoe UI", 23, "bold"),
        )
        style.configure(
            "HeroSubtitle.TLabel",
            background="#ffffff",
            foreground=self.colors["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "HeroAuthor.TLabel",
            background="#ffffff",
            foreground=self.colors["primary"],
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "HeroBadge.TLabel",
            background="#eef2ff",
            foreground=self.colors["primary"],
            font=("Segoe UI", 9, "bold"),
            padding=(14, 9),
        )
        style.configure(
            "Section.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["ink"],
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "LogTitle.TLabel",
            background=self.colors["bg"],
            foreground=self.colors["ink"],
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "Field.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["ink"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Counter.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["primary"],
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "Budget.TLabel",
            background=self.colors["panel"],
            foreground="#059669",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background=self.colors["bg"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 10),
        )
        style.configure("TButton", font=("Segoe UI", 9), padding=(12, 7))
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(14, 8))
        style.configure("Success.TButton", font=("Segoe UI", 9, "bold"), padding=(14, 8))
        style.map("Primary.TButton", background=[("active", "#4434ef"), ("!disabled", self.colors["primary"])], foreground=[("!disabled", "#ffffff")])
        style.map("Success.TButton", background=[("active", "#0d7bd1"), ("!disabled", self.colors["success"])], foreground=[("!disabled", "#ffffff")])

    def _folder_row(self, parent: ttk.Frame, label: str, variable: StringVar, command) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill=X, pady=5)
        ttk.Label(row, text="▢", style="Counter.TLabel").pack(side=LEFT, padx=(0, 8))
        ttk.Label(row, text=label, width=18, style="Field.TLabel").pack(side=LEFT)
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttk.Button(row, text="Seleccionar", command=command).pack(side=RIGHT)

    def _select_input_folder(self) -> None:
        selected = filedialog.askdirectory(title="Seleccionar carpeta de entrada")
        if selected:
            self.input_folder.set(selected)
            self._clear_preview_state()
            self._update_counter()

    def _select_output_folder(self) -> None:
        selected = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if selected:
            self.output_folder.set(selected)
            self._clear_preview_state()
            self._update_counter()

    def _on_model_changed(self, _event=None) -> None:
        model = MODEL_API_VALUES[self.image_model.get()]
        api_key, _, fallback = load_settings()
        save_settings(api_key, model, fallback)
        self._update_counter()
        if model == "gpt-image-2":
            self.status.set("Modo Profesional: mayor fidelidad para textiles, escenas de uso y productos complejos.")
        else:
            self.status.set("Modo Económico: recomendado para pruebas, fondos y grandes cantidades.")

    def _show_advanced_options(self) -> None:
        window = Toplevel(self.root)
        window.title("Opciones avanzadas")
        window.geometry("720x610")
        window.minsize(650, 560)
        window.configure(bg=self.colors["bg"])

        container = ttk.Frame(window, padding=18, style="App.TFrame")
        container.pack(fill=BOTH, expand=True)
        ttk.Label(container, text="Configuracion del catalogo", style="LogTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14)
        )

        fields = [
            ("Preset de prompt", self.prompt_preset, tuple(PROMPT_PRESETS)),
            ("Agrupacion", self.grouping, GROUPING_OPTIONS),
            ("Tipo de salida", self.output_style, OUTPUT_STYLE_OPTIONS),
        ]
        for row, (label, variable, values) in enumerate(fields, start=1):
            ttk.Label(container, text=label, style="Status.TLabel").grid(row=row, column=0, sticky="w", pady=6)
            combo = ttk.Combobox(container, textvariable=variable, values=values, state="readonly", width=34)
            combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=6)
            if variable is self.prompt_preset:
                combo.bind("<<ComboboxSelected>>", self._apply_prompt_preset)
            else:
                combo.bind("<<ComboboxSelected>>", lambda _event: self._update_counter())

        ttk.Label(container, text="Datos CSV/XLSX", style="Status.TLabel").grid(row=5, column=0, sticky="w", pady=6)
        ttk.Entry(container, textvariable=self.metadata_file).grid(row=5, column=1, sticky="ew", pady=6)
        ttk.Button(container, text="Seleccionar", command=self._select_metadata_file).grid(
            row=5, column=2, sticky="ew", padx=(8, 0), pady=6
        )

        ttk.Button(container, text="Crear plantilla Excel", command=self._create_metadata_template).grid(
            row=6, column=1, sticky="w", pady=(4, 12)
        )

        checks = ttk.Frame(container, padding=12, style="Card.TFrame")
        checks.grid(row=7, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Checkbutton(checks, text="Omitir resultados existentes", variable=self.skip_existing).pack(anchor="w")
        ttk.Checkbutton(checks, text="Crear versiones sin reemplazar", variable=self.version_existing).pack(anchor="w")
        ttk.Checkbutton(
            checks, text="Mostrar visor Antes/Despues", variable=self.show_viewer, command=self._toggle_batch_viewer
        ).pack(anchor="w")

        retry_row = ttk.Frame(container, style="App.TFrame")
        retry_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Label(retry_row, text="Reintentos por error temporal:", style="Status.TLabel").pack(side=LEFT)
        ttk.Spinbox(retry_row, from_=0, to=5, textvariable=self.retry_count, width=5).pack(side=LEFT, padx=(8, 0))

        note = (
            "Agrupa por prefijo nombres como SKU_frente y SKU_detalle. En modo Infografia, la IA crea "
            "la fotografia y la aplicacion agrega localmente los textos exactos del CSV/Excel."
        )
        ttk.Label(container, text=note, style="Status.TLabel", wraplength=650).grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(8, 14)
        )

        actions = ttk.Frame(container, style="App.TFrame")
        actions.grid(row=10, column=0, columnspan=3, sticky="ew")
        ttk.Button(actions, text="Abrir carpeta de salida", command=self._open_output_folder).pack(side=LEFT)
        ttk.Button(actions, text="Configurar API", command=self._show_api_settings).pack(side=LEFT, padx=(8, 0))
        ttk.Button(actions, text="Buscar actualizaciones", command=self._check_for_updates).pack(
            side=LEFT, padx=(8, 0)
        )
        ttk.Button(actions, text="Cerrar", command=window.destroy).pack(side=RIGHT)
        container.columnconfigure(1, weight=1)

    def _check_for_updates(self, silent: bool = False) -> None:
        if not silent:
            self.status.set("Buscando actualizaciones de Visualia...")
        threading.Thread(target=self._fetch_update_safely, args=(silent,), daemon=True).start()

    def _show_budget_settings(self) -> None:
        window = Toplevel(self.root)
        window.title("Presupuesto local")
        window.geometry("540x390")
        window.resizable(False, False)
        window.configure(bg=self.colors["bg"])
        container = ttk.Frame(window, padding=22, style="App.TFrame")
        container.pack(fill=BOTH, expand=True)
        ttk.Label(container, text="Control estimado de saldo", style="LogTitle.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text=("Escribe cuánto cargaste originalmente y cuánto muestra actualmente OpenAI. Desde el saldo "
                  "actual Visualia descontará el costo estimado de las nuevas imágenes."),
            style="Status.TLabel",
            wraplength=470,
        ).pack(anchor="w", pady=(10, 16))
        loaded_var = StringVar(value=f"{self.budget_loaded:.2f}" if self.budget_enabled else "")
        remaining_var = StringVar(value=f"{self.budget_remaining:.2f}" if self.budget_enabled else "")
        loaded_row = ttk.Frame(container, style="App.TFrame")
        loaded_row.pack(fill=X, pady=(0, 10))
        ttk.Label(loaded_row, text="Total cargado en la API (USD)", style="Status.TLabel").pack(side=LEFT)
        ttk.Entry(loaded_row, textvariable=loaded_var, width=16).pack(side=RIGHT)
        remaining_row = ttk.Frame(container, style="App.TFrame")
        remaining_row.pack(fill=X)
        ttk.Label(remaining_row, text="Saldo actual mostrado por OpenAI (USD)", style="Status.TLabel").pack(side=LEFT)
        ttk.Entry(remaining_row, textvariable=remaining_var, width=16).pack(side=RIGHT)
        ttk.Label(
            container,
            text="Ejemplo: total cargado 10.00 y saldo actual 9.40.",
            style="Status.TLabel",
        ).pack(anchor="w", pady=(10, 0))

        def apply_budget() -> None:
            try:
                loaded = float(loaded_var.get().replace(",", "."))
                remaining = float(remaining_var.get().replace(",", "."))
                if loaded < 0 or remaining < 0 or remaining > loaded:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    APP_NAME,
                    "Introduce valores válidos. El saldo actual debe ser menor o igual al total cargado.",
                )
                return
            self.budget_enabled = True
            self.budget_loaded = loaded
            self.budget_remaining = remaining
            save_budget(True, loaded, remaining)
            self._update_counter()
            window.destroy()

        buttons = ttk.Frame(container, style="App.TFrame")
        buttons.pack(fill=X, pady=(22, 0))
        ttk.Button(buttons, text="Desactivar control", command=lambda: self._disable_budget(window)).pack(side=LEFT)
        ttk.Button(buttons, text="Guardar saldo", command=apply_budget, style="Success.TButton").pack(side=RIGHT)

    def _disable_budget(self, window: Toplevel) -> None:
        self.budget_enabled = False
        save_budget(False, self.budget_loaded, self.budget_remaining)
        self._update_counter()
        window.destroy()

    def _charge_estimated_generation(self) -> None:
        if self.demo_mode.get() or not self.budget_enabled:
            return
        self.budget_remaining = max(0.0, self.budget_remaining - self._current_unit_cost())
        save_budget(True, self.budget_loaded, self.budget_remaining)
        self._update_counter()

    def _fetch_update_safely(self, silent: bool) -> None:
        try:
            release = fetch_latest_release()
            latest = str(release.get("tag_name", "")).lstrip("v")
            if version_tuple(latest) > version_tuple(APP_VERSION):
                installer = next(
                    (
                        asset
                        for asset in release.get("assets", [])
                        if asset.get("name", "").lower().startswith("instalador_visualia_")
                        and asset.get("name", "").lower().endswith(".exe")
                    ),
                    None,
                )
                checksum = next(
                    (asset for asset in release.get("assets", []) if asset.get("name", "").endswith(".sha256")),
                    None,
                )
                if installer:
                    self.progress_queue.put(("update_available", latest, release, installer, checksum))
                    return
            self.progress_queue.put(("update_current", silent))
        except Exception as exc:
            self.progress_queue.put(("update_error", silent, str(exc)))

    def _offer_update(self, latest: str, release: dict, installer: dict, checksum: dict | None) -> None:
        changes = (release.get("body") or "Actualización con mejoras y correcciones.").strip()
        if len(changes) > 900:
            changes = changes[:900] + "..."
        answer = messagebox.askyesno(
            "Actualización de Visualia",
            f"Hay una nueva versión disponible: {latest}\n\n"
            f"Versión instalada: {APP_VERSION}\n\nNovedades:\n{changes}\n\n"
            "¿Deseas descargarla e instalarla ahora?",
        )
        if answer:
            threading.Thread(
                target=self._download_update_safely,
                args=(latest, installer, checksum),
                daemon=True,
            ).start()

    def _download_update_safely(self, latest: str, installer: dict, checksum: dict | None) -> None:
        try:
            download_dir = user_data_folder() / "updates"
            download_dir.mkdir(parents=True, exist_ok=True)
            target = download_dir / installer["name"]
            request = urllib.request.Request(installer["browser_download_url"], headers={"User-Agent": "Visualia"})
            with urllib.request.urlopen(request, timeout=30) as response, target.open("wb") as output:
                total = int(response.headers.get("Content-Length", "0"))
                downloaded = 0
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    percent = int(downloaded * 100 / total) if total else 0
                    self.progress_queue.put(("update_progress", percent, latest))

            if checksum:
                check_request = urllib.request.Request(
                    checksum["browser_download_url"], headers={"User-Agent": "Visualia"}
                )
                with urllib.request.urlopen(check_request, timeout=15) as response:
                    expected = response.read().decode("utf-8").strip().split()[0].lower()
                actual = hashlib.sha256(target.read_bytes()).hexdigest().lower()
                if actual != expected:
                    target.unlink(missing_ok=True)
                    raise RuntimeError("La verificación SHA-256 de la actualización no coincide.")
            self.progress_queue.put(("update_ready", target, latest))
        except Exception as exc:
            self.progress_queue.put(("update_download_error", str(exc)))

    def _apply_prompt_preset(self, _event=None) -> None:
        preset = PROMPT_PRESETS.get(self.prompt_preset.get(), "")
        if preset:
            self.prompt_text.delete("1.0", END)
            self.prompt_text.insert("1.0", preset)
        if self.prompt_preset.get() == "Catálogo A4 Tonka":
            self.size.set("1024x1536")
            self.make_a4.set(True)
            self.make_1080.set(False)
            self.status.set("Preset Catálogo A4 Tonka: salida vertical 2480x3508 a 300 dpi.")
            self._update_counter()

    def _toggle_social_output(self) -> None:
        if self.make_1080.get():
            self.make_a4.set(False)
        self._update_counter()

    def _toggle_a4_output(self) -> None:
        if self.make_a4.get():
            self.make_1080.set(False)
            self.size.set("1024x1536")
        self._update_counter()

    def _select_metadata_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Seleccionar datos de productos",
            filetypes=(("Excel o CSV", "*.xlsx *.xlsm *.csv"), ("Todos", "*.*")),
        )
        if selected:
            self.metadata_file.set(selected)
            self._update_counter()

    def _create_metadata_template(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Guardar plantilla de productos",
            defaultextension=".xlsx",
            filetypes=(("Excel", "*.xlsx"), ("CSV", "*.csv")),
        )
        if not selected:
            return
        try:
            create_metadata_template(Path(selected))
            self.metadata_file.set(selected)
            messagebox.showinfo(APP_NAME, f"Plantilla creada:\n{selected}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _open_output_folder(self) -> None:
        folder_text = self.output_folder.get().strip()
        if not folder_text:
            messagebox.showinfo(APP_NAME, "Selecciona primero una carpeta de salida.")
            return
        folder = Path(folder_text)
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _show_api_settings(self) -> None:
        current_key, _, current_cost = load_settings()
        current_model = MODEL_API_VALUES[self.image_model.get()]
        window = Toplevel(self.root)
        window.title("Configuracion de OpenAI API")
        window.geometry("620x330")
        window.configure(bg=self.colors["bg"])
        container = ttk.Frame(window, padding=18, style="App.TFrame")
        container.pack(fill=BOTH, expand=True)

        key_var = StringVar(value=current_key)
        model_var = StringVar(value=current_model)
        cost_var = StringVar(value=f"{current_cost:.4f}")
        fields = (("API key", key_var, True), ("Modelo", model_var, False), ("Costo alternativo USD", cost_var, False))
        for row, (label, variable, secret) in enumerate(fields):
            ttk.Label(container, text=label, style="Status.TLabel").grid(row=row, column=0, sticky="w", pady=8)
            entry = ttk.Entry(
                container,
                textvariable=variable,
                show="*" if secret else "",
                state="readonly" if label == "Modelo" else "normal",
            )
            entry.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=8)

        ttk.Label(
            container,
            text=(
                "El modelo se selecciona en la pantalla principal. La clave se guarda en el perfil local "
                "del usuario, no se incluye en el EXE y nunca se escribe en los reportes."
            ),
            style="Status.TLabel",
            wraplength=560,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 18))

        def save_and_close():
            try:
                cost = float(cost_var.get().strip())
                save_settings(key_var.get(), model_var.get(), cost)
                self.estimated_cost = max(0.0, cost)
                self._update_counter()
                window.destroy()
                messagebox.showinfo(APP_NAME, "Configuracion guardada.")
            except ValueError:
                messagebox.showerror(APP_NAME, "El costo debe ser un numero valido.")

        ttk.Button(container, text="Guardar", command=save_and_close, style="Success.TButton").grid(
            row=4, column=1, sticky="e"
        )
        container.columnconfigure(1, weight=1)

    def _catalog_jobs(self, input_folder: Path) -> list[ProductJob]:
        metadata_path = Path(self.metadata_file.get().strip()) if self.metadata_file.get().strip() else None
        return build_product_jobs(input_folder, self.grouping.get(), metadata_path)

    def _start_preview(self) -> None:
        if not self._can_start_work():
            return

        try:
            input_folder, output_folder, prompt = self._read_valid_form()
            jobs = self._catalog_jobs(input_folder)
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"No se pudieron preparar los productos:\n{exc}")
            return

        if not jobs:
            messagebox.showerror(APP_NAME, "No se encontraron productos para procesar.")
            return
        self.preview_job = jobs[0]

        unit_cost = self._current_unit_cost()
        if self.budget_enabled and not self.demo_mode.get() and self.budget_remaining + 1e-9 < unit_cost:
            messagebox.showwarning(
                APP_NAME,
                "El saldo estimado no alcanza para la vista previa. Ajusta el saldo o activa modo demostración.",
            )
            return
        mode_note = "No se llamara a OpenAI ni se generara costo." if self.demo_mode.get() else (
            f"Puede costar aprox. ${unit_cost:.2f} USD."
        )
        proceed = messagebox.askyesno(
            APP_NAME,
            f"Se generara 1 vista previa. {mode_note}\n\n"
            "Quieres continuar?",
        )
        if not proceed:
            return

        self._clear_log()
        self._set_working_state(True)
        self.progress.configure(value=0, maximum=1)
        self.status.set("Generando vista previa...")

        self.worker_thread = threading.Thread(
            target=self._run_preview_safely,
            args=(
                input_folder,
                output_folder,
                prompt,
                self.size.get(),
                self.make_1080.get(),
                self.demo_mode.get(),
                self.preview_job,
                QUALITY_API_VALUES[self.quality.get()],
                self.output_style.get(),
                self.output_format.get(),
                self.make_a4.get(),
            ),
            daemon=True,
        )
        self.worker_thread.start()

    def _start_batch(self, skip_first_image: Path | None = None) -> None:
        if not self._can_start_work():
            return

        try:
            input_folder, output_folder, prompt = self._read_valid_form()
            jobs = self._catalog_jobs(input_folder)
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"No se pudieron preparar los productos:\n{exc}")
            return

        if not jobs:
            messagebox.showerror(APP_NAME, "No se encontraron imagenes JPG, PNG o WEBP en la carpeta de entrada.")
            return

        selected_count = self._selected_image_count(len(jobs))
        jobs = jobs[:selected_count]
        if skip_first_image:
            jobs = [job for job in jobs if job.primary_image != skip_first_image]
        total_to_charge = len(jobs)
        unit_cost = self._current_unit_cost()
        if self.budget_enabled and not self.demo_mode.get() and unit_cost > 0:
            affordable = int((self.budget_remaining + 1e-9) / unit_cost)
            if affordable <= 0:
                messagebox.showwarning(
                    APP_NAME,
                    "El saldo estimado no alcanza para generar una imagen. Ajusta el saldo o usa modo demostración.",
                )
                return
            if affordable < total_to_charge:
                jobs = jobs[:affordable]
                total_to_charge = len(jobs)
                messagebox.showinfo(
                    APP_NAME,
                    f"El saldo estimado alcanza para {affordable} imagen(es). El lote se limitará automáticamente.",
                )
        estimated_total = max(0, total_to_charge) * unit_cost
        projected = max(0.0, self.budget_remaining - estimated_total) if self.budget_enabled else 0.0
        budget_line = f"\nSaldo estimado después: ${projected:.3f} USD" if self.budget_enabled else ""
        proceed = messagebox.askyesno(
            APP_NAME,
            f"Imagenes a generar ahora: {total_to_charge}\n"
            f"Costo aproximado: ${estimated_total:.3f} USD{budget_line}\n\n"
            "Proceder con el lote?",
        )
        if not proceed:
            return

        if not skip_first_image:
            self._clear_log()

        self._set_working_state(True)
        self.cancel_event.clear()
        self.progress.configure(value=0, maximum=max(1, total_to_charge))
        self.status.set("Iniciando lote...")
        if self.show_viewer.get():
            self._ensure_batch_viewer()
            if skip_first_image:
                output_key = self.preview_job.key if self.preview_job else skip_first_image.stem
                final_path = choose_output_path(output_folder, output_key, False, self.output_format.get())
                if final_path.exists():
                    self._update_batch_viewer(skip_first_image, final_path)

        self.worker_thread = threading.Thread(
            target=self._run_batch_safely,
            args=(
                input_folder,
                output_folder,
                jobs,
                prompt,
                self.size.get(),
                self.make_1080.get(),
                self.demo_mode.get(),
                QUALITY_API_VALUES[self.quality.get()],
                self.output_style.get(),
                self.skip_existing.get(),
                self.version_existing.get(),
                max(0, int(self.retry_count.get())),
                self.output_format.get(),
                self.make_a4.get(),
            ),
            daemon=True,
        )
        self.worker_thread.start()

    def _read_valid_form(self) -> tuple[Path, Path, str]:
        input_folder_text = self.input_folder.get().strip()
        output_folder_text = self.output_folder.get().strip()
        input_folder = Path(input_folder_text).expanduser()
        output_folder = Path(output_folder_text).expanduser()
        prompt = self.prompt_text.get("1.0", END).strip()
        self._validate_form(input_folder_text, output_folder_text, input_folder, prompt)
        return input_folder, output_folder, prompt

    def _validate_form(
        self,
        input_folder_text: str,
        output_folder_text: str,
        input_folder: Path,
        prompt: str,
    ) -> None:
        if not input_folder_text:
            raise ValueError("Selecciona una carpeta de entrada valida.")
        if not input_folder.is_dir():
            raise ValueError("Selecciona una carpeta de entrada valida.")
        if not output_folder_text:
            raise ValueError("Selecciona una carpeta de salida valida.")
        if not prompt:
            raise ValueError("Escribe un prompt personalizado antes de generar.")

    def _run_preview_safely(
        self,
        input_folder: Path,
        output_folder: Path,
        prompt: str,
        size: str,
        make_1080: bool,
        demo_mode: bool,
        job: ProductJob,
        quality: str,
        output_style: str,
        output_format: str,
        make_a4: bool,
    ) -> None:
        try:
            generate_preview(
                input_folder,
                output_folder,
                prompt,
                size,
                make_1080,
                self.progress_queue,
                demo_mode,
                job,
                quality,
                output_style,
                output_format,
                make_a4,
            )
        except Exception as exc:
            self.progress_queue.put(("fatal", str(exc)))

    def _run_batch_safely(
        self,
        input_folder: Path,
        output_folder: Path,
        jobs: list[ProductJob],
        prompt: str,
        size: str,
        make_1080: bool,
        demo_mode: bool,
        quality: str,
        output_style: str,
        skip_existing: bool,
        version_existing: bool,
        retry_count: int,
        output_format: str,
        make_a4: bool,
    ) -> None:
        try:
            process_catalog_jobs(
                jobs,
                output_folder,
                prompt,
                size,
                quality,
                make_1080,
                make_a4,
                output_style,
                demo_mode,
                skip_existing,
                version_existing,
                retry_count,
                self.progress_queue,
                self.cancel_event,
                self.estimated_cost,
                output_format,
            )
        except Exception as exc:
            self.progress_queue.put(("fatal", str(exc)))

    def _poll_progress_queue(self) -> None:
        while True:
            try:
                event = self.progress_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_progress_event(event)
        self.root.after(150, self._poll_progress_queue)

    def _handle_progress_event(self, event: tuple) -> None:
        event_type = event[0]
        if event_type == "preview_start":
            model, image_name = event[1], event[2]
            self.progress.configure(maximum=1, value=0)
            self._append_log(f"Modelo: {model}")
            self._append_log(f"Vista previa: {image_name}")
        elif event_type == "preview_done":
            self.preview_source_path = event[1]
            self.preview_generated_path = event[2]
            self.progress.configure(value=1)
            self.status.set("Vista previa generada. Revisa la imagen antes de continuar.")
            self._append_log(f"PREVIEW: {self.preview_source_path.name} -> {self.preview_generated_path.name}")
            self._charge_estimated_generation()
            self._set_working_state(False)
            self._show_preview_window()
        elif event_type == "start":
            total, model, already_done = event[1], event[2], event[3]
            self.progress.configure(maximum=total, value=already_done)
            self._append_log(f"Modelo: {model}")
            self._append_log(f"Imagenes del lote: {total}")
            if already_done:
                self._append_log("La vista previa aprobada se uso como primera imagen generada.")
        elif event_type == "status":
            self.status.set(event[1])
            if len(event) > 2:
                self._update_batch_viewer(event[2], None)
        elif event_type == "metadata":
            if event[2]:
                self._append_log(f"EXCEL OK: {event[1]} - {event[3]} columna(s) con datos encontradas.")
            else:
                self._append_log(f"AVISO EXCEL: {event[1]} no tiene una fila coincidente; se usará solo la imagen.")
        elif event_type == "success":
            self._append_log(f"OK: {event[1]} -> {event[2]}")
            self._charge_estimated_generation()
            if len(event) > 4:
                self._update_batch_viewer(event[3], event[4])
        elif event_type == "error":
            self._append_log(f"ERROR: {event[1]}")
        elif event_type == "skipped":
            self._append_log(f"OMITIDO: {event[1]} (ya existe {event[2]})")
        elif event_type == "retry":
            self._append_log(
                f"REINTENTO: {event[1]} intento {event[2]}/{event[3]} en {event[4]} s. Motivo: {event[5]}"
            )
        elif event_type == "validation":
            self._append_log(f"REVISAR: {event[1]} - {event[2]}")
        elif event_type == "report":
            self._append_log(f"REPORTE: {event[1]}")
        elif event_type == "progress":
            self.progress.configure(value=event[1])
        elif event_type == "cancelled":
            self._set_working_state(False)
            self.status.set(f"Lote detenido despues de {event[1]} de {event[2]} productos.")
            self._append_log("LOTE DETENIDO POR EL USUARIO")
        elif event_type == "done":
            errors = event[1]
            self._set_working_state(False)
            self._clear_preview_state()
            if errors:
                self.status.set(f"Lote terminado con {len(errors)} error(es).")
                messagebox.showwarning(APP_NAME, "El lote termino, pero algunas imagenes fallaron. Revisa el registro.")
            else:
                self.status.set("Lote terminado correctamente.")
                messagebox.showinfo(APP_NAME, "Todas las imagenes se generaron correctamente.")
        elif event_type == "update_available":
            self._offer_update(event[1], event[2], event[3], event[4])
        elif event_type == "update_current":
            if not event[1]:
                self.status.set(f"Visualia {APP_VERSION} está actualizado.")
                messagebox.showinfo("Actualizaciones", f"Ya tienes la versión más reciente: {APP_VERSION}.")
        elif event_type == "update_error":
            if not event[1]:
                messagebox.showwarning("Actualizaciones", f"No se pudo consultar GitHub Releases.\n\n{event[2]}")
        elif event_type == "update_progress":
            self.progress.configure(maximum=100, value=event[1])
            self.status.set(f"Descargando Visualia {event[2]}... {event[1]}%")
        elif event_type == "update_ready":
            installer_path, latest = event[1], event[2]
            self.status.set(f"Actualización {latest} descargada y verificada.")
            if messagebox.askyesno(
                "Actualización lista",
                "La actualización fue descargada y verificada correctamente.\n\n"
                "Visualia se cerrará y abrirá el instalador. ¿Continuar?",
            ):
                subprocess.Popen([str(installer_path)], cwd=str(installer_path.parent))
                self.root.destroy()
        elif event_type == "update_download_error":
            self.status.set("No se pudo descargar la actualización.")
            messagebox.showerror("Actualización", event[1])
        elif event_type == "fatal":
            self._set_working_state(False)
            self.status.set("No se pudo completar la operacion.")
            self._append_log(f"ERROR FATAL: {event[1]}")
            messagebox.showerror(APP_NAME, event[1])

    def _show_preview_window(self) -> None:
        if not self.preview_source_path or not self.preview_generated_path:
            return

        window = Toplevel(self.root)
        window.title("Vista previa generada")
        window.geometry("780x840")
        window.minsize(620, 620)
        window.configure(bg=self.colors["bg"])

        container = ttk.Frame(window, padding=18, style="App.TFrame")
        container.pack(fill=BOTH, expand=True)

        ttk.Label(container, text=f"Imagen: {self.preview_source_path.name}", style="Status.TLabel").pack(
            anchor="w", pady=(0, 8)
        )

        self.preview_photo = make_display_image(self.preview_generated_path)
        image_label = ttk.Label(container, image=self.preview_photo)
        image_label.pack(fill=BOTH, expand=True, pady=(0, 12))

        remaining = max(0, self._selected_image_count(self._image_count()) - 1)
        cost_remaining = remaining * self._current_unit_cost()
        ttk.Label(
            container,
            text=f"Si apruebas, faltan {remaining} imagenes. Costo aproximado restante: ${cost_remaining:.2f} USD.",
            style="Status.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        actions = ttk.Frame(container, style="App.TFrame")
        actions.pack(fill=X)

        ttk.Button(actions, text="Cancelar", command=window.destroy).pack(side=RIGHT)
        ttk.Button(
            actions,
            text="Proceder con lote",
            command=lambda: self._accept_preview_and_continue(window),
            style="Success.TButton",
        ).pack(side=RIGHT, padx=(0, 8))

    def _accept_preview_and_continue(self, window: Toplevel) -> None:
        if not self.preview_source_path or not self.preview_generated_path:
            window.destroy()
            return

        preview_job = self.preview_job
        output_key = preview_job.key if preview_job else self.preview_source_path.stem
        final_path = choose_output_path(
            Path(self.output_folder.get().strip()), output_key, False, self.output_format.get()
        )
        self.preview_generated_path.replace(final_path)
        self._append_log(f"OK: {self.preview_source_path.name} -> {final_path.name}")
        window.destroy()
        self._start_batch(skip_first_image=self.preview_source_path)

    def _toggle_batch_viewer(self) -> None:
        if self.show_viewer.get():
            self._ensure_batch_viewer()
        else:
            self._close_batch_viewer()

    def _ensure_batch_viewer(self) -> None:
        if self.viewer_window and self.viewer_window.winfo_exists():
            self.viewer_window.deiconify()
            self.viewer_window.lift()
            return

        window = Toplevel(self.root)
        window.title("Visor del lote - Antes y despues")
        window.geometry("1000x620")
        window.minsize(760, 500)
        window.configure(bg=self.colors["bg"])
        window.protocol("WM_DELETE_WINDOW", self._close_batch_viewer)
        self.viewer_window = window

        container = ttk.Frame(window, padding=18, style="App.TFrame")
        container.pack(fill=BOTH, expand=True)
        self.viewer_caption = ttk.Label(
            container,
            text="El visor se actualizara al procesar cada imagen.",
            style="Status.TLabel",
        )
        self.viewer_caption.pack(anchor="w", pady=(0, 12))

        columns = ttk.Frame(container, style="App.TFrame")
        columns.pack(fill=BOTH, expand=True)
        before_frame = ttk.Frame(columns, padding=12, style="Card.TFrame")
        before_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        after_frame = ttk.Frame(columns, padding=12, style="Card.TFrame")
        after_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(8, 0))

        ttk.Label(before_frame, text="ANTES", style="Section.TLabel").pack(pady=(0, 10))
        ttk.Label(after_frame, text="DESPUES", style="Section.TLabel").pack(pady=(0, 10))
        self.viewer_before_label = ttk.Label(before_frame, text="Esperando imagen...")
        self.viewer_before_label.pack(fill=BOTH, expand=True)
        self.viewer_after_label = ttk.Label(after_frame, text="Esperando resultado...")
        self.viewer_after_label.pack(fill=BOTH, expand=True)

    def _update_batch_viewer(self, source_path: Path, result_path: Path | None) -> None:
        if not self.show_viewer.get():
            return
        self._ensure_batch_viewer()
        if not self.viewer_before_label or not self.viewer_after_label or not self.viewer_caption:
            return

        try:
            self.viewer_before_photo = make_display_image(source_path, (440, 440))
            self.viewer_before_label.configure(image=self.viewer_before_photo, text="")
        except Exception as exc:
            self.viewer_before_photo = None
            self.viewer_before_label.configure(image="", text=f"No se pudo mostrar la entrada:\n{exc}")

        if result_path and result_path.exists():
            try:
                self.viewer_after_photo = make_display_image(result_path, (440, 440))
                self.viewer_after_label.configure(image=self.viewer_after_photo, text="")
                self.viewer_caption.configure(text=f"Completada: {source_path.name} -> {result_path.name}")
            except Exception as exc:
                self.viewer_after_photo = None
                self.viewer_after_label.configure(image="", text=f"No se pudo mostrar el resultado:\n{exc}")
        else:
            self.viewer_after_photo = None
            self.viewer_after_label.configure(image="", text="Generando resultado...")
            self.viewer_caption.configure(text=f"Procesando: {source_path.name}")

    def _close_batch_viewer(self) -> None:
        self.show_viewer.set(False)
        if self.viewer_window and self.viewer_window.winfo_exists():
            self.viewer_window.destroy()
        self.viewer_window = None
        self.viewer_before_label = None
        self.viewer_after_label = None
        self.viewer_caption = None
        self.viewer_before_photo = None
        self.viewer_after_photo = None

    def _can_start_work(self) -> bool:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo(APP_NAME, "Ya hay una operacion en proceso.")
            return False
        return True

    def _cancel_batch(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            self.cancel_event.set()
            self.status.set("Deteniendo despues de la imagen actual...")
            self._append_log("Solicitud de detencion enviada.")

    def _set_working_state(self, is_working: bool) -> None:
        state = "disabled" if is_working else "normal"
        self.preview_button.configure(state=state)
        self.generate_button.configure(state=state)
        self.refresh_button.configure(state=state)
        self.advanced_button.configure(state=state)
        self.cancel_button.configure(state="normal" if is_working else "disabled")

    def _image_count(self) -> int:
        folder_text = self.input_folder.get().strip()
        if not folder_text:
            return 0
        folder = Path(folder_text).expanduser()
        if not folder.is_dir():
            return 0
        try:
            return len(self._catalog_jobs(folder))
        except Exception:
            return 0

    def _selected_limit(self) -> int | None:
        value = self.batch_limit.get()
        return None if value == "Todas" else int(value)

    def _selected_image_count(self, available: int) -> int:
        limit = self._selected_limit()
        return available if limit is None else min(available, limit)

    def _current_unit_cost(self) -> float:
        if self.demo_mode.get():
            return 0.0
        model = MODEL_API_VALUES[self.image_model.get()]
        return estimate_output_cost(
            model,
            QUALITY_API_VALUES[self.quality.get()],
            self.size.get(),
            self.estimated_cost,
        )

    def _update_counter(self) -> None:
        count = self._image_count()
        selected_count = self._selected_image_count(count)
        unit_cost = self._current_unit_cost()
        estimated_total = selected_count * unit_cost
        self.counter_text.set(
            f"Disponibles: {count} | A generar: {selected_count} | Estimado: ${estimated_total:.3f} | "
            f"Vista previa: ${unit_cost:.3f}"
        )
        if self.budget_enabled:
            affordable = int((self.budget_remaining + 1e-9) / unit_cost) if unit_cost > 0 else selected_count
            projected = max(0.0, self.budget_remaining - estimated_total)
            spent = max(0.0, self.budget_loaded - self.budget_remaining)
            self.budget_text.set(
                f"Te quedan ${self.budget_remaining:.2f} de ${self.budget_loaded:.2f} | "
                f"Consumido: ${spent:.2f} | Después del lote: ${projected:.2f} | "
                f"Capacidad aproximada: {affordable} imágenes"
            )
        else:
            self.budget_text.set("Presupuesto local: no configurado")

    def _clear_preview_state(self) -> None:
        self.preview_source_path = None
        self.preview_generated_path = None
        self.preview_photo = None
        self.preview_job = None

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(END, message + "\n")
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", END)
        self.log_text.configure(state="disabled")


def main() -> None:
    root = Tk()
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    BatchImageGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
