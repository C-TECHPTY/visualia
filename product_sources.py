"""Read product tables and per-item technical sheets without guessing missing facts."""
import csv
import re
import unicodedata
from pathlib import Path


def header(value):
    value = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    return re.sub(r"[\s_-]+", " ", "".join(c for c in value if not unicodedata.combining(c)))


IDENTIFIERS = ("item", "sku", "codigo", "archivo", "file", "producto id")
FIELDS = set(IDENTIFIERS) | {"producto", "nombre", "descripcion", "caracteristicas", "tamano", "peso", "material", "empaque", "ean", "marca", "medidas", "color", "capacidad"}


def product_key(value):
    value = str(value).strip()
    if Path(value).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".txt", ".xlsx", ".csv"}:
        value = Path(value).stem
    return re.sub(r"(?:[_ -](?:frente|frontal|atras|reverso|lateral|detalle|empaque|caja|uso|vista|front|back|side|detail|package))+$", "", value, flags=re.I).casefold()


def _cell(cell):
    value = cell.value
    if value is None:
        return ""
    # Preserve explicit Excel zero-padding on identifiers and EANs.
    if isinstance(value, (int, float)) and value == int(value):
        fmt = cell.number_format
        if re.fullmatch(r"0+", fmt or ""):
            return str(int(value)).zfill(len(fmt))
        return str(int(value))
    return str(value).strip()


def sheets(path):
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            return [("CSV", list(csv.reader(handle, dialect))) ]
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("Usa XLSX, XLSM, CSV o fichas TXT; convierte los archivos XLS antiguos a XLSX.")
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        return [(sheet.title, [[_cell(c) for c in row] for row in sheet.iter_rows()]) for sheet in book.worksheets]
    finally:
        book.close()


def _records(path, individual, sheet_name, key_column, header_row):
    if path.suffix.lower() == ".txt":
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = path.read_text(encoding="cp1252")
        row, notes = {}, []
        for line in content.splitlines():
            match = re.match(r"^([^:=]{1,60})\s*[:=]\s*(.+)$", line)
            if match:
                name, value = match.groups()
                name = header(name)
                row[name] = (row.get(name, "") + " " + value.strip()).strip()
            elif line.strip():
                notes.append(line.strip())
        if notes:
            row["ficha tecnica"] = "\n".join(notes)
        if row:
            yield row
        return
    found_sheet = False
    for title, values in sheets(path):
        if sheet_name and title != sheet_name:
            continue
        found_sheet = True
        nonempty = [r for r in values if any(str(v).strip() for v in r)]
        # Vertical sheets: Campo | Valor, optionally preceded by a title.
        pairs = [r for r in nonempty if len(r) >= 2 and header(r[0]) in FIELDS and str(r[1]).strip()]
        if individual and len(pairs) >= 2 and all(not any(str(v).strip() for v in r[2:]) for r in pairs) and header(pairs[0][1]) not in FIELDS:
            yield {header(r[0]): str(r[1]).strip() for r in nonempty if len(r) >= 2 and str(r[1]).strip()}
            continue
        wanted = (header(key_column),) if key_column else IDENTIFIERS
        index = header_row - 1 if header_row else next((i for i, r in enumerate(values) if any(header(c) in wanted for c in r)), None)
        if index is None and individual:
            index = next((i for i, r in enumerate(values) if sum(header(c) in FIELDS for c in r) >= 2), None)
        if index is None or index >= len(values):
            continue
        names = [header(c) for c in values[index]]
        populated = [n for n in names if n]
        if len(populated) != len(set(populated)):
            raise ValueError(f"{path.name}, {title}: hay encabezados duplicados.")
        for values_row in values[index + 1:]:
            row = {name: str(value).strip() for name, value in zip(names, values_row) if name and str(value).strip()}
            if row:
                yield row
    if sheet_name and not found_sheet:
        raise ValueError(f"No existe la hoja '{sheet_name}' en {path.name}.")


def load_product_source(path, sheet_name="", key_column="", header_row=0):
    if not path:
        return {}
    path = Path(path)
    if not path.exists():
        raise ValueError(f"No existe la fuente de productos: {path}")
    folder = path.is_dir()
    files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".csv", ".xlsx", ".xlsm"} and not p.name.startswith("~$")) if folder else [path]
    result, origins = {}, {}
    for file in files:
        records = list(_records(file, folder or file.suffix.lower() == ".txt", sheet_name, key_column, header_row))
        if not records:
            raise ValueError(f"No se reconocieron productos en {file.name}. Selecciona hoja, fila de encabezados y columna ITEM/SKU, o usa una ficha Campo/Valor.")
        if folder and len(records) != 1:
            raise ValueError(f"{file.name}: se esperaba una ficha de un solo producto. Usa el modo Excel general para tablas con varios productos.")
        for row in records:
            identifiers = [row[k] for k in ((header(key_column),) if key_column else IDENTIFIERS) if row.get(k)]
            if folder:
                filename_key = product_key(file.stem)
                if identifiers and filename_key not in {product_key(v) for v in identifiers}:
                    raise ValueError(f"Conflicto en {file.name}: el ITEM/SKU de la ficha no coincide con el nombre del archivo.")
                identifiers.append(file.stem)
            if not identifiers:
                if file.suffix.lower() == ".txt":
                    identifiers = [file.stem]
                else:
                    raise ValueError(f"{file.name}: hay una fila sin ITEM/SKU. Indica la columna identificadora.")
            for key in {product_key(v) for v in identifiers}:
                if key in result:
                    raise ValueError(f"ITEM/SKU duplicado '{key}': {origins[key]} y {file.name}.")
                result[key], origins[key] = row, file.name
    if not result:
        raise ValueError("La carpeta no contiene fichas TXT, XLSX, XLSM o CSV.")
    return result
