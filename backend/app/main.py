from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import auth, projects, sessions, ws

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Claude Command Center API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # Permisivo a proposito: la autenticacion es por Bearer token (header
    # Authorization), no por cookies -- un origen malicioso no puede leer
    # el token de otra pestana solo por CORS, asi que esto no es la
    # superficie de ataque real aca (el JWT si lo es, y ya tiene expiracion
    # corta + el device token del agente por separado). En produccion el
    # frontend se sirve del mismo origen que el backend igual (ver abajo),
    # asi que CORS ni siquiera entra en juego en ese caso.
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(sessions.router)
app.include_router(ws.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Sirve el build de la PWA desde el mismo origen que la API, para que el
# tunel (Cloudflare Tunnel u otro) solo necesite exponer un puerto y una
# URL -- nada de CORS ni de coordinar dos origenes distintos en produccion.
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/manifest.json")
    def manifest():
        return FileResponse(_frontend_dist / "manifest.json")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request):
        # Cualquier ruta que no matcheo con los routers de arriba (auth,
        # projects, sessions, ws, /health, /assets) es una ruta del lado
        # cliente de React -- le devolvemos index.html y que React Router
        # (si lo hubiera) o el propio estado de la app decida que mostrar.
        return FileResponse(_frontend_dist / "index.html")
