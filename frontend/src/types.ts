export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "activity";
  content: string;
  created_at: string;
}

export interface ActivityEvent {
  text: string;
  ts: number;
}

export interface Device {
  id: string;
  name: string;
  os: string;
  status: "online" | "offline";
  cpu_percent: number;
  ram_percent: number;
  current_project: string;
  last_seen: string | null;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  description: string;
  technologies: string;
  created_at: string;
}

export interface SessionInfo {
  id: string;
  project_id: string | null;
  title: string;
  autonomy_level: number;
  status: string;
  started_at: string;
  ended_at: string | null;
}

export interface AuthorizationRequest {
  action_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  reason: string;
  session_id: string;
}

export interface ActionLogEntry {
  id: string;
  tool_name: string;
  tool_input: string;
  decision: string;
  status: string;
  result: string;
  created_at: string;
}
