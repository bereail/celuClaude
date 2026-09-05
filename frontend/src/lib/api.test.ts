import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, getToken, setToken } from "./api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("api request()", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON on success", async () => {
    (fetch as any).mockResolvedValue(jsonResponse({ access_token: "a", refresh_token: "b" }));
    const res = await api.login("bereail", "newton508");
    expect(res.access_token).toBe("a");
  });

  it("throws the backend's detail message on an HTTP error, not a generic one", async () => {
    (fetch as any).mockResolvedValue(jsonResponse({ detail: "Credenciales invalidas" }, 401));
    await expect(api.login("bereail", "wrong")).rejects.toThrow("Credenciales invalidas");
  });

  it("falls back to the raw body when the error response isn't JSON", async () => {
    (fetch as any).mockResolvedValue(new Response("Internal Server Error", { status: 500 }));
    await expect(api.login("bereail", "x")).rejects.toThrow("Internal Server Error");
  });

  // Este es exactamente el bug que causaba "credenciales invalidas" cuando en
  // realidad el fetch ni siquiera llegaba al servidor (URL de API rota,
  // celular sin conexion, etc.) -- request() debe distinguirlo de un 401 real.
  it("gives a distinct message when fetch itself fails (no response at all)", async () => {
    (fetch as any).mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.login("bereail", "newton508")).rejects.toThrow(/conectar/i);
  });

  it("attaches the stored bearer token to authenticated requests", async () => {
    setToken("my-token");
    (fetch as any).mockResolvedValue(jsonResponse([]));
    await api.listProjects();
    const [, init] = (fetch as any).mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer my-token");
  });

  it("clears the token and does not attach Authorization when logged out", async () => {
    setToken(null);
    (fetch as any).mockResolvedValue(jsonResponse([]));
    await api.listProjects();
    const [, init] = (fetch as any).mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
    expect(getToken()).toBeNull();
  });
});
