import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import remote_control


FAKE_MONITOR = {"left": 100, "top": 50, "width": 1000, "height": 500}


def test_fractional_to_absolute_maps_center():
    assert remote_control.fractional_to_absolute(0.5, 0.5, FAKE_MONITOR) == (600, 300)


def test_fractional_to_absolute_maps_corners():
    assert remote_control.fractional_to_absolute(0.0, 0.0, FAKE_MONITOR) == (100, 50)
    assert remote_control.fractional_to_absolute(1.0, 1.0, FAKE_MONITOR) == (1100, 550)


def test_fractional_to_absolute_clamps_out_of_range():
    # un cliente desprolijo (o malicioso) mandando fracciones fuera de
    # [0,1] no debe poder mover el mouse fuera del monitor capturado
    assert remote_control.fractional_to_absolute(-0.5, 2.0, FAKE_MONITOR) == (100, 550)


def test_click_raises_when_disabled_in_config():
    with pytest.raises(remote_control.RemoteControlDisabled):
        remote_control.click(0.5, 0.5, "left", {"remote_control_enabled": False})


def test_click_calls_pyautogui_with_mapped_coords(monkeypatch):
    calls = []
    monkeypatch.setattr(remote_control, "get_capture_monitor", lambda: FAKE_MONITOR)
    monkeypatch.setattr(remote_control.pyautogui, "moveTo", lambda x, y: calls.append(("move", x, y)))
    monkeypatch.setattr(remote_control.pyautogui, "click", lambda x, y, button: calls.append(("click", x, y, button)))
    monkeypatch.setattr(remote_control, "_audit", lambda line: None)

    result = remote_control.click(0.25, 0.75, "right", {"remote_control_enabled": True})

    assert result == {"x": 350, "y": 425, "button": "right"}
    assert calls == [("move", 350, 425), ("click", 350, 425, "right")]


def test_click_defaults_invalid_button_to_left(monkeypatch):
    monkeypatch.setattr(remote_control, "get_capture_monitor", lambda: FAKE_MONITOR)
    monkeypatch.setattr(remote_control.pyautogui, "moveTo", lambda x, y: None)
    clicked = {}
    monkeypatch.setattr(remote_control.pyautogui, "click", lambda x, y, button: clicked.update(button=button))
    monkeypatch.setattr(remote_control, "_audit", lambda line: None)

    remote_control.click(0.5, 0.5, "middle", {"remote_control_enabled": True})

    assert clicked["button"] == "left"
