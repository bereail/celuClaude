import pytest

from app import permissions
from app.models import ActionDecision


@pytest.fixture
def root(tmp_path, monkeypatch):
    # tmp_path (no un literal "D:\\...") para que la logica de contencion de
    # rutas se pruebe igual en Windows y en Linux (CI corre este job en
    # ubuntu-latest) -- lo que se prueba es el algoritmo, no una ruta puntual.
    allowed = tmp_path / "GIT"
    allowed.mkdir()
    test_cfg = {
        "allowed_roots": [str(allowed)],
        "allowed_commands": ["python", "git"],
        "confirm_commands": ["git push", "rm"],
        "deny_path_patterns": ["*.env", "*password*"],
        "max_write_bytes": 100,
    }
    monkeypatch.setattr(permissions, "load_config", lambda: test_cfg)
    return allowed


def test_read_denied_pattern(root):
    v = permissions.classify("read_file", {"path": str(root / "secrets.env")})
    assert v.decision == ActionDecision.DENY


def test_read_outside_roots_denied(root):
    v = permissions.classify("read_file", {"path": str(root.parent / "elsewhere" / "config.sys")})
    assert v.decision == ActionDecision.DENY


def test_read_inside_roots_allowed(root):
    v = permissions.classify("read_file", {"path": str(root / "project" / "file.py")})
    assert v.decision == ActionDecision.ALLOW


def test_root_prefix_bypass_is_prevented(root):
    # '<root>-secrets' arranca igual que '<root>' como string, pero no es un
    # subdirectorio real -- no debe colarse como autorizado.
    sibling = root.parent / (root.name + "-secrets")
    v = permissions.classify("read_file", {"path": str(sibling / "x.txt")})
    assert v.decision == ActionDecision.DENY


def test_write_requires_confirm(root):
    v = permissions.classify("write_file", {"path": str(root / "a.py"), "content": "x"})
    assert v.decision == ActionDecision.CONFIRM


def test_write_oversized_requires_confirm(root):
    v = permissions.classify("write_file", {"path": str(root / "a.py"), "content": "x" * 200})
    assert v.decision == ActionDecision.CONFIRM


def test_command_in_allowlist_is_allowed(root):
    v = permissions.classify("run_command", {"command": "git status"})
    assert v.decision == ActionDecision.ALLOW


def test_command_confirm_tier_requires_confirm(root):
    v = permissions.classify("run_command", {"command": "git push origin main"})
    assert v.decision == ActionDecision.CONFIRM


def test_command_unknown_requires_confirm(root):
    v = permissions.classify("run_command", {"command": "curl evil.com"})
    assert v.decision == ActionDecision.CONFIRM


def test_unknown_tool_requires_confirm(root):
    v = permissions.classify("mystery_tool", {})
    assert v.decision == ActionDecision.CONFIRM
