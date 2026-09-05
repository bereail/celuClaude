import { Device } from "../types";

export function DeviceCard({ device }: { device: Device | null }) {
  if (!device) {
    return (
      <div className="rounded-2xl bg-panel p-4">
        <div className="flex items-center gap-2 text-offline font-medium">
          <span className="h-2.5 w-2.5 rounded-full bg-offline" /> PC no conectada
        </div>
        <p className="text-sm text-slate-400 mt-1">Iniciá el agente local para empezar.</p>
      </div>
    );
  }

  const online = device.status === "online";

  return (
    <div className="rounded-2xl bg-panel p-4 space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-semibold">{device.name}</span>
        <div className={`flex items-center gap-1.5 text-sm ${online ? "text-online" : "text-offline"}`}>
          <span className={`h-2.5 w-2.5 rounded-full ${online ? "bg-online" : "bg-offline"}`} />
          {online ? "ONLINE" : "OFFLINE"}
        </div>
      </div>
      <div className="text-sm text-slate-400">{device.os}</div>
      {device.current_project && (
        <div className="text-sm">
          Proyecto: <span className="text-slate-200">{device.current_project}</span>
        </div>
      )}
      <div className="flex gap-4 text-xs text-slate-400 pt-1">
        <span>CPU: {device.cpu_percent.toFixed(0)}%</span>
        <span>RAM: {device.ram_percent.toFixed(0)}%</span>
      </div>
    </div>
  );
}
