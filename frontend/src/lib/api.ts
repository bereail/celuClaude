// En produccion el backend sirve el build de este frontend desde su propio
// origen (ver backend/app/main.py), asi que el caso normal es "mismo origen,
// sin configurar nada" -- funciona igual detras del tunel de Cloudflare, en
// la LAN, o abriendo el build local. VITE_API_BASE es solo para `npm run dev`,
// donde Vite corre en un puerto distinto al backend.
const API_BASE = import.meta.env.VITE_API_BASE ?? window.location.origin;
const WS_BASE = API_BASE.replace(/^http/, "ws");

export function getToken(): string | null {
  return localStorage.getItem("access_token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("access_token", token);
  else localStorage.removeItem("access_token");
}

// Selección de PC/proyecto: preferencia puramente local de este celular, no
// tiene sentido guardarla en el backend (cada dispositivo del usuario podría
// querer mirar un proyecto distinto).
export function getSelection(): { deviceId: string | null; projectId: string | null } {
  return {
    deviceId: localStorage.getItem("selected_device_id"),
    projectId: localStorage.getItem("selected_project_id"),
  };
}

export function setSelection(deviceId: string | null, projectId: string | null) {
  if (deviceId) localStorage.setItem("selected_device_id", deviceId);
  else localStorage.removeItem("selected_device_id");
  if (projectId) localStorage.setItem("selected_project_id", projectId);
  else localStorage.removeItem("selected_project_id");
}

let onUnauthorized: (() => void) | null = null;

// App.tsx llama esto una vez al montar, para poder reaccionar (forzar
// logout) cuando cualquier llamada REST -- no solo el WebSocket -- descubre
// que el token vencio o es invalido.
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401 && path !== "/auth/login") {
      setToken(null);
      onUnauthorized?.();
    }
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  listProjects: () => request("/projects"),
  createProject: (payload: { name: string; path: string; description?: string; technologies?: string }) =>
    request("/projects", { method: "POST", body: JSON.stringify(payload) }),
  listDevices: () => request("/devices"),
  createSession: (payload: { project_id?: string | null; title?: string; autonomy_level?: number }) =>
    request("/sessions", { method: "POST", body: JSON.stringify(payload) }),
  listSessions: () => request("/sessions"),
  getMessages: (sessionId: string) => request(`/sessions/${sessionId}/messages`),
  getActions: (sessionId: string) => request(`/sessions/${sessionId}/actions`),
  sendInstruction: (sessionId: string, deviceId: string, text: string) =>
    request(`/sessions/${sessionId}/instruct`, {
      method: "POST",
      body: JSON.stringify({ device_id: deviceId, text }),
    }),
  decideAction: (actionId: string, decision: "approved" | "denied" | "always") =>
    request(`/actions/${actionId}/decision`, { method: "POST", body: JSON.stringify({ decision }) }),
  explainAction: (actionId: string, question: string) =>
    request<{ answer: string }>(`/actions/${actionId}/explain`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
};

export interface MobileSocketHandle {
  close: () => void;
  send: (payload: object) => void;
}

/**
 * Auth happens over the first message (not the URL query string) so the JWT
 * never lands in a proxy/access-log line. Reconnects with backoff on drop —
 * without this, a phone that loses signal for a few seconds silently stops
 * receiving activity updates until the page is reloaded.
 */
const AUTH_FAILURE_CLOSE_CODE = 4401;

export function connectMobileSocket(
  onEvent: (event: any) => void,
  onConnectionChange?: (connected: boolean) => void,
  onAuthFailure?: () => void
): MobileSocketHandle {
  let closedByCaller = false;
  let backoff = 1000;
  let ws: WebSocket | null = null;

  const connect = () => {
    const token = getToken();
    if (!token || closedByCaller) return;

    ws = new WebSocket(`${WS_BASE}/ws/mobile`);

    ws.onopen = () => {
      ws?.send(JSON.stringify({ type: "auth", token }));
    };

    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data);
        if (event.type === "authenticated") {
          backoff = 1000;
          onConnectionChange?.(true);
          return;
        }
        onEvent(event);
      } catch {
        /* ignore malformed frame */
      }
    };

    ws.onclose = (closeEvent) => {
      onConnectionChange?.(false);
      if (closedByCaller) return;
      if (closeEvent.code === AUTH_FAILURE_CLOSE_CODE) {
        // El token esta vencido o es invalido: reintentar con el mismo
        // token solo produciria un loop infinito de "reconectando...".
        // Forzamos logout para que la persona vuelva a entrar.
        closedByCaller = true;
        setToken(null);
        onAuthFailure?.();
        return;
      }
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 15000);
    };

    ws.onerror = () => ws?.close();
  };

  connect();

  return {
    close: () => {
      closedByCaller = true;
      ws?.close();
    },
    send: (payload: object) => {
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
      // si no esta conectado en este instante, se pierde -- es una
      // suscripcion de "estoy mirando ahora", no un comando que deba
      // persistir; al reconectar el usuario simplemente re-entra a la pestana.
    },
  };
}
