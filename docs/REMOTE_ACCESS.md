# Acceso remoto (Prioridad 2) — Cloudflare Tunnel

Guía para poder abrir el Command Center desde el celular sin estar en la misma
red Wi-Fi que la PC, sin abrir puertos en el router y sin exponer la PC
directamente a Internet.

## Por qué esto y no otra cosa

Ver la comparación completa en `docs/ARCHITECTURE.md` (sección agregada en
Prioridad 2). Resumen: `cloudflared` corre en la PC y abre una conexión
**saliente** hacia Cloudflare — el mismo patrón que ya usa el agente para
hablar con el backend. Nunca hay un puerto escuchando hacia Internet en tu
router ni en tu PC. Es gratis, no requiere mantener un servidor aparte, y da
HTTPS/WSS automático sin tener que gestionar certificados.

## Requisitos previos

- El dominio `ailonline.com.ar` (o el que uses) agregado a una cuenta de
  Cloudflare gratuita, con los nameservers ya apuntando ahí (ver los pasos
  que se mandaron por chat — eso lo hace el dueño de la cuenta, no se puede
  automatizar desde acá).
- `cloudflared` instalado en la PC (`winget install --id Cloudflare.cloudflared -e`).
- El backend corriendo en `http://localhost:8000` (ver README principal).

## Pasos

### 1. Autenticar cloudflared con tu cuenta de Cloudflare

```powershell
cloudflared tunnel login
```

Abre el navegador, pedís que autorice el dominio `ailonline.com.ar`. Genera
un certificado local (`~/.cloudflared/cert.pem`) que cloudflared usa para las
siguientes operaciones — no hace falta volver a loguearse cada vez.

### 2. Crear el túnel (una sola vez)

```powershell
cloudflared tunnel create celu-command-center
```

Esto imprime un `Tunnel ID` (un UUID) y crea un archivo de credenciales en
`~/.cloudflared/<TUNNEL_ID>.json`. Anotá el ID, lo necesitás en el paso 4.

### 3. Apuntar el subdominio al túnel

```powershell
cloudflared tunnel route dns celu-command-center celu.ailonline.com.ar
```

Esto crea automáticamente el registro DNS en Cloudflare — no hay que tocar
nada a mano en el panel. Cambiá `celu` por el subdominio que prefieras.

### 4. Completar la config

```powershell
copy deploy\cloudflared\config.example.yml deploy\cloudflared\config.yml
```

Editar `deploy\cloudflared\config.yml` y completar `tunnel` (el UUID del paso
2), `credentials-file` (la ruta que imprimió el paso 2) y `hostname` (el
subdominio del paso 3, si usaste uno distinto a `celu.ailonline.com.ar`).

### 5. Probar en primer plano

```powershell
cloudflared tunnel --config deploy\cloudflared\config.yml run
```

Con el backend corriendo, abrí `https://celu.ailonline.com.ar` desde el
celular (con datos móviles, no Wi-Fi, para probar que realmente no depende de
la red local). Si carga el login de la PWA, funciona. `Ctrl+C` para cortar
esta prueba.

### 6. Dejarlo corriendo siempre (como servicio de Windows)

Abrir PowerShell **como Administrador** (instalar un servicio de Windows lo
requiere) y usar la **ruta absoluta** al config — el servicio no arranca
parado en la carpeta del proyecto, así que una ruta relativa (`deploy\...`)
no resuelve después de un reinicio:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --config "D:\Bere\GIT\celuClaude\deploy\cloudflared\config.yml" service install
Start-Service Cloudflared
Get-Service Cloudflared   # tiene que decir Status: Running, StartType: Automatic
```

Esto lo deja corriendo en segundo plano y arrancando solo con Windows (antes
de loguearse, incluso), sin depender de tener una terminal abierta. Para
desinstalarlo: `cloudflared service uninstall` (también como Administrador).

## Antes de dejarlo expuesto de forma permanente — checklist de seguridad

Estos puntos importan mucho más ahora que antes, porque el backend deja de
depender de estar en la misma red que vos:

- [ ] `JWT_SECRET` en `backend/.env` es un valor random generado (`python -c
      "import secrets;print(secrets.token_hex(32))"`), no el de ejemplo.
- [ ] `AGENT_ENROLLMENT_TOKEN` también es un valor random propio, no el de
      ejemplo — es lo único que protege el registro de un agente nuevo.
- [ ] `APP_USER_PASSWORD_HASH` corresponde a una contraseña fuerte de verdad
      (no una de prueba).
- [ ] `permissions.yaml` → `allowed_roots` apunta solo a las carpetas de
      proyectos reales, no a la raíz del disco.
- [ ] (Recomendado) Activar **Cloudflare Access** delante del hostname — ver
      abajo. Agrega un login adicional (con tu email, sin costo) antes de que
      cualquiera llegue siquiera a la pantalla de login de la app.

## Capa extra recomendada: Cloudflare Access

Gratis para uso personal (hasta 50 usuarios). Agrega una verificación por
email (código de un solo uso) **antes** de que el tráfico llegue al backend
— así un desconocido que se tope con la URL no puede ni siquiera intentar
loguearse en la app.

1. **dash.cloudflare.com** → **Zero Trust** → **Access** → **Applications** →
   **Add an application** → **Self-hosted**.
2. Dominio: `celu.ailonline.com.ar` (el mismo del túnel).
3. Policy: "Allow" solo para tu email (`berenicesolohaga@gmail.com` o el que
   uses).
4. Guardar. A partir de ahí, entrar a esa URL primero pide un código que
   Cloudflare manda por mail — recién después se ve la app.

## Qué cambia en el código (ya aplicado)

- El backend ahora sirve el build de la PWA (`frontend/dist`) desde su propio
  origen (`backend/app/main.py`), así que el túnel solo necesita exponer un
  puerto — no hay que coordinar dos hostnames ni configurar CORS para
  producción.
- El frontend (`frontend/src/lib/api.ts`) calcula la URL de la API/WebSocket
  a partir de `window.location.origin` por defecto — funciona igual entrando
  por la LAN, por el túnel, o local, sin tocar nada.
