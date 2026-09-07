"""The "Add Years" modal must show "(no data)" -- not "(processing)" -- for
configured years the fetch produced nothing for, and leave them
re-selectable so the user can retry (user report, Gaza).
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SELECTOR_HTML = (ROOT / "public" / "viewport_selector.html").read_text()
VIEWPORTS_PY = (ROOT / "api" / "views" / "viewports.py").read_text()


def test_backend_reports_years_no_data():
    assert "def _pipeline_active(" in VIEWPORTS_PY
    assert "'years_no_data'" in VIEWPORTS_PY or '"years_no_data"' in VIEWPORTS_PY
    # only genuinely no-data when the pipeline is NOT live
    assert "_pipeline_active(viewport_name)" in VIEWPORTS_PY


@pytest.mark.parametrize("needle", [
    "vp.years_no_data",
    "(no data",          # the label the user sees
    "select to retry",   # re-selectable, not a dead end
])
def test_modal_renders_no_data_state(needle):
    assert needle in SELECTOR_HTML, f"viewport_selector.html should contain {needle!r}"


def test_no_data_year_is_not_locked():
    # A no-data year must be checkable again; only a still-processing
    # configured year is disabled.
    assert "const locked = isConfigured && !isNoData;" in SELECTOR_HTML
