from pathlib import Path

from backend.app import store


def use_temp_storage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(store, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")


def test_create_run_writes_manifest(tmp_path: Path, monkeypatch) -> None:
    use_temp_storage(tmp_path, monkeypatch)
    store.init_store()

    run = store.create_run(["Alice", "Bob Inc"])

    assert run["total_count"] == 2
    assert run["results"][0]["status"] == "pending"
    assert (tmp_path / "runs" / run["id"] / "run.json").exists()


def test_complete_result_updates_counts_and_pdf_path(tmp_path: Path, monkeypatch) -> None:
    use_temp_storage(tmp_path, monkeypatch)
    store.init_store()
    run = store.create_run(["Alice"])
    pdf_path = tmp_path / "runs" / run["id"] / "result.pdf"
    pdf_path.write_text("pdf", encoding="utf-8")

    store.complete_result(run["id"], 1, "no_hit", "Lookup Results: 0 Found", pdf_path)
    updated = store.get_run(run["id"])

    assert updated is not None
    assert updated["completed_count"] == 1
    assert updated["no_hit_count"] == 1
    assert updated["results"][0]["pdf_path"] == f"runs\\{run['id']}\\result.pdf"


def test_recover_interrupted_runs_marks_active_status_error(tmp_path: Path, monkeypatch) -> None:
    use_temp_storage(tmp_path, monkeypatch)
    store.init_store()
    run = store.create_run(["Alice"])
    store.update_run_status(run["id"], "running")
    store.mark_result_checking(run["id"], 1)

    store.recover_interrupted_runs()
    updated = store.get_run(run["id"])

    assert updated is not None
    assert updated["status"] == "error"
    assert updated["results"][0]["status"] == "error"
    assert updated["error_count"] == 1
