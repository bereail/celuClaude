import { AuthorizationRequest } from "../types";

interface Props {
  request: AuthorizationRequest;
  onDecide: (decision: "approved" | "denied" | "always") => void;
}

export function ApprovalSheet({ request, onDecide }: Props) {
  const detail =
    request.tool_name === "run_command"
      ? String(request.tool_input.command ?? "")
      : String(request.tool_input.path ?? "");

  return (
    <div className="fixed inset-0 bg-black/60 flex items-end justify-center z-50">
      <div className="w-full max-w-md rounded-t-3xl bg-panel p-6 space-y-4">
        <div className="flex items-center gap-2 text-warn font-semibold text-lg">
          ⚠️ AUTORIZACIÓN NECESARIA
        </div>
        <p className="text-sm text-slate-400">Claude quiere ejecutar:</p>
        <code className="block bg-black/40 rounded-xl p-3 text-sm break-all">{detail}</code>
        <p className="text-sm text-slate-400">Motivo: {request.reason}</p>
        <div className="flex flex-col gap-2 pt-2">
          <button
            onClick={() => onDecide("denied")}
            className="w-full rounded-xl bg-offline/20 text-offline py-3 font-medium"
          >
            DENEGAR
          </button>
          <button
            onClick={() => onDecide("approved")}
            className="w-full rounded-xl bg-panel border border-slate-600 py-3 font-medium"
          >
            PERMITIR UNA VEZ
          </button>
          <button
            onClick={() => onDecide("always")}
            className="w-full rounded-xl bg-accent py-3 font-medium"
          >
            PERMITIR SIEMPRE
          </button>
        </div>
      </div>
    </div>
  );
}
