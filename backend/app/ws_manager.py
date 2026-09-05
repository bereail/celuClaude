"""Realtime hub: routes messages between mobile clients and PC agents,
and bridges the async "wait for human approval" step in the orchestrator.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from fastapi import WebSocket


@dataclass
class Hub:
    mobile_clients: dict[str, WebSocket] = field(default_factory=dict)
    agent_connections: dict[str, WebSocket] = field(default_factory=dict)
    # request_id -> Future resolved with the agent's result dict
    pending_agent_calls: dict[str, asyncio.Future] = field(default_factory=dict)
    # device_id -> set of request_ids currently in flight against that device,
    # so we can fail them fast (instead of waiting out the full timeout) if
    # the agent drops mid-call.
    pending_by_device: dict[str, set[str]] = field(default_factory=dict)
    # action_log_id -> Future resolved with "approved" | "denied" | "always"
    pending_approvals: dict[str, asyncio.Future] = field(default_factory=dict)
    # device_id -> True while an instruction is being processed against it,
    # so two instructions can't be dispatched to the same PC concurrently.
    busy_devices: set[str] = field(default_factory=set)
    # device_id -> set of user_ids currently watching the screen mirror, so
    # the agent only captures/sends frames while someone is actually looking
    # (no punto en gastar CPU/batería/datos transmitiendo a nadie).
    screen_subscribers: dict[str, set[str]] = field(default_factory=dict)

    # ---- mobile side ----
    def register_mobile(self, user_id: str, ws: WebSocket) -> None:
        self.mobile_clients[user_id] = ws

    def unregister_mobile(self, user_id: str) -> None:
        self.mobile_clients.pop(user_id, None)

    async def broadcast_to_mobile(self, event: dict) -> None:
        dead = []
        for user_id, ws in self.mobile_clients.items():
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                dead.append(user_id)
        for user_id in dead:
            self.unregister_mobile(user_id)

    # ---- agent side ----
    def register_agent(self, device_id: str, ws: WebSocket) -> None:
        self.agent_connections[device_id] = ws
        self.pending_by_device.setdefault(device_id, set())

    def unregister_agent(self, device_id: str) -> None:
        self.agent_connections.pop(device_id, None)
        # Fail-fast: don't make the orchestrator wait out a 120s timeout to
        # find out the agent is gone.
        for request_id in self.pending_by_device.pop(device_id, set()):
            future = self.pending_agent_calls.get(request_id)
            if future and not future.done():
                future.set_exception(ConnectionError("El agente se desconecto mientras se ejecutaba la accion."))

    def is_agent_online(self, device_id: str) -> bool:
        return device_id in self.agent_connections

    def is_device_busy(self, device_id: str) -> bool:
        return device_id in self.busy_devices

    def mark_busy(self, device_id: str) -> None:
        self.busy_devices.add(device_id)

    def mark_free(self, device_id: str) -> None:
        self.busy_devices.discard(device_id)

    async def send_to_agent(self, device_id: str, payload: dict) -> None:
        ws = self.agent_connections.get(device_id)
        if not ws:
            raise ConnectionError(f"Agente {device_id} no esta conectado.")
        await ws.send_text(json.dumps(payload))

    async def call_agent(self, device_id: str, request_id: str, payload: dict, timeout: float = 120.0) -> dict:
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self.pending_agent_calls[request_id] = future
        self.pending_by_device.setdefault(device_id, set()).add(request_id)
        try:
            await self.send_to_agent(device_id, payload)
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.pending_agent_calls.pop(request_id, None)
            self.pending_by_device.get(device_id, set()).discard(request_id)

    def resolve_agent_call(self, request_id: str, result: dict) -> None:
        future = self.pending_agent_calls.get(request_id)
        if future and not future.done():
            future.set_result(result)

    # ---- approvals ----
    async def wait_for_approval(self, action_log_id: str, timeout: float = 900.0) -> str:
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self.pending_approvals[action_log_id] = future
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.pending_approvals.pop(action_log_id, None)

    def resolve_approval(self, action_log_id: str, decision: str) -> bool:
        """Returns False if there was no live approval waiting on this id
        (already resolved, timed out, or backend restarted since it was raised)."""
        future = self.pending_approvals.get(action_log_id)
        if future and not future.done():
            future.set_result(decision)
            return True
        return False

    # ---- espejo de pantalla ----
    def subscribe_screen(self, device_id: str, user_id: str) -> bool:
        """Returns True if this is the first subscriber for that device
        (backend should tell the agent to start capturing)."""
        subs = self.screen_subscribers.setdefault(device_id, set())
        was_empty = len(subs) == 0
        subs.add(user_id)
        return was_empty

    def unsubscribe_screen(self, device_id: str, user_id: str) -> bool:
        """Returns True if this was the last subscriber for that device
        (backend should tell the agent to stop capturing)."""
        subs = self.screen_subscribers.get(device_id)
        if not subs or user_id not in subs:
            return False
        subs.discard(user_id)
        return len(subs) == 0

    def unsubscribe_screen_everywhere(self, user_id: str) -> list[str]:
        """Called on mobile disconnect. Returns the device_ids that just lost
        their last subscriber (backend should tell those agents to stop)."""
        emptied = []
        for device_id, subs in self.screen_subscribers.items():
            if user_id in subs:
                subs.discard(user_id)
                if not subs:
                    emptied.append(device_id)
        return emptied


hub = Hub()
