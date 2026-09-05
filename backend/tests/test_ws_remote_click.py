"""El check de seguridad mas nuevo del backend: un remote_click solo se
relaya al agente si el usuario esta efectivamente suscripto al espejo de
pantalla de ESE device_id (ver routers/ws.py). Sin este check, cualquier
mobile client autenticado podria mover el mouse de un dispositivo cuya
pantalla ni siquiera esta mirando.
"""

from conftest import TEST_EMAIL, TEST_PASSWORD


def test_remote_click_requires_active_screen_subscription(client):
    with client.websocket_connect("/ws/agent") as agent_ws:
        agent_ws.send_json({"type": "hello", "name": "Test PC", "os": "Windows", "enrollment_token": "test-enrollment-token"})
        registered = agent_ws.receive_json()
        assert registered["type"] == "registered"
        device_id = registered["device_id"]

        token = client.post("/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}).json()["access_token"]

        with client.websocket_connect("/ws/mobile") as mobile_ws:
            mobile_ws.send_json({"type": "auth", "token": token})
            assert mobile_ws.receive_json()["type"] == "authenticated"

            # Sin suscripcion todavia: este click NO debe llegar al agente.
            mobile_ws.send_json({"type": "remote_click", "device_id": device_id, "x": 0.5, "y": 0.5, "button": "left"})

            # Nos suscribimos despues -- si el click de arriba se hubiera
            # relayado, llegaria ANTES que este mensaje (mismo orden en que
            # se procesan en el loop del agente), asi que verificar que lo
            # PRIMERO que llega es el screen_subscribe prueba que el click
            # sin suscripcion se descarto.
            mobile_ws.send_json({"type": "screen_subscribe", "device_id": device_id})
            first = agent_ws.receive_json()
            assert first == {"type": "screen_subscribe"}

            # Ahora si, con suscripcion activa, el click debe llegar tal cual.
            mobile_ws.send_json({"type": "remote_click", "device_id": device_id, "x": 0.25, "y": 0.75, "button": "right"})
            second = agent_ws.receive_json()
            assert second == {"type": "remote_click", "x": 0.25, "y": 0.75, "button": "right"}
