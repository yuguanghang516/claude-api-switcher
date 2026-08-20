"""Provider activation and credential-export safety regression tests."""

import json

import pytest

from app.config_manager import ConfigManager
from app.provider_manager import ProviderManager


def _manager(tmp_path):
    config = ConfigManager(str(tmp_path / "data"))
    return config, ProviderManager(config)


def test_export_never_reads_or_serializes_credential_store(tmp_path, monkeypatch):
    config, manager = _manager(tmp_path)

    def credential_access_is_forbidden(_provider_name):
        raise AssertionError("export must not read the credential store")

    monkeypatch.setattr(manager.cred, "get_api_key", credential_access_is_forbidden)
    destination = tmp_path / "export.json"

    ok, _ = manager.export_config(str(destination))

    assert ok is True
    serialized = destination.read_text(encoding="utf-8")
    exported = json.loads(serialized)
    assert "SENSITIVE_SENTINEL" not in serialized
    assert "api_key" not in serialized.lower()
    assert "auth_token" not in serialized.lower()
    assert exported["providers"][0]["name"] == config.get_providers()[0]["name"]
    assert "id" not in exported["providers"][0]


def test_untested_provider_cannot_be_activated(tmp_path, monkeypatch):
    config, manager = _manager(tmp_path)
    monkeypatch.setattr(
        manager.cred, "get_api_key", lambda _provider_name: "SENSITIVE_SENTINEL"
    )

    ok, _ = manager.set_current("LongCat")

    assert ok is False
    assert config.get_current_provider_name() == ""


def test_export_strips_accidentally_embedded_credential_fields(tmp_path):
    config, manager = _manager(tmp_path)
    config.get_provider("LongCat")["api_key"] = "SENSITIVE_SENTINEL"
    destination = tmp_path / "export.json"

    ok, _ = manager.export_config(str(destination))

    assert ok is True
    serialized = destination.read_text(encoding="utf-8")
    assert "SENSITIVE_SENTINEL" not in serialized
    assert "api_key" not in serialized.lower()
