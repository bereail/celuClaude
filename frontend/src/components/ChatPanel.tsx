import { ChatMessage } from "../types";

export function ChatPanel({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="flex flex-col gap-3 overflow-y-auto flex-1 px-1">
      {messages.map((m) => (
        <div
          key={m.id}
          className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
            m.role === "user"
              ? "self-end bg-accent text-white"
              : "self-start bg-panel text-slate-100"
          }`}
        >
          {m.content}
        </div>
      ))}
    </div>
  );
}
