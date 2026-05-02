from __future__ import annotations

import asyncio
import zipfile

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import (
    authenticate_user,
    check_login_rate_limit,
    clear_failed_logins,
    clear_session_cookie,
    current_user,
    is_auth_configured,
    load_auth_config,
    login_rate_key,
    record_failed_login,
    require_user,
    set_session_cookie,
)
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


class LoginRequest(BaseModel):
    username: str
    password: str


@app.on_event("startup")
async def startup() -> None:
    init_store()


@app.get("/api/auth/status")
async def auth_status(request: Request) -> dict:
    username = current_user(request)
    return {
        "configured": is_auth_configured(),
        "authenticated": username is not None,
        "username": username,
    }


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request) -> JSONResponse:
    config = load_auth_config()
    rate_key = login_rate_key(payload.username, request)
    check_login_rate_limit(rate_key)
    if not authenticate_user(payload.username, payload.password, config):
        record_failed_login(rate_key)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    username = payload.username.strip()
    clear_failed_logins(rate_key)
    response = JSONResponse({"configured": True, "authenticated": True, "username": username})
    set_session_cookie(response, username, config)
    return response


@app.post("/api/auth/logout")
async def logout() -> JSONResponse:
    secure = False
    if is_auth_configured():
        secure = load_auth_config().cookie_secure
    response = JSONResponse({"configured": is_auth_configured(), "authenticated": False, "username": None})
    clear_session_cookie(response, secure=secure)
    return response


@app.post("/api/runs")
async def create_run_endpoint(
    names_text: str = Form(""),
    file: UploadFile | None = File(None),
    _: str = Depends(require_user),
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
async def get_run_endpoint(run_id: str, _: str = Depends(require_user)) -> dict:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@app.get("/api/runs/{run_id}/results/{result_id}/pdf")
async def download_pdf(
    run_id: str,
    result_id: int,
    _: str = Depends(require_user),
) -> FileResponse:
    result = get_result(run_id, result_id)
    if not result or not result.get("pdf_path"):
        raise HTTPException(status_code=404, detail="PDF not found.")
    path = resolve_storage_path(str(result["pdf_path"]))
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file is missing from storage.")
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@app.get("/api/runs/{run_id}/zip")
async def download_zip(run_id: str, _: str = Depends(require_user)) -> FileResponse:
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
