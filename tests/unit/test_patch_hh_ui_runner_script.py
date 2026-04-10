"""Tests for the one-off patch script safety."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


def test_importing_patch_script_has_no_file_system_side_effects() -> None:
    script_path = Path("C:/development/helpers/hh_bot/scripts/patch_hh_ui_runner.py")
    spec = importlib.util.spec_from_file_location("patch_hh_ui_runner_test", script_path)
    module = importlib.util.module_from_spec(spec)

    with (
        patch.object(Path, "read_text", side_effect=AssertionError("read_text should not run on import")),
        patch.object(Path, "write_text", side_effect=AssertionError("write_text should not run on import")),
    ):
        assert spec.loader is not None
        spec.loader.exec_module(module)

    assert hasattr(module, "build_patched_runner")
    assert hasattr(module, "main")
