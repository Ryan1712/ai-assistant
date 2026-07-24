import { apiFetch } from "./client";

export type Conversation = {
  id: string;
  title: string | null;
  queue_held: boolean;
  archived_at: string | null;
  created_at: string;
};

// Cụm từ resume theo funtional-plan 5.7 — BE match không phân biệt hoa/thường/dấu
export const RESUME_PHRASE = "tiếp tục công việc";

/** Chuẩn hóa giống BE (continuity._normalize): lowercase, đ→d, bỏ dấu, gộp space. */
export function isResumePhrase(text: string): boolean {
  const norm = text
    .toLowerCase()
    .replace(/đ/g, "d")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
  return norm === "tiep tuc cong viec";
}

export type ChatRequestStatus =
  | "queued"
  | "running"
  | "awaiting_confirmation"
  | "done"
  | "failed"
  | "cancelled";

export type ProposedAction = {
  tool_name: string;
  tool_input: Record<string, unknown>;
  display_text: string;
};

export type ToolPendingAction = {
  kind: "tool";
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_use_id: string;
};

export type ProposalPendingAction = {
  kind: "proposal";
  actions: ProposedAction[];
  reasoning: string;
  tool_use_id: string;
};

export type PendingAction = ToolPendingAction | ProposalPendingAction;

export type ChatRequest = {
  id: string;
  conversation_id: string;
  status: ChatRequestStatus;
  content: string;
  voice_note_id: string | null;
  pending_action: PendingAction | null;
  created_at: string;
};

export type ContentBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: unknown }
  | { type: "tool_result"; tool_use_id: string; content: string };

export type Message = {
  id: string;
  conversation_id: string | null;
  role: "user" | "assistant";
  content: ContentBlock[];
  voice_note_id: string | null;
  created_at: string;
};

export const listConversations = () =>
  apiFetch<Conversation[]>("/api/v1/conversations");

export const createConversation = (title?: string) =>
  apiFetch<Conversation>("/api/v1/conversations", { method: "POST", body: { title } });

export const renameConversation = (conversationId: string, title: string) =>
  apiFetch<Conversation>(`/api/v1/conversations/${conversationId}`, {
    method: "PATCH",
    body: { title },
  });

export const deleteConversation = (conversationId: string) =>
  apiFetch<void>(`/api/v1/conversations/${conversationId}`, { method: "DELETE" });

export const listMessages = (conversationId: string) =>
  apiFetch<Message[]>(`/api/v1/conversations/${conversationId}/messages`);

export const getActiveConversation = () =>
  apiFetch<Conversation>("/api/v1/conversations/active");

export const getTimeline = (opts?: { beforeAt?: string; beforeId?: string; limit?: number }) => {
  const p = new URLSearchParams();
  if (opts?.limit) p.set("limit", String(opts.limit));
  if (opts?.beforeAt && opts?.beforeId) {
    p.set("before_at", opts.beforeAt);
    p.set("before_id", opts.beforeId);
  }
  const qs = p.toString();
  return apiFetch<Message[]>(`/api/v1/conversations/timeline${qs ? `?${qs}` : ""}`);
};

export const listRequests = (conversationId: string) =>
  apiFetch<ChatRequest[]>(`/api/v1/conversations/${conversationId}/requests`);

export const sendMessage = (conversationId: string, content: string, voiceNoteId?: string) =>
  apiFetch<ChatRequest>(`/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    body: voiceNoteId ? { content, voice_note_id: voiceNoteId } : { content },
  });

export const stopAll = (conversationId: string) =>
  apiFetch<void>(`/api/v1/conversations/${conversationId}/stop-all`, { method: "POST" });

export const cancelRequest = (requestId: string) =>
  apiFetch<void>(`/api/v1/chat-requests/${requestId}/cancel`, { method: "POST" });

export const reorderRequest = (requestId: string, beforeId: string | null = null) =>
  apiFetch<ChatRequest>(`/api/v1/chat-requests/${requestId}/reorder`, {
    method: "POST",
    body: { before_id: beforeId },
  });

export const confirmRequest = (requestId: string, approved: boolean) =>
  apiFetch<ChatRequest>(`/api/v1/chat-requests/${requestId}/confirm`, {
    method: "POST",
    body: { approved },
  });
