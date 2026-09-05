# Arquitectura — Claude Command Center

## 1. Opciones evaluadas

| | A. Celular→Backend→Claude→Agent | B. Celular→Claude→Agent directo | C. Celular→WS→Backend→Agent | D. WebRTC end-to-end |
|---|---|---|---|---|
| Seguridad | Alta (backend controla auth/permisos/audit) | Baja (celular necesita la API key de Anthropic o credenciales del agente) | Alta | Media (señalización sigue necesitando backend) |
| NAT / PC sin IP pública | OK (agent hace conexión saliente) | Requiere exponer el agent o usar relay igual | OK (agent hace conexión saliente) | Necesita STUN/TURN igual que backend |
| Latencia texto/comandos | Buena | Buena | Buena | Buena |
| Streaming de pantalla | Requiere pieza aparte | Requiere pieza aparte | Screenshots periódicos por WS (MVP) | Nativo, baja latencia (fase futura) |
| Complejidad de build | Media | Baja pero insegura | Media | Alta (SFU/TURN, señalización, NAT traversal) |
| Historial/memoria centralizada | Sí | No (viviría en el celular o el agent) | Sí | Sí (si hay backend igual) |
| Multi-dispositivo / notificaciones push | Fácil | Difícil | Fácil | Fácil (si hay backend) |

## 2. Decisión

**Arquitectura C, con el backend orquestando la llamada a Claude** (fusión de A y C): el celular nunca habla directo ni con Claude ni con el agent.

```
CELULAR (PWA)  <--HTTPS/WSS-->  BACKEND (FastAPI)  <--WSS-->  AGENTE LOCAL (PC)
                                      |
                                 Anthropic API (Claude)
```

Razones:
- El agente de la PC **solo hace conexiones salientes** (WSS hacia el backend) — nunca escucha en un puerto expuesto a Internet. Elimina el riesgo de exponer la PC directamente (ver punto 19 del pedido original).
- El backend es el único que guarda la API key de Anthropic, la lógica de permisos, el audit log y el historial — el celular y el agente son "tontos" en materia de secretos.
- Funciona detrás de cualquier NAT/router doméstico sin configurar port-forwarding.
- WebSockets es suficiente para texto, comandos y activity stream en tiempo real; para **Modo A (espejo de pantalla)** el MVP usa captura periódica de screenshots (JPEG, ~2 fps) sobre el mismo WebSocket — mucho más simple que WebRTC y suficiente para "ver qué está pasando". WebRTC (Opción D) queda en el roadmap para cuando se quiera video fluido con control de mouse/teclado en tiempo real.

## 3. Stack elegido

| Capa | Tecnología | Por qué |
|---|---|---|
| Backend | Python + FastAPI + `websockets` nativo de Starlette | Async nativo, tipado, mismo lenguaje que el agente y fácil integración con el SDK de Anthropic |
| DB | SQLite (SQLAlchemy) | Cero infraestructura para uso personal; el modelo ORM permite migrar a Postgres sin reescribir nada |
| Auth | JWT (access + refresh) + hash de contraseña (bcrypt) | Simple, estándar, revocable |
| Agente local | Python (`websockets` cliente, `psutil`, `mss`, `subprocess`) | Mismo runtime que el backend, multiplataforma, librerías maduras para CPU/RAM/screenshot |
| IA | Anthropic API (Claude), tool use | El modelo decide qué herramienta ejecutar (leer archivo, correr comando, etc.); el backend valida contra permisos antes de reenviar al agente |
| Frontend móvil | React + Vite + TypeScript + Tailwind (PWA) | Instalable en el celular como app, dark mode nativo, un solo código para todos los celulares (no apps nativas separadas) |
| Voz | Web Speech API (STT en el navegador) | Cero costo, cero latencia de red extra; si hace falta mayor precisión, fase futura: Whisper en el backend |
| Streaming de pantalla (MVP) | Screenshots JPEG por WebSocket | Simple, ya cubre "ver qué está pasando" (secciones 4-5) |
| Streaming de pantalla (futuro) | WebRTC (`aiortc` o servidor SFU) | Para video fluido + control remoto de mouse/teclado |
| Deployment | Docker Compose (backend), agente como script/servicio en la PC, frontend build estático servido por el backend o Vercel | Portable, fácil de mostrar en un portfolio |

## 4. Modelo de permisos (resumen — detalle en `agent/config.example.yaml`)

Tres listas explícitas evaluadas en ese orden: **DENY** (nunca, ni con confirmación — `.env`, credenciales, fuera de directorios autorizados) → **CONFIRM** (requiere aprobación desde el celular, con opción "permitir siempre" que se graba en DB) → **ALLOW** (se ejecuta directo, siempre dentro de un directorio raíz autorizado y con un allowlist de binarios). Todo pasa por el backend, que es quien tiene la última palabra. El agente vuelve a validar cada acción contra su propia copia local de la config de permisos (defensa en profundidad frente a spoofing de red o un agente impostor — cerrado con auth por dispositivo con token propio, ver auditoría). Límite honesto: esa revalidación local no prueba criptográficamente que una aprobación humana real ocurrió para una acción CONFIRM — si el proceso del backend mismo estuviera comprometido, podría en teoría pedir una acción CONFIRM sin aprobación genuina. Cerrar esto del todo requeriría que el celular firme la aprobación con una clave que el backend nunca tenga (no implementado); como mitigación parcial, el agente mantiene un log de auditoría local independiente del backend.

## 5. Acceso remoto fuera de la LAN (Prioridad 2)

Comparación de las opciones evaluadas — detalle completo y pasos en [`docs/REMOTE_ACCESS.md`](REMOTE_ACCESS.md):

| | VPS propio | ngrok | Tailscale | Cloudflare Tunnel (elegido) |
|---|---|---|---|---|
| Costo | ~USD 5-6/mes | Gratis con límites (URL inestable en free) | Gratis (uso personal) | Gratis |
| Mantenimiento | Alto (parches, backups de un servidor aparte) | Bajo | Bajo | Bajo (un proceso `cloudflared` en la PC) |
| Requiere algo instalado en el celular | No | No | Sí (app de Tailscale) | No — es una URL HTTPS normal |
| Exposición pública | Sí (IP propia) | Sí | No, nunca sale a la red pública | Sí (subdominio, blindable con Cloudflare Access) |
| Sigue funcionando con la PC apagada | Sí — pero sin sentido, si la PC está apagada el agente no puede hacer nada igual | No | No | No |

Se descartó el VPS porque el backend solo es útil si la PC (donde vive el agente) está encendida — centralizarlo en un servidor aparte agrega costo y mantenimiento sin ganar disponibilidad real. Se descartó ngrok por la URL inestable en el plan gratuito. Entre Tailscale y Cloudflare Tunnel, se eligió Cloudflare Tunnel porque no requiere instalar nada adicional en el celular (se abre como cualquier sitio HTTPS), manteniendo la promesa original de "PWA simple, sin apps extra" — a costa de un subdominio públicamente resoluble (mitigado con Cloudflare Access como capa de login adicional antes de llegar siquiera a la app).

## 6. Streaming de pantalla (Prioridad 3)

Se evaluó reemplazar el espejo de pantalla por WebRTC (video real, baja latencia) y se decidió **no hacerlo todavía**, por una razón técnica concreta: la PC vive detrás de un router doméstico y el celular casi siempre detrás de NAT del operador móvil — esa combinación necesita casi siempre un **TURN server** para que la conexión directa funcione, y un TURN confiable no es gratis (cobra por el ancho de banda relayado). Con la restricción explícita de no generar costos, construir WebRTC hoy habría significado una conexión que falla silenciosamente en la práctica en una fracción real de las redes.

En su lugar se mejoró el mecanismo existente (screenshots sobre el WebSocket ya probado): más cuadros por segundo (de 1 cada 2s a varios por segundo), sin reenviar cuadros idénticos a uno anterior (hash de cada JPEG), y — el cambio más importante — **activado solo mientras hay alguien mirando** (`screen_subscribe`/`screen_unsubscribe` viajan como mensajes sobre el mismo WebSocket, el backend lleva la cuenta de suscriptores por dispositivo en `Hub.screen_subscribers`, y el agente captura pantalla únicamente mientras tiene al menos un suscriptor activo). Antes de este cambio, si `screenshot_enabled` estaba en `true`, el agente transmitía todo el tiempo sin importar si alguien lo veía. WebRTC queda documentado como paso siguiente, condicionado a que en algún momento se acepte pagar un TURN o se resuelva de otra forma (por ejemplo, Cloudflare Calls, no evaluado en profundidad todavía).

## 7. Fases (siguiendo el pedido original)

MVP construido en esta sesión: Fases 1-7 (arquitectura, backend, agente, WS realtime, frontend, integración Claude, permisos) en versión mínima funcional, más Prioridades 1-3 del roadmap post-auditoría (selector de PC/proyecto, acceso remoto vía Cloudflare Tunnel, espejo de pantalla mejorado con activación por demanda). Fases pendientes (WebRTC real, hardening de seguridad completo, testing automatizado, deployment productivo, documentación final) quedan como roadmap explícito en el README principal.
