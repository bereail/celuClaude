import { useEffect, useState } from "react";

export function ScreenMirror({ imageB64, lastFrameAt }: { imageB64: string | null; lastFrameAt: number | null }) {
  const [, forceTick] = useState(0);

  // Re-renderiza cada segundo para que "hace Ns" se mantenga actualizado
  // aunque no llegue ningun cuadro nuevo (pantalla quieta del otro lado).
  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

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
      <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/60 rounded-full px-2.5 py-1 text-xs">
        <span className={`h-2 w-2 rounded-full ${isLive ? "bg-online animate-pulse" : "bg-slate-500"}`} />
        {isLive ? "EN VIVO" : `hace ${ageSeconds}s`}
      </div>
      <img src={`data:image/jpeg;base64,${imageB64}`} alt="Pantalla de la PC" className="w-full" />
    </div>
  );
}
