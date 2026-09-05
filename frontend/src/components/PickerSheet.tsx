import { useState } from "react";
import { api } from "../lib/api";
import { Device, Project } from "../types";

interface Props {
  devices: Device[];
  projects: Project[];
  onProjectCreated: (project: Project) => void;
  onConfirm: (deviceId: string, projectId: string | null) => void;
  onCancel?: () => void;
  currentDeviceId: string | null;
  currentProjectId: string | null;
}

export function PickerSheet({
  devices,
  projects,
  onProjectCreated,
  onConfirm,
  onCancel,
  currentDeviceId,
  currentProjectId,
}: Props) {
  const [deviceId, setDeviceId] = useState<string | null>(currentDeviceId);
  const [projectId, setProjectId] = useState<string | null>(currentProjectId);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPath, setNewPath] = useState("");
  const [saving, setSaving] = useState(false);

  const createProject = async () => {
    if (!newName.trim() || !newPath.trim()) return;
    setSaving(true);
    try {
      const project = (await api.createProject({ name: newName.trim(), path: newPath.trim() })) as Project;
      setNewName("");
      setNewPath("");
      setCreating(false);
      onProjectCreated(project);
      setProjectId(project.id);
    } catch (err) {
      alert(`No se pudo crear el proyecto: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-end justify-center z-50">
      <div className="w-full max-w-md rounded-t-3xl bg-panel p-6 space-y-5 max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-lg">¿Con qué PC y proyecto?</h2>
          {onCancel && (
            <button onClick={onCancel} className="text-slate-500 text-sm">
              cerrar
            </button>
          )}
        </div>

        <div>
          <p className="text-xs text-slate-400 mb-2 uppercase tracking-wide">PC</p>
          {devices.length === 0 && <p className="text-sm text-slate-500">No hay ninguna PC registrada todavía.</p>}
          <div className="flex flex-col gap-2">
            {devices.map((d) => {
              const online = d.status === "online";
              const selected = deviceId === d.id;
              return (
                <button
                  key={d.id}
                  disabled={!online}
                  onClick={() => setDeviceId(d.id)}
                  className={`flex items-center justify-between rounded-xl px-4 py-3 text-left border ${
                    selected ? "border-accent bg-accent/10" : "border-slate-700"
                  } ${!online ? "opacity-40" : ""}`}
                >
                  <span>{d.name}</span>
                  <span className={`flex items-center gap-1.5 text-xs ${online ? "text-online" : "text-offline"}`}>
                    <span className={`h-2 w-2 rounded-full ${online ? "bg-online" : "bg-offline"}`} />
                    {online ? "online" : "offline"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <p className="text-xs text-slate-400 mb-2 uppercase tracking-wide">Proyecto</p>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => setProjectId(null)}
              className={`rounded-xl px-4 py-3 text-left border ${
                projectId === null ? "border-accent bg-accent/10" : "border-slate-700"
              }`}
            >
              Sin proyecto (sesión libre)
            </button>
            {projects.map((p) => (
              <button
                key={p.id}
                onClick={() => setProjectId(p.id)}
                className={`rounded-xl px-4 py-3 text-left border ${
                  projectId === p.id ? "border-accent bg-accent/10" : "border-slate-700"
                }`}
              >
                <div>{p.name}</div>
                <div className="text-xs text-slate-500 truncate">{p.path}</div>
              </button>
            ))}
          </div>

          {!creating ? (
            <button onClick={() => setCreating(true)} className="mt-2 text-sm text-accent">
              + Nuevo proyecto
            </button>
          ) : (
            <div className="mt-3 space-y-2 rounded-xl bg-black/30 p-3">
              <input
                className="w-full rounded-lg bg-panel px-3 py-2 text-sm outline-none"
                placeholder="Nombre (ej: Turnero)"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
              <input
                className="w-full rounded-lg bg-panel px-3 py-2 text-sm outline-none"
                placeholder="Carpeta (ej: D:\Bere\GIT\Turnero)"
                value={newPath}
                onChange={(e) => setNewPath(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  onClick={createProject}
                  disabled={saving}
                  className="flex-1 rounded-lg bg-accent py-2 text-sm disabled:opacity-50"
                >
                  {saving ? "Creando..." : "Crear"}
                </button>
                <button onClick={() => setCreating(false)} className="flex-1 rounded-lg bg-panel border border-slate-600 py-2 text-sm">
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>

        <button
          onClick={() => deviceId && onConfirm(deviceId, projectId)}
          disabled={!deviceId}
          className="w-full rounded-xl bg-accent py-3 font-medium disabled:opacity-40"
        >
          Empezar
        </button>
      </div>
    </div>
  );
}
