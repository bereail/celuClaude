import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ActionLogEntry } from "../types";

const CANNED_QUESTIONS = [
  "¿Qué hizo?",
  "¿Por qué lo hizo?",
  "¿Qué significa este código?",
  "¿Qué debería saber para explicarlo en una entrevista?",
];

const DECISION_STYLES: Record<string, string> = {
  allow: "text-online",
  confirm: "text-warn",
  deny: "text-offline",
};

function summarize(entry: ActionLogEntry): string {
  try {
    const input = JSON.parse(entry.tool_input);
    return input.command ?? input.path ?? entry.tool_input;
  } catch {
    return entry.tool_input;
  }
}

function ActionCard({ entry }: { entry: ActionLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  const ask = async (q: string) => {
    if (!q.trim()) return;
    setAsking(true);
    setAnswer(null);
    try {
      const res = await api.explainAction(entry.id, q.trim());
      setAnswer(res.answer);
    } catch (err) {
      setAnswer(`No se pudo obtener la explicación: ${err}`);
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="rounded-xl bg-panel border border-slate-700 overflow-hidden">
      <button onClick={() => setExpanded((e) => !e)} className="w-full text-left px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium text-sm">{entry.tool_name}</span>
          <span className={`text-xs ${DECISION_STYLES[entry.decision] ?? "text-slate-400"}`}>{entry.status}</span>
        </div>
        <div className="text-xs text-slate-400 truncate mt-0.5">{summarize(entry)}</div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-slate-700 pt-3">
          <div className="flex flex-wrap gap-2">
            {CANNED_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => {
                  setQuestion(q);
                  ask(q);
                }}
                disabled={asking}
                className="text-xs rounded-full border border-accent text-accent px-3 py-1.5 disabled:opacity-40"
              >
                {q}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-lg bg-black/30 px-3 py-2 text-sm outline-none"
              placeholder="O preguntá lo que quieras..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask(question)}
            />
            <button
              onClick={() => ask(question)}
              disabled={asking || !question.trim()}
              className="rounded-lg bg-accent px-3 text-sm disabled:opacity-40"
            >
              Preguntar
            </button>
          </div>

          {asking && <p className="text-xs text-slate-500">Claude está pensando...</p>}
          {answer && <p className="text-sm whitespace-pre-wrap bg-black/20 rounded-lg p-3">{answer}</p>}
        </div>
      )}
    </div>
  );
}

export function ActionsPanel({ sessionId }: { sessionId: string | null }) {
  const [actions, setActions] = useState<ActionLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = () => {
    if (!sessionId) return;
    setLoading(true);
    api
      .getActions(sessionId)
      .then((a) => setActions((a as ActionLogEntry[]).slice().reverse()))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(load, [sessionId]);

  if (!sessionId) return <p className="text-sm text-slate-500 text-center">Elegí una PC para empezar.</p>;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-400 uppercase tracking-wide">Acciones de esta sesión</p>
        <button onClick={load} className="text-xs text-accent">
          {loading ? "actualizando..." : "actualizar"}
        </button>
      </div>
      {actions.length === 0 && <p className="text-sm text-slate-500">Todavía no hay acciones en esta sesión.</p>}
      {actions.map((a) => (
        <ActionCard key={a.id} entry={a} />
      ))}
    </div>
  );
}
