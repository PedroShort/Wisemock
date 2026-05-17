"""Shared file loading pipeline for setup imports."""
from pathlib import Path

from wisemock.config import SUPPORTED_DOC_EXTENSIONS
from wisemock.core.exam_io import load_questions_from_json
from wisemock.core.extract import combine_source_texts, extract_text_from_file


MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_MULTI_FILE_SIZE_BYTES = 100 * 1024 * 1024
MIN_EXTRACTED_TEXT_CHARS = 50


def dedupe_paths(paths):
    """Return non-empty paths once, preserving user order."""
    seen = set()
    out = []
    for raw in paths or []:
        if not raw or not isinstance(raw, str):
            continue
        cleaned = raw.strip()
        if not cleaned:
            continue
        key = str(Path(cleaned).expanduser())
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def file_list_summary(paths):
    names = [Path(path).name for path in paths]
    if len(names) <= 3:
        return ", ".join(names)
    return ", ".join(names[:3]) + f", +{len(names) - 3} more"


def _validate_existing_file(raw):
    try:
        file_path = Path(raw)
    except Exception:
        raise ValueError("Invalid file path.")
    if not file_path.exists():
        raise ValueError(f"File not found: {file_path.name}")
    if not file_path.is_file():
        raise ValueError(f"Not a file: {file_path.name}")
    try:
        size = file_path.stat().st_size
    except OSError as error:
        raise ValueError(f"Cannot read file {file_path.name}: {error}") from error
    if size > MAX_FILE_SIZE_BYTES:
        mb = size / (1024 * 1024)
        raise ValueError(
            f"{file_path.name} is too large ({mb:.1f} MB). Limit is "
            f"{MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB per file."
        )
    if size == 0:
        raise ValueError(f"File is empty: {file_path.name}")
    return file_path, size


def _emit(progress, percent, message):
    if progress:
        progress(max(0, min(100, int(percent))), message)


def load_input_paths(paths, progress=None):
    """Load one setup input job.

    Returns a dict with one of:
    - kind=json_exam
    - kind=single_document
    - kind=multi_study_document
    """
    paths = dedupe_paths(paths)
    if not paths:
        raise ValueError("No files were provided.")

    _emit(progress, 2, "Validating selected file(s)...")

    if len(paths) == 1:
        file_path, _size = _validate_existing_file(paths[0])
        ext = file_path.suffix.lower()
        if ext == ".json":
            _emit(progress, 15, f"Reading {file_path.name}...")
            try:
                data = load_questions_from_json(str(file_path))
            except Exception as error:
                raise ValueError(f"Invalid JSON exam file: {error}") from error
            _emit(progress, 100, f"Loaded {file_path.name}.")
            return {
                "kind": "json_exam",
                "data": data,
                "label": file_path.name,
                "base_path": str(file_path),
            }
        if ext not in SUPPORTED_DOC_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type: {ext or '(no extension)'}. "
                "Supported: .json, .pdf, .docx, .pptx"
            )

        def doc_progress(local_percent, message):
            _emit(progress, 5 + (local_percent * 0.9), message)

        _emit(progress, 5, f"Extracting {file_path.name}...")
        try:
            text = extract_text_from_file(str(file_path), progress=doc_progress)
        except ImportError:
            raise
        except Exception as error:
            raise ValueError(f"Extraction error: {error}") from error
        if not isinstance(text, str) or len(text.strip()) < MIN_EXTRACTED_TEXT_CHARS:
            raise ValueError("Could not extract enough text from this file.")
        status = f"Extracted ~{len(text):,} characters from {file_path.name}"
        _emit(progress, 100, status)
        return {
            "kind": "single_document",
            "path": str(file_path),
            "paths": [str(file_path)],
            "text": text,
            "status": status,
            "file": {"name": file_path.name, "subtext": status},
        }

    file_paths = []
    total_size = 0
    for raw in paths:
        file_path, size = _validate_existing_file(raw)
        ext = file_path.suffix.lower()
        if ext == ".json":
            raise ValueError("JSON exam files must be loaded alone.")
        if ext not in SUPPORTED_DOC_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type in multi-file drop: "
                f"{file_path.name} ({ext or 'no extension'})."
            )
        total_size += size
        file_paths.append(file_path)

    if total_size > MAX_MULTI_FILE_SIZE_BYTES:
        mb = total_size / (1024 * 1024)
        raise ValueError(
            f"Selected files are too large together ({mb:.1f} MB). "
            f"Limit is {MAX_MULTI_FILE_SIZE_BYTES // (1024 * 1024)} MB."
        )

    sources = []
    count = len(file_paths)
    for index, file_path in enumerate(file_paths, 1):
        start = 5 + ((index - 1) / count) * 90
        span = 90 / count

        def doc_progress(local_percent, message, start=start, span=span):
            _emit(progress, start + (local_percent / 100) * span, message)

        _emit(progress, start, f"Loading file {index} of {count}: {file_path.name}")
        try:
            text = extract_text_from_file(str(file_path), progress=doc_progress)
        except ImportError:
            raise
        except Exception as error:
            raise ValueError(f"Extraction error in {file_path.name}: {error}") from error
        if not isinstance(text, str) or len(text.strip()) < MIN_EXTRACTED_TEXT_CHARS:
            raise ValueError(f"Could not extract enough text from {file_path.name}.")
        sources.append((str(file_path), text))

    _emit(progress, 96, f"Combining {count} study files...")
    combined_text = combine_source_texts(sources)
    loaded_paths = [str(path) for path in file_paths]
    status = (
        f"Extracted ~{len(combined_text):,} characters from "
        f"{file_list_summary(loaded_paths)}"
    )
    _emit(progress, 100, status)
    return {
        "kind": "multi_study_document",
        "path": loaded_paths[0],
        "paths": loaded_paths,
        "text": combined_text,
        "status": status,
        "file": {
            "name": f"{count} study files loaded",
            "subtext": status,
        },
    }
