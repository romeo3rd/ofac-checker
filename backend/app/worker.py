from __future__ import annotations

import asyncio
from datetime import datetime

from .config import RUNS_DIR
from .store import (
    complete_result,
    finish_run,
    get_results_for_run,
    mark_result_checking,
    update_run_status,
)
from .ofac import OfacClient, safe_filename_part


_run_lock = asyncio.Lock()


async def run_batch(run_id: str) -> None:
    async with _run_lock:
        update_run_status(run_id, "running")
        results = get_results_for_run(run_id)
        run_dir = RUNS_DIR / str(run_id)
        today = datetime.now().strftime("%m%d%Y")
        try:
            async with OfacClient() as client:
                for result in results:
                    result_id = int(result["id"])
                    name = str(result["name"])
                    mark_result_checking(run_id, result_id)
                    pdf_name = f"{int(result['position']) + 1:03d}-OFAC {safe_filename_part(name)} {today}.pdf"
                    pdf_path = run_dir / pdf_name
                    try:
                        ofac_result = await client.search(name, pdf_path)
                        complete_result(
                            run_id,
                            result_id,
                            status=ofac_result.status,
                            result_text=ofac_result.result_text,
                            pdf_path=ofac_result.pdf_path,
                        )
                    except Exception as exc:
                        complete_result(
                            run_id,
                            result_id,
                            status="error",
                            error_message=str(exc),
                        )
        except Exception as exc:
            for result in get_results_for_run(run_id):
                if result["status"] in {"pending", "checking"}:
                    complete_result(
                        run_id,
                        int(result["id"]),
                        status="error",
                        error_message=f"Batch failed before this check completed: {exc}",
                    )
        finally:
            finish_run(run_id)
