from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST, STORAGE_DIR
from .store import (
    create_run,
    get_result,
    get_results_for_run,
    get_run,
    init_store,
    resolve_storage_path,
)
from .parsing import dedupe_blank_only, parse_text_names, parse_uploaded_names
from .worker import run_batch


app = FastAPI(title="OFAC Batch Checker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    init_store()


@app.post("/api/runs")
async def create_run_endpoint(
    names_text: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict:
    names = parse_text_names(names_text)
    if file and file.filename:
        if not file.filename.lower().endswith((".txt", ".csv")):
            raise HTTPException(status_code=400, detail="Only .txt and .csv uploads are supported.")
        names.extend(parse_uploaded_names(file.filename, await file.read()))
    names = dedupe_blank_only(names)
    if not names:
        raise HTTPException(status_code=400, detail="Enter or upload at least one name.")

    run = create_run(names)
    asyncio.create_task(run_batch(str(run["id"])))
    return run


@app.get("/api/runs/{run_id}")
async def get_run_endpoint(run_id: str) -> dict:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@app.get("/api/runs/{run_id}/results/{result_id}/pdf")
async def download_pdf(run_id: str, result_id: int) -> FileResponse:
    result = get_result(run_id, result_id)
    if not result or not result.get("pdf_path"):
        raise HTTPException(status_code=404, detail="PDF not found.")
    path = resolve_storage_path(str(result["pdf_path"]))
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file is missing from storage.")
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@app.get("/api/runs/{run_id}/zip")
async def download_zip(run_id: str) -> FileResponse:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")

    zip_dir = STORAGE_DIR / "zips"
    zip_dir.mkdir(exist_ok=True)
    zip_path = zip_dir / f"ofac-run-{run_id}.zip"
    count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for result in get_results_for_run(run_id):
            if not result.get("pdf_path"):
                continue
            pdf_path = resolve_storage_path(str(result["pdf_path"]))
            if pdf_path.exists():
                archive.write(pdf_path, arcname=pdf_path.name)
                count += 1
    if count == 0:
        raise HTTPException(status_code=404, detail="No PDFs are available for this run.")
    return FileResponse(zip_path, filename=zip_path.name, media_type="application/zip")


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found.")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
