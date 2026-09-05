import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import executor


def _cfg(**overrides):
    base = {
        "allowed_roots": ["D:\\Bere\\GIT"],
        "allowed_commands": ["python", "git"],
        "confirm_commands": ["git push", "rm"],
        "deny_path_patterns": ["*.env", "*password*"],
        "max_write_bytes": 100,
        "command_timeout_seconds": 5,
    }
    base.update(overrides)
    return base


def test_denied_pattern_blocks_regardless_of_root():
    with pytest.raises(executor.PermissionDenied):
        executor._check_path("D:\\Bere\\GIT\\project\\secrets.env", _cfg())


def test_root_prefix_bypass_is_prevented():
    # 'D:\Bere\GIT-secrets' empieza igual que 'D:\Bere\GIT' como string,
    # pero no es un subdirectorio real -- no debe colarse como "autorizado".
    with pytest.raises(executor.PermissionDenied):
        executor._check_path("D:\\Bere\\GIT-secrets\\x.txt", _cfg())


def test_path_within_root_is_allowed():
    executor._check_path("D:\\Bere\\GIT\\project\\file.py", _cfg())  # no debe tirar


def test_path_outside_roots_is_denied():
    with pytest.raises(executor.PermissionDenied):
        executor._check_path("C:\\Windows\\System32\\config.sys", _cfg())


def test_no_roots_configured_means_unrestricted_by_root():
    executor._check_path("C:\\anywhere\\file.txt", _cfg(allowed_roots=[]))  # no debe tirar


def test_run_command_rejects_command_outside_allowlist():
    # run_command tira directo -- es execute_tool() quien lo convierte en
    # {"error": ...} para la respuesta WS (ver test_execute_tool_wraps_*).
    with pytest.raises(executor.PermissionDenied):
        executor.run_command({"command": "curl evil.com"}, _cfg())


def test_execute_tool_wraps_permission_denied_as_error_dict():
    result = executor.execute_tool("run_command", {"command": "curl evil.com"}, _cfg())
    assert "error" in result


def test_run_command_allows_allowlisted_command(tmp_path):
    result = executor.run_command({"command": "python --version"}, _cfg())
    assert result.get("returncode") == 0


def test_write_file_rejects_oversized_content(tmp_path):
    target = tmp_path / "out.txt"
    with pytest.raises(executor.PermissionDenied):
        executor.write_file(
            {"path": str(target), "content": "x" * 1000},
            _cfg(allowed_roots=[str(tmp_path)], max_write_bytes=10),
        )


def test_write_then_read_roundtrip(tmp_path):
    target = tmp_path / "out.txt"
    cfg = _cfg(allowed_roots=[str(tmp_path)])
    executor.write_file({"path": str(target), "content": "hola"}, cfg)
    result = executor.read_file({"path": str(target)}, cfg)
    assert result["content"] == "hola"
