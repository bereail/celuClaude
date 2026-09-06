# Claude Command Center

[![tests](https://github.com/bereail/celuClaude/actions/workflows/tests.yml/badge.svg)](https://github.com/bereail/celuClaude/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Centro de comando remoto para dirigir y supervisar a Claude trabajando en tu propia computadora, desde el celular — no es un chatbot, es un panel de control con streaming de actividad, permisos y auditoría.

```
CELULAR (PWA)  <--HTTPS/WSS-->  BACKEND (FastAPI)  <--WSS-->  AGENTE LOCAL (PC)
                                      |
                                 Anthropic API (Claude)
```

Ver el análisis completo de arquitectura (comparación de 4 opciones y por qué se eligió esta) en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Por qué existe

Mandar una instrucción desde el celular ("analizá el proyecto del turnero y buscá errores") y ver en tiempo real qué archivos abre Claude, qué comandos corre y qué encontró — con la posibilidad de aprobar o frenar cualquier acción sensible antes de que se ejecute en tu PC.

## Qué hay implementado (MVP de esta sesión)

- **Backend** (`backend/`): FastAPI + WebSockets, auth JWT, SQLite, orquestación de Claude con *tool use* (`list_dir`, `read_file`, `write_file`, `run_command`), motor de permisos (ALLOW / CONFIRM / DENY), audit log de cada acción.
- **Agente local** (`agent/`): cliente WebSocket que solo hace conexiones **salientes** (nunca expone un puerto), re-valida permisos de forma independiente antes de tocar el filesystem o una shell, reporta CPU/RAM y actividad en tiempo real, y transmite el espejo de pantalla (screenshots frecuentes, sin reenviar cuadros idénticos) **solo mientras alguien lo está mirando desde el celular** — no gasta CPU/batería/datos transmitiendo a nadie.
- **Frontend móvil** (`frontend/`): PWA React + TypeScript + Tailwind, dark mode, chat + entrada por voz (Web Speech API), Activity Stream en vivo, tarjeta de estado de la PC, modal de autorización (Denegar / Permitir una vez / Permitir siempre), toggle Actividad ↔ Espejo de pantalla.
- **Seguridad**: el celular nunca ve la API key de Anthropic ni le habla directo al agente; toda acción pasa por el motor de permisos en el backend y se vuelve a validar en el agente (defensa en profundidad); rutas con `.env`, `credentials`, `.pem`, `id_rsa`, cookies, etc. están bloqueadas por patrón sin excepción.

## Qué queda de roadmap explícito (no implementado todavía)

| Fase del pedido original | Estado |
|---|---|
| Streaming de pantalla en vivo | ✅ Mejorado (Prioridad 3) — espejo de pantalla con varios cuadros/seg, activado solo mientras se está mirando. WebRTC evaluado y descartado por ahora: requeriría un TURN server (pago) para funcionar de forma confiable en redes con NAT/CGNAT — ver `docs/ARCHITECTURE.md` sección 5. |
| Control remoto de mouse (click) | ✅ Hecho — tocar el espejo de pantalla mueve el mouse y hace click ahí; mantener apretado hace click derecho. Interruptor maestro `remote_control_enabled` en `config.yaml` del agente (default `false`), y solo actúa mientras alguien está efectivamente mirando esa pantalla. Ver [`agent/remote_control.py`](agent/remote_control.py). Falta: teclado, drag, scroll |
| Modo autónomo con niveles 0-3 y checkpoints de plan | Roadmap — hoy el `autonomy_level` se guarda en la sesión pero el orquestador siempre pide confirmación según el motor de permisos, no hay "modo autónomo dentro de límites" todavía |
| Modo Explicar | ✅ Hecho — preguntas sobre una acción puntual ya ejecutada (qué hizo, por qué, cómo explicarlo en una entrevista), sin acceso a herramientas ni al filesystem; ver [`backend/app/explain.py`](backend/app/explain.py) y [`frontend/src/components/ActionsPanel.tsx`](frontend/src/components/ActionsPanel.tsx) |
| Modo Entrevista / Modo Freelance | Roadmap — son prompts especializados sobre la misma arquitectura, no requieren cambios estructurales |
| Notificaciones push reales (celular cerrado) | Roadmap — requiere un service worker + push provider (FCM/Web Push); hoy la actividad solo llega si la PWA está conectada por WebSocket |
| Historial completo con reapertura de sesiones pausadas | Parcial — las sesiones y mensajes ya se persisten en SQLite; falta la UI de "volver a entrar y ver qué pasó mientras no estabas" |
| Registro de múltiples PCs / múltiples proyectos por PC | ✅ Hecho (Prioridad 1) — selector explícito en el celular, ver [`frontend/src/components/PickerSheet.tsx`](frontend/src/components/PickerSheet.tsx) |
| Acceso remoto fuera de la LAN, con HTTPS/WSS | ✅ Hecho (Prioridad 2) — Cloudflare Tunnel, ver [`docs/REMOTE_ACCESS.md`](docs/REMOTE_ACCESS.md) |
| Testing automatizado | Parcial — ver sección [Tests](#tests) más abajo. Corre en CI en cada push. No cubre componentes React ni flujos end-to-end |
| Revocación de dispositivos desde la UI | Roadmap |

## Puesta en marcha (desarrollo local)

### 1. Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate       # Windows
pip install -r requirements.txt
copy .env.example .env
copy permissions.example.yaml permissions.yaml
python scripts/hash_password.py "tu-contraseña"        # pegar el hash en .env -> APP_USER_PASSWORD_HASH
# completar ANTHROPIC_API_KEY, JWT_SECRET y AGENT_ENROLLMENT_TOKEN en .env
uvicorn app.main:app --reload
```

Backend corriendo en `http://localhost:8000` (health check en `/health`).

### 2. Agente local (en la PC que querés que Claude use)

```bash
cd agent
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy config.example.yaml config.yaml
# editar allowed_roots, enrollment_token (igual al del backend) y server_url
python agent.py
```

### 3. Frontend (PWA)

Para desarrollo, con hot-reload:

```bash
cd frontend
npm install
copy .env.example .env    # VITE_API_BASE=http://localhost:8000
npm run dev
```

Abrir `http://localhost:5173` desde el celular (misma red Wi-Fi que la PC, usando la IP local en vez de `localhost`).

Para uso real (recomendado incluso en casa): compilar el frontend y dejar que el **backend lo sirva directamente** desde su propio origen — así hay una sola URL para todo, sin CORS y sin coordinar dos puertos:

```bash
cd frontend
npm run build     # genera frontend/dist
```

Con eso ya alcanza — `backend/app/main.py` detecta `frontend/dist` y lo sirve automáticamente en `/`. Reiniciá el backend después de compilar.

### 4. Acceso remoto (fuera de tu red Wi-Fi)

Ver [`docs/REMOTE_ACCESS.md`](docs/REMOTE_ACCESS.md) — Cloudflare Tunnel, gratis, sin abrir puertos, con HTTPS/WSS automático y checklist de seguridad antes de dejarlo expuesto de forma permanente.

## Seguridad — decisiones concretas

- El agente **nunca escucha** en un puerto: solo abre una conexión saliente por WebSocket hacia el backend. No hay superficie de ataque expuesta en la PC.
- Cada acción de Claude pasa dos veces por el motor de permisos: una vez en el backend (antes de siquiera preguntar al usuario) y otra vez en el agente (antes de tocar el disco). Si el backend fuera comprometido, el agente igual filtra.
- Tres niveles: **DENY** (secretos, fuera de directorio autorizado — nunca, ni con confirmación), **CONFIRM** (requiere aprobación explícita desde el celular, con "permitir siempre" auditable), **ALLOW** (allowlist explícita de binarios).
- JWT de acceso de vida corta + refresh token; el token del agente (`enrollment_token`) es distinto del token de usuario del celular — comprometer uno no compromete el otro.
- Toda acción queda en `action_log` con decisión, resultado y timestamp — audit log completo, no borrable desde la UI.

## Tests

```bash
cd backend && pytest tests/ -v      # motor de permisos, JWT, login/rate-limit, seguridad del click remoto por WS
cd agent && pytest tests/ -v        # motor de permisos del agente, mapeo de coordenadas del control remoto
cd frontend && npm test             # manejo de errores de la capa de API (vitest)
```

Corren automáticamente en cada push vía GitHub Actions ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)). No cubren componentes React ni flujos end-to-end todavía — ver la tabla de roadmap para el detalle de qué falta.

## Stack y por qué

Ver la tabla completa de comparación de arquitecturas y stack en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Resumen: FastAPI + WebSockets (async nativo, mismo lenguaje que el agente), SQLite vía SQLAlchemy (cero infra para uso personal, migrable a Postgres), React + Vite + TS + Tailwind como PWA (una sola base de código instalable en el celular), Web Speech API para voz (cero costo, cero infraestructura extra), Anthropic API con *tool use* para que sea el propio modelo el que decida qué acción tomar.

## Funcionalidades propuestas — triage

**Imprescindibles para MVP** (implementadas): chat + voz, activity stream, terminal/comandos vía `run_command`, permisos con confirmación, estado online/offline, audit log.

**Muy útiles** (roadmap corto): selector de proyecto/device en la UI, notificaciones push reales, reapertura de sesión con resumen de "qué pasó mientras no estabas", modo Explicar (pedirle a Claude que explique en lenguaje simple lo que acaba de hacer — es un prompt, no requiere infraestructura nueva).

**Futuras**: espejo de pantalla en video (WebRTC), teclado/drag/scroll remoto, modo autónomo por niveles con checkpoints de plan, modo Entrevista, modo Freelance.

## Por qué es un buen proyecto de portfolio

Demuestra: diseño de arquitectura distribuida con justificación explícita (no "porque sí"), WebSockets bidireccionales en tiempo real, integración real con *tool use* de un LLM (no solo un wrapper de chat), un modelo de permisos y seguridad pensado en capas (defensa en profundidad, no solo "confío en el backend"), y una app full-stack con mobile-first UI. Un entrevistador técnico probablemente pregunte: por qué WebSockets y no WebRTC para el streaming, cómo se evita que el agente ejecute algo destructivo, qué pasa si el backend se cae en medio de una tarea, y cómo escalaría esto a más de un usuario — las respuestas a las tres primeras ya están en `docs/ARCHITECTURE.md` y en el código de permisos; la última es honestamente el punto más débil del MVP actual (todo está diseñado single-user) y vale la pena tenerlo presente como próxima iteración.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
