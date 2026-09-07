"""_pipeline_active: is a viewport's data pipeline actually running?

Used by list_viewports to tell "still processing" apart from "processing
finished, this year has no coverage". A user report (Gaza) showed years
that never had embeddings stuck on "(processing)" forever because the
Add-Years modal had no way to know the pipeline had long finished.
"""

from __future__ import annotations

import json
import os
import time

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tee_project.settings")
import django  # noqa: E402

django.setup()

from api.views import viewports as vp  # noqa: E402


@pytest.fixture
def progress_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, "PROGRESS_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_tasks(monkeypatch):
    monkeypatch.setattr(vp, "tasks", {})


def _write_progress(progress_dir, name, status, age_seconds=0):
    pf = progress_dir / f"{name}_pipeline_progress.json"
    pf.write_text(json.dumps({"status": status, "message": "", "percent": 50}))
    if age_seconds:
        old = time.time() - age_seconds
        os.utime(pf, (old, old))
    return pf


def test_no_task_and_no_progress_file_is_not_active(progress_dir):
    assert vp._pipeline_active("gaza") is False


def test_running_task_is_active(progress_dir, monkeypatch):
    monkeypatch.setattr(vp, "tasks", {"gaza_full_pipeline": {"status": "in_progress"}})
    assert vp._pipeline_active("gaza") is True


def test_finished_task_is_not_active(progress_dir, monkeypatch):
    monkeypatch.setattr(vp, "tasks", {"gaza_full_pipeline": {"status": "completed"}})
    assert vp._pipeline_active("gaza") is False


def test_fresh_processing_progress_file_is_active(progress_dir):
    _write_progress(progress_dir, "gaza", "processing")
    assert vp._pipeline_active("gaza") is True


@pytest.mark.parametrize("status", ["complete", "error", "cancelled"])
def test_terminal_progress_file_is_not_active(progress_dir, status):
    _write_progress(progress_dir, "gaza", status)
    assert vp._pipeline_active("gaza") is False


def test_stale_progress_file_is_not_active(progress_dir):
    # A crashed pipeline can leave "processing" behind forever -- treat a
    # file untouched for >20 min as dead.
    _write_progress(progress_dir, "gaza", "processing", age_seconds=1300)
    assert vp._pipeline_active("gaza") is False
