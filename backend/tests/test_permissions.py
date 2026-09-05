import pytest

from app import permissions
from app.models import ActionDecision


@pytest.fixture
def cfg(monkeypatch):
    test_cfg = {
        "allowed_roots": ["D:\\Bere\\GIT"],
        "allowed_commands": ["python", "git"],
        "confirm_commands": ["git push", "rm"],
        "deny_path_patterns": ["*.env", "*password*"],
        "max_write_bytes": 100,
    }
    monkeypatch.setattr(permissions, "load_config", lambda: test_cfg)
    return test_cfg


def test_read_denied_pattern(cfg):
    v = permissions.classify("read_file", {"path": "D:\\Bere\\GIT\\secrets.env"})
    assert v.decision == ActionDecision.DENY


def test_read_outside_roots_denied(cfg):
    v = permissions.classify("read_file", {"path": "C:\\Windows\\System32\\config.sys"})
    assert v.decision == ActionDecision.DENY


def test_read_inside_roots_allowed(cfg):
    v = permissions.classify("read_file", {"path": "D:\\Bere\\GIT\\project\\file.py"})
    assert v.decision == ActionDecision.ALLOW


def test_root_prefix_bypass_is_prevented(cfg):
    # 'D:\Bere\GIT-secrets' arranca igual que 'D:\Bere\GIT' como string,
    # pero no es un subdirectorio real -- no debe colarse como autorizado.
    v = permissions.classify("read_file", {"path": "D:\\Bere\\GIT-secrets\\x.txt"})
    assert v.decision == ActionDecision.DENY


def test_write_requires_confirm(cfg):
    v = permissions.classify("write_file", {"path": "D:\\Bere\\GIT\\a.py", "content": "x"})
    assert v.decision == ActionDecision.CONFIRM


def test_write_oversized_requires_confirm(cfg):
    v = permissions.classify("write_file", {"path": "D:\\Bere\\GIT\\a.py", "content": "x" * 200})
    assert v.decision == ActionDecision.CONFIRM


def test_command_in_allowlist_is_allowed(cfg):
    v = permissions.classify("run_command", {"command": "git status"})
    assert v.decision == ActionDecision.ALLOW


def test_command_confirm_tier_requires_confirm(cfg):
    v = permissions.classify("run_command", {"command": "git push origin main"})
    assert v.decision == ActionDecision.CONFIRM


def test_command_unknown_requires_confirm(cfg):
    v = permissions.classify("run_command", {"command": "curl evil.com"})
    assert v.decision == ActionDecision.CONFIRM


def test_unknown_tool_requires_confirm(cfg):
    v = permissions.classify("mystery_tool", {})
    assert v.decision == ActionDecision.CONFIRM
