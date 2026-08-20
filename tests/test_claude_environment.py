import os
import subprocess

from app.claude_environment import (
    ClaudeEnvironmentManager,
    ClaudeEnvironmentStatus,
)


def test_detect_reports_working_install(monkeypatch, tmp_path):
    executable = tmp_path / "claude.exe"
    executable.write_bytes(b"stub")
    manager = ClaudeEnvironmentManager(str(tmp_path))
    monkeypatch.setattr(manager, "_candidate_installations", lambda include_path=True: [str(executable)])
    monkeypatch.setattr(
        manager,
        "_run",
        lambda command, timeout: subprocess.CompletedProcess(command, 0, "2.1.235 (Claude Code)\n", ""),
    )

    status = manager.detect()

    assert status.installed is True
    assert status.healthy is True
    assert status.version == "2.1.235 (Claude Code)"
    assert status.executable == str(executable)


def test_detect_warns_about_duplicate_installations(monkeypatch, tmp_path):
    first = tmp_path / "claude.exe"
    second = tmp_path / "claude.cmd"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    manager = ClaudeEnvironmentManager(str(tmp_path))
    monkeypatch.setattr(
        manager, "_candidate_installations", lambda include_path=True: [str(first), str(second)]
    )
    monkeypatch.setattr(
        manager,
        "_run",
        lambda command, timeout: subprocess.CompletedProcess(command, 0, "2.1.235 (Claude Code)", ""),
    )

    status = manager.detect()

    assert len(status.installations) == 2
    assert "多个" in status.warning


def test_install_prefers_winget_and_verifies(monkeypatch, tmp_path):
    manager = ClaudeEnvironmentManager(str(tmp_path))
    missing = ClaudeEnvironmentStatus(installed=False)
    installed = ClaudeEnvironmentStatus(
        installed=True,
        executable=str(tmp_path / "claude.exe"),
        version="2.1.235 (Claude Code)",
        healthy=True,
        install_method="winget",
    )
    states = iter([missing, installed])
    monkeypatch.setattr(manager, "detect", lambda run_doctor=False: next(states))
    monkeypatch.setattr(manager, "_which_executable", lambda *names: r"C:\winget.exe")
    monkeypatch.setattr(manager, "_activate_known_paths", lambda: None)
    commands = []

    def fake_run(command, timeout):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "Successfully installed", "")

    monkeypatch.setattr(manager, "_run", fake_run)

    result = manager.install()

    assert result.success is True
    assert result.code == "installed"
    assert commands[0][1:5] == ["install", "--id", "Anthropic.ClaudeCode", "--exact"]
    assert "版本检查通过" in result.steps


def test_install_failure_message_distinguishes_network_error():
    code, message = ClaudeEnvironmentManager._classify_failure(
        "Unable to connect to source: proxy failure", 1, "winget"
    )

    assert code == "network_error"
    assert "代理" in message


def test_install_failure_message_distinguishes_locked_file():
    code, message = ClaudeEnvironmentManager._classify_failure(
        "The process cannot access the file because it is being used", 32, "update"
    )

    assert code == "file_locked"
    assert "关闭 Claude" in message


def test_repair_path_updates_current_process_without_persisting(monkeypatch, tmp_path):
    executable = tmp_path / "claude.exe"
    executable.write_bytes(b"stub")
    manager = ClaudeEnvironmentManager(str(tmp_path))
    monkeypatch.setattr(
        manager, "_candidate_installations", lambda include_path=True: [str(executable)]
    )
    monkeypatch.setattr(
        manager,
        "detect",
        lambda run_doctor=False: ClaudeEnvironmentStatus(
            installed=True,
            executable=str(executable),
            version="2.1.235 (Claude Code)",
            healthy=True,
        ),
    )
    old_path = os.environ.get("PATH", "")
    try:
        result = manager.repair_path(persist=False)
        assert result.success is True
        assert os.environ["PATH"].split(os.pathsep)[0] == str(tmp_path)
    finally:
        os.environ["PATH"] = old_path


def test_native_installer_allowlist_is_restricted():
    from app.claude_environment import OFFICIAL_INSTALLER_HOSTS

    assert "claude.ai" in OFFICIAL_INSTALLER_HOSTS
    assert "downloads.claude.ai" in OFFICIAL_INSTALLER_HOSTS
    assert all(host.endswith("claude.ai") for host in OFFICIAL_INSTALLER_HOSTS)
