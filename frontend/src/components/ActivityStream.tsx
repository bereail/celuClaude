import { useEffect, useRef } from "react";
import { ActivityEvent } from "../types";

export function ActivityStream({ events, working }: { events: ActivityEvent[]; working: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="rounded-2xl bg-panel p-4 flex flex-col gap-2 max-h-64 overflow-hidden">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span className={`h-2.5 w-2.5 rounded-full ${working ? "bg-online animate-pulse" : "bg-slate-600"}`} />
        {working ? "Claude está trabajando..." : "ACTIVIDAD"}
      </div>
      <div className="overflow-y-auto flex flex-col gap-1 font-mono text-xs text-slate-300">
        {events.length === 0 && <span className="text-slate-500">Sin actividad todavía.</span>}
        {events.map((e, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-slate-500">›</span>
            <span>{e.text}</span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
