"""Additional persistence-safety tests for ConfigManager."""

import json
from pathlib import Path
import pytest

from app.config_manager import ConfigManager
import app.config_manager as config_module


def test_atomic_save_uses_a_temporary_file_in_the_target_directory(
    tmp_path, monkeypatch
):
    data_dir = tmp_path / "data"
    manager = ConfigManager(str(data_dir))
    real_replace = config_module.os.replace
    observed = {}

    def recording_replace(source, destination):
        observed["source"] = Path(source)
        observed["destination"] = Path(destination)
        return real_replace(source, destination)

    monkeypatch.setattr(config_module.os, "replace", recording_replace)
    manager.set_current_provider("LongCat")

    assert observed["source"].parent == data_dir
    assert observed["source"].suffix == ".tmp"
    assert observed["destination"] == data_dir / "config.json"
    assert json.loads((data_dir / "config.json").read_text(encoding="utf-8"))[
        "current_provider"
    ] == "LongCat"


def test_failed_replace_preserves_previous_file_and_removes_temp_file(
    tmp_path, monkeypatch
):
    data_dir = tmp_path / "data"
    manager = ConfigManager(str(data_dir))
    config_file = data_dir / "config.json"
    original_bytes = config_file.read_bytes()
    manager.config["current_provider"] = "uncommitted-value"

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(config_module.os, "replace", fail_replace)
    with pytest.raises(IOError):
        manager._save_config()

    assert config_file.read_bytes() == original_bytes
    assert list(data_dir.glob("*.tmp")) == []
