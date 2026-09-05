import { useEffect, useRef, useState } from "react";
import { ActionsPanel } from "./components/ActionsPanel";
import { ActivityStream } from "./components/ActivityStream";
import { ApprovalSheet } from "./components/ApprovalSheet";
import { ChatPanel } from "./components/ChatPanel";
import { DeviceCard } from "./components/DeviceCard";
import { Login } from "./components/Login";
import { MicButton } from "./components/MicButton";
import { PickerSheet } from "./components/PickerSheet";
import { ScreenMirror } from "./components/ScreenMirror";
import {
  api,
  connectMobileSocket,
  getSelection,
  getToken,
  MobileSocketHandle,
  setSelection,
  setToken,
  setUnauthorizedHandler,
} from "./lib/api";
import { ActivityEvent, AuthorizationRequest, ChatMessage, Device, Project } from "./types";

type View = "activity" | "screen" | "actions";

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [devices, setDevices] = useState<Device[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [working, setWorking] = useState(false);
  const [approval, setApproval] = useState<AuthorizationRequest | null>(null);
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [view, setView] = useState<View>("activity");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [socketConnected, setSocketConnected] = useState(false);
  const [lastFrameAt, setLastFrameAt] = useState<number | null>(null);
  const socketRef = useRef<MobileSocketHandle | null>(null);

  const device = devices.find((d) => d.id === deviceId) ?? null;
  const project = projects.find((p) => p.id === projectId) ?? null;

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false));
    return () => setUnauthorizedHandler(null);
  }, []);

  // Carga inicial: PCs, proyectos, y decide si hace falta preguntar o si ya
  // hay una seleccion guardada de una visita anterior que sigue siendo valida.
  useEffect(() => {
    if (!authed) return;

    (async () => {
      const [deviceList, projectList] = await Promise.all([
        api.listDevices() as Promise<Device[]>,
        api.listProjects() as Promise<Project[]>,
      ]);
      setDevices(deviceList);
      setProjects(projectList);

      const saved = getSelection();
      const savedDeviceIsValid = saved.deviceId && deviceList.some((d) => d.id === saved.deviceId);
      if (savedDeviceIsValid) {
        setDeviceId(saved.deviceId);
        setProjectId(saved.projectId);
        await startSession(saved.projectId, projectList);
      } else {
        setShowPicker(true);
      }
    })().catch(console.error);

    const socket = connectMobileSocket((event) => {
      switch (event.type) {
        case "message":
          setMessages((prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: event.role, content: event.content, created_at: new Date().toISOString() },
          ]);
          if (event.role === "assistant") setWorking(false);
          break;
        case "activity":
          setWorking(true);
          setActivity((prev) => [...prev.slice(-49), { text: event.text, ts: Date.now() }]);
          break;
        case "authorization_required":
          setApproval(event as AuthorizationRequest);
          break;
        case "device_status":
          setDevices((prev) => prev.map((d) => (d.id === event.device_id ? { ...d, ...event, status: event.status ?? d.status } : d)));
          break;
        case "screenshot":
          setScreenshot(event.image_b64);
          setLastFrameAt(Date.now());
          break;
        case "done":
          setWorking(false);
          break;
      }
    }, setSocketConnected, () => setAuthed(false));

    socketRef.current = socket;
    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [authed]);

  // Espejo de pantalla: solo pedimos cuadros mientras esta pestaña esta
  // activa y hay una PC elegida -- si cambiamos de pestaña o de PC, avisamos
  // al backend para que el agente deje de gastar CPU/batería/datos mandando
  // capturas a nadie.
  useEffect(() => {
    if (!device || view !== "screen") return;
    socketRef.current?.send({ type: "screen_subscribe", device_id: device.id });
    return () => {
      socketRef.current?.send({ type: "screen_unsubscribe", device_id: device.id });
    };
  }, [view, device?.id, socketConnected]);

  const startSession = async (newProjectId: string | null, projectList: Project[]) => {
    const title = projectList.find((p) => p.id === newProjectId)?.name ?? "Sesion movil";
    const session = (await api.createSession({ project_id: newProjectId, title })) as { id: string };
    setSessionId(session.id);
  };

  const chooseSelection = async (newDeviceId: string, newProjectId: string | null) => {
    setSelection(newDeviceId, newProjectId);
    setDeviceId(newDeviceId);
    setProjectId(newProjectId);
    setShowPicker(false);
    setMessages([]);
    setActivity([]);
    await startSession(newProjectId, projects);
  };

  const send = async (text: string) => {
    if (!text.trim() || !device || !sessionId) return;
    setInput("");
    setWorking(true);
    try {
      await api.sendInstruction(sessionId, device.id, text.trim());
    } catch (err) {
      setWorking(false);
      alert(`No se pudo enviar: ${err}`);
    }
  };

  const decide = async (decision: "approved" | "denied" | "always") => {
    if (!approval) return;
    await api.decideAction(approval.action_id, decision);
    setApproval(null);
  };

  if (!authed) {
    return <Login onLoggedIn={() => setAuthed(true)} />;
  }

  return (
    <div className="min-h-screen flex flex-col max-w-md mx-auto p-4 gap-4">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="font-bold">CLAUDE COMMAND CENTER</h1>
          {!socketConnected && <span className="text-xs text-warn">reconectando…</span>}
        </div>
        <button
          className="text-xs text-slate-500"
          onClick={() => {
            setToken(null);
            setAuthed(false);
          }}
        >
          salir
        </button>
      </header>

      <button
        onClick={() => setShowPicker(true)}
        className="flex items-center justify-between rounded-xl bg-panel px-4 py-2 text-sm border border-slate-700"
      >
        <span>
          <span className="text-slate-400">PC:</span> {device?.name ?? "elegir"} ·{" "}
          <span className="text-slate-400">Proyecto:</span> {project?.name ?? "ninguno"}
        </span>
        <span className="text-accent">cambiar</span>
      </button>

      <DeviceCard device={device} />

      <ChatPanel messages={messages} />

      <div className="flex items-center gap-3">
        <input
          className="flex-1 rounded-xl bg-panel px-4 py-3 outline-none"
          placeholder="¿Qué querés hacer?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
        />
        <MicButton onResult={(text) => send(text)} disabled={!device} />
      </div>
      <button
        onClick={() => send(input)}
        disabled={!device || working}
        className="w-full rounded-xl bg-accent py-3 font-medium disabled:opacity-40"
      >
        ENVIAR
      </button>

      <div className="flex rounded-xl overflow-hidden border border-slate-700 text-sm">
        <button
          onClick={() => setView("activity")}
          className={`flex-1 py-2 ${view === "activity" ? "bg-accent" : "bg-panel"}`}
        >
          Actividad
        </button>
        <button
          onClick={() => setView("screen")}
          className={`flex-1 py-2 ${view === "screen" ? "bg-accent" : "bg-panel"}`}
        >
          Ver pantalla
        </button>
        <button
          onClick={() => setView("actions")}
          className={`flex-1 py-2 ${view === "actions" ? "bg-accent" : "bg-panel"}`}
        >
          Acciones
        </button>
      </div>

      {view === "activity" && <ActivityStream events={activity} working={working} />}
      {view === "screen" && <ScreenMirror imageB64={screenshot} lastFrameAt={lastFrameAt} />}
      {view === "actions" && <ActionsPanel sessionId={sessionId} />}

      {approval && <ApprovalSheet request={approval} onDecide={decide} />}

      {showPicker && (
        <PickerSheet
          devices={devices}
          projects={projects}
          onProjectCreated={(p) => setProjects((prev) => [p, ...prev])}
          currentDeviceId={deviceId}
          currentProjectId={projectId}
          onConfirm={chooseSelection}
          onCancel={device ? () => setShowPicker(false) : undefined}
        />
      )}
    </div>
  );
}
