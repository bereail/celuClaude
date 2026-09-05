import { useEffect, useRef, useState } from "react";

const LONG_PRESS_MS = 500;

interface Props {
  imageB64: string | null;
  lastFrameAt: number | null;
  onRemoteClick?: (xFrac: number, yFrac: number, button: "left" | "right") => void;
}

export function ScreenMirror({ imageB64, lastFrameAt, onRemoteClick }: Props) {
  const [, forceTick] = useState(0);
  const imgRef = useRef<HTMLImageElement>(null);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  // Re-renderiza cada segundo para que "hace Ns" se mantenga actualizado
  // aunque no llegue ningun cuadro nuevo (pantalla quieta del otro lado).
  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const fireClick = (clientX: number, clientY: number, button: "left" | "right") => {
    const el = imgRef.current;
    if (!el || !onRemoteClick) return;
    const rect = el.getBoundingClientRect();
    const xFrac = (clientX - rect.left) / rect.width;
    const yFrac = (clientY - rect.top) / rect.height;
    if (xFrac < 0 || xFrac > 1 || yFrac < 0 || yFrac > 1) return;
    onRemoteClick(xFrac, yFrac, button);
  };

  // Tap = click izquierdo. Mantener apretado = click derecho (no hay boton
  // derecho real en touch). onContextMenu cubre el caso de un mouse real
  // sobre el mismo componente (ej. probando desde una PC).
  const onPointerDown = (e: React.PointerEvent<HTMLImageElement>) => {
    longPressFired.current = false;
    const { clientX, clientY } = e;
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true;
      fireClick(clientX, clientY, "right");
    }, LONG_PRESS_MS);
  };

  const clearLongPress = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  const onPointerUp = (e: React.PointerEvent<HTMLImageElement>) => {
    clearLongPress();
    if (!longPressFired.current) fireClick(e.clientX, e.clientY, "left");
  };

  const onContextMenu = (e: React.MouseEvent<HTMLImageElement>) => {
    e.preventDefault();
    clearLongPress();
    fireClick(e.clientX, e.clientY, "right");
  };

  if (!imageB64) {
    return (
      <div className="rounded-2xl bg-panel p-6 text-center text-sm text-slate-500">
        Conectando al espejo de pantalla... si no aparece nada, revisá que
        <code className="mx-1 text-xs">screenshot_enabled: true</code>
        esté en el <code className="text-xs">config.yaml</code> del agente.
      </div>
    );
  }

  const ageSeconds = lastFrameAt ? Math.max(0, Math.round((Date.now() - lastFrameAt) / 1000)) : null;
  const isLive = ageSeconds !== null && ageSeconds <= 2;

  return (
    <div className="rounded-2xl overflow-hidden bg-black relative">
      <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/60 rounded-full px-2.5 py-1 text-xs pointer-events-none">
        <span className={`h-2 w-2 rounded-full ${isLive ? "bg-online animate-pulse" : "bg-slate-500"}`} />
        {isLive ? "EN VIVO" : `hace ${ageSeconds}s`}
      </div>
      {onRemoteClick && (
        <div className="absolute top-2 right-2 bg-black/60 rounded-full px-2.5 py-1 text-xs text-slate-300 pointer-events-none">
          tocá para clickear · mantené para click derecho
        </div>
      )}
      <img
        ref={imgRef}
        src={`data:image/jpeg;base64,${imageB64}`}
        alt="Pantalla de la PC"
        className="w-full touch-none select-none"
        onPointerDown={onRemoteClick ? onPointerDown : undefined}
        onPointerUp={onRemoteClick ? onPointerUp : undefined}
        onPointerLeave={clearLongPress}
        onContextMenu={onRemoteClick ? onContextMenu : undefined}
      />
    </div>
  );
}
