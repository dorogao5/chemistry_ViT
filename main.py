"""FastAPI web application for the chemistry OCR pipeline."""

from __future__ import annotations

import asyncio
import base64
import json
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from chemistry_web_pipeline import ChemistryPipeline, ChemistryOCRError


app = FastAPI(title="Chemistry OCR")


class APIKeyStore:
    """Thread-safe storage for the Mistral API key with local file persistence."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._api_key: str | None = None
        self._key_file = Path(__file__).parent / ".api_key"
        self._load_key()

    def _load_key(self) -> None:
        """Load API key from local file on startup."""
        try:
            if self._key_file.exists():
                with open(self._key_file, 'r', encoding='utf-8') as f:
                    self._api_key = f.read().strip() or None
        except Exception:
            # Ignore file read errors, start with no key
            self._api_key = None

    async def set(self, api_key: str) -> None:
        async with self._lock:
            self._api_key = api_key.strip() or None
            self._save_key()

    def _save_key(self) -> None:
        """Save API key to local file."""
        try:
            if self._api_key:
                with open(self._key_file, 'w', encoding='utf-8') as f:
                    f.write(self._api_key)
            elif self._key_file.exists():
                self._key_file.unlink()  # Remove file if key is cleared
        except Exception:
            # Ignore file write errors
            pass

    async def get(self) -> str | None:
        async with self._lock:
            return self._api_key

    async def is_set(self) -> bool:
        async with self._lock:
            return bool(self._api_key)


api_key_store = APIKeyStore()


GENERATED_DIR = Path(tempfile.gettempdir()) / "chemistry_ocr_docs"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static",
)

generated_files: Dict[str, Tuple[Path, str]] = {}

# Monotonic document index for unique display filenames across requests
_index_lock = asyncio.Lock()
_doc_index = 0


async def _next_doc_index() -> int:
    global _doc_index
    async with _index_lock:
        _doc_index += 1
        return _doc_index


def _decode_data_url(data_url: str) -> Tuple[bytes, str]:
    if not data_url.startswith("data:"):
        raise ValueError("Expected data URL for pasted image")
    header, encoded = data_url.split(",", maxsplit=1)
    mimetype_part = header.split(";", maxsplit=1)[0]
    mime_type = mimetype_part.replace("data:", "") or "image/png"
    data = base64.b64decode(encoded)
    return data, mime_type


async def _ensure_key() -> str:
    api_key = await api_key_store.get()
    if not api_key:
        raise HTTPException(status_code=400, detail="Сначала укажите Mistral API ключ")
    return api_key


def _store_generated_doc(filename: str, content: bytes) -> Tuple[str, str]:
    token = uuid.uuid4().hex
    safe_name = filename if filename.lower().endswith(".docx") else f"{filename}.docx"
    target_path = GENERATED_DIR / f"{token}_{Path(safe_name).name}"
    target_path.write_bytes(content)
    generated_files[token] = (target_path, safe_name)
    return token, safe_name


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    api_key_set = await api_key_store.is_set()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "api_key_set": api_key_set,
            "modes": ["OCR", "ViT"],
            "vit_models": [
                {"key": "pixtral-12b", "label": "small (pixtral-12b + mistral-small)"},
                {"key": "pixtral-large-latest", "label": "high (pixtral-large + mistral-small)"},
            ],
        },
    )


@app.post("/api/set-key")
async def set_api_key(data: dict) -> JSONResponse:
    api_key = (data or {}).get("api_key", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API ключ не может быть пустым")
    await api_key_store.set(api_key)
    return JSONResponse({"message": "API ключ сохранен"})


@app.post("/api/process")
async def process_images(request: Request) -> JSONResponse:
    api_key = await _ensure_key()
    pipeline = ChemistryPipeline(api_key)

    form = await request.form()
    uploads = form.getlist("files")
    pasted_images = form.getlist("pasted")
    mode = form.get("mode") or "ViT"
    vit_model = form.get("vit_model") or "pixtral-large-latest"

    if not uploads and not pasted_images:
        raise HTTPException(status_code=400, detail="Не переданы изображения для обработки")

    documents: List[dict] = []

    try:
        # Process uploaded files
        for upload in uploads:
            if upload is None:
                continue
            filename = upload.filename or "image"
            data = await upload.read()
            if not data:
                continue
            doc_idx = await _next_doc_index()
            if mode == "ViT":
                docx_bytes = pipeline.process_image_bytes_vit(
                    data,
                    mime_type=upload.content_type or "image/png",
                    model=vit_model,
                )
            else:
                docx_bytes = pipeline.process_image_bytes(
                    data, mime_type=upload.content_type or "image/png"
                )
            stem = Path(filename).stem or "image"
            display_name = f"{stem}_{doc_idx}.docx"
            token, saved_name = _store_generated_doc(display_name, docx_bytes)
            documents.append(
                {
                    "filename": saved_name,
                    "download_url": f"/download/{token}",
                }
            )

        # Process pasted images (data URLs)
        for idx, pasted in enumerate(pasted_images):
            if not pasted:
                continue
            data, mime_type = _decode_data_url(pasted)
            doc_idx = await _next_doc_index()
            if mode == "ViT":
                docx_bytes = pipeline.process_image_bytes_vit(
                    data, mime_type=mime_type, model=vit_model
                )
            else:
                docx_bytes = pipeline.process_image_bytes(data, mime_type=mime_type)
            display_name = f"pasted_{doc_idx}.docx"
            token, saved_name = _store_generated_doc(display_name, docx_bytes)
            documents.append(
                {
                    "filename": saved_name,
                    "download_url": f"/download/{token}",
                }
            )
    except ChemistryOCRError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not documents:
        raise HTTPException(status_code=400, detail="Не удалось обработать предоставленные изображения")

    return JSONResponse({"documents": documents})


@app.get("/download/{token}")
async def download_document(token: str) -> Response:
    entry = generated_files.get(token)
    if not entry:
        raise HTTPException(status_code=404, detail="Файл не найден или срок его действия истек")
    path, filename = entry
    if not path.exists():
        generated_files.pop(token, None)
        raise HTTPException(status_code=404, detail="Файл недоступен")
    # Build safe Content-Disposition with ASCII fallback and UTF-8 filename*
    try:
        ascii_fallback = filename.encode("ascii", errors="ignore").decode() or "document.docx"
    except Exception:
        ascii_fallback = "document.docx"
    utf8_quoted = quote(filename)

    # Read bytes and return a direct Response to avoid sendfile quirks
    content = path.read_bytes()
    headers = {
        "Content-Disposition": f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_quoted}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Length": str(len(content)),
    }
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@app.post("/api/clear-key")
async def clear_api_key() -> JSONResponse:
    await api_key_store.set("")
    return JSONResponse({"message": "API ключ удален"})


