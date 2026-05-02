from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import RUNS_DIR, STORAGE_DIR


_lock = threading.Lock()
ACTIVE_RUN_STATUSES = {"queued", "running"}
ACTIVE_RESULT_STATUSES = {"pending", "checking"}
TERMINAL_RESULT_STATUSES = {"no_hit", "hit_found", "error"}


def init_store() -> None:
    STORAGE_DIR.mkdir(exist_ok=True)
    RUNS_DIR.mkdir(exist_ok=True)
    recover_interrupted_runs()


def recover_interrupted_runs() -> None:
    with _lock:
        for manifest in RUNS_DIR.glob("*/run.json"):
            run = _read_run_unlocked(manifest.parent.name)
            if not run:
                continue
            changed = False
            if run["status"] in ACTIVE_RUN_STATUSES:
                run["status"] = "error"
                changed = True
            for result in run.get("results", []):
                if result["status"] in ACTIVE_RESULT_STATUSES:
                    result["status"] = "error"
                    result["error_message"] = "Server restarted before this check completed."
                    result["completed_at"] = _now()
                    changed = True
            if changed:
                _recalculate_counts(run)
                _write_run_unlocked(run)


def create_run(names: list[str]) -> dict[str, Any]:
    with _lock:
        run_id = _new_run_id()
        run = {
            "id": run_id,
            "created_at": _now(),
            "updated_at": _now(),
            "status": "queued",
            "total_count": len(names),
            "completed_count": 0,
            "hit_count": 0,
            "no_hit_count": 0,
            "error_count": 0,
            "results": [
                {
                    "id": idx + 1,
                    "run_id": run_id,
                    "position": idx,
                    "name": name,
                    "status": "pending",
                    "result_text": None,
                    "pdf_path": None,
                    "error_message": None,
                    "started_at": None,
                    "completed_at": None,
                }
                for idx, name in enumerate(names)
            ],
        }
        _write_run_unlocked(run)
        return run


def get_run(run_id: str) -> dict[str, Any] | None:
    with _lock:
        return _read_run_unlocked(run_id)


def get_result(run_id: str, result_id: int) -> dict[str, Any] | None:
    run = get_run(run_id)
    if not run:
        return None
    return next((result for result in run["results"] if int(result["id"]) == result_id), None)


def get_results_for_run(run_id: str) -> list[dict[str, Any]]:
    run = get_run(run_id)
    return list(run["results"]) if run else []


def update_run_status(run_id: str, status: str) -> None:
    with _lock:
        run = _read_required_run_unlocked(run_id)
        run["status"] = status
        run["updated_at"] = _now()
        _write_run_unlocked(run)


def mark_result_checking(run_id: str, result_id: int) -> None:
    with _lock:
        run = _read_required_run_unlocked(run_id)
        result = _find_required_result(run, result_id)
        result["status"] = "checking"
        result["started_at"] = _now()
        result["error_message"] = None
        _recalculate_counts(run)
        _write_run_unlocked(run)


def complete_result(
    run_id: str,
    result_id: int,
    status: str,
    result_text: str | None = None,
    pdf_path: Path | None = None,
    error_message: str | None = None,
) -> None:
    rel_pdf = str(pdf_path.relative_to(STORAGE_DIR)) if pdf_path else None
    with _lock:
        run = _read_required_run_unlocked(run_id)
        result = _find_required_result(run, result_id)
        result["status"] = status
        result["result_text"] = result_text
        result["pdf_path"] = rel_pdf
        result["error_message"] = error_message
        result["completed_at"] = _now()
        _recalculate_counts(run)
        _write_run_unlocked(run)


def finish_run(run_id: str) -> None:
    with _lock:
        run = _read_required_run_unlocked(run_id)
        run["status"] = "completed_with_errors" if run["error_count"] else "completed"
        run["updated_at"] = _now()
        _write_run_unlocked(run)


def resolve_storage_path(relative_path: str) -> Path:
    candidate = (STORAGE_DIR / relative_path).resolve()
    storage_root = STORAGE_DIR.resolve()
    if storage_root not in candidate.parents and candidate != storage_root:
        raise ValueError("Invalid storage path")
    return candidate


def _new_run_id() -> str:
    base = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_id = base
    suffix = 1
    while (RUNS_DIR / run_id).exists():
        suffix += 1
        run_id = f"{base}-{suffix}"
    return run_id


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _manifest_path(run_id: str) -> Path:
    return RUNS_DIR / run_id / "run.json"


def _read_run_unlocked(run_id: str) -> dict[str, Any] | None:
    path = _manifest_path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_required_run_unlocked(run_id: str) -> dict[str, Any]:
    run = _read_run_unlocked(run_id)
    if not run:
        raise ValueError(f"Unknown run {run_id}")
    return run


def _write_run_unlocked(run: dict[str, Any]) -> None:
    run["updated_at"] = _now()
    run_dir = RUNS_DIR / str(run["id"])
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run.json"
    tmp_path = run_dir / "run.tmp"
    tmp_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _find_required_result(run: dict[str, Any], result_id: int) -> dict[str, Any]:
    for result in run["results"]:
        if int(result["id"]) == result_id:
            return result
    raise ValueError(f"Unknown result {result_id}")


def _recalculate_counts(run: dict[str, Any]) -> None:
    results = run.get("results", [])
    run["total_count"] = len(results)
    run["completed_count"] = sum(1 for result in results if result["status"] in TERMINAL_RESULT_STATUSES)
    run["hit_count"] = sum(1 for result in results if result["status"] == "hit_found")
    run["no_hit_count"] = sum(1 for result in results if result["status"] == "no_hit")
    run["error_count"] = sum(1 for result in results if result["status"] == "error")
