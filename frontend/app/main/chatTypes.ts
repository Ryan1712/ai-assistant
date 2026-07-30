// Kiểu dữ liệu dùng chung giữa Chat và ChatRow — tránh circular import.
import type { ProposedAction } from "../../src/api/chat";

export type Row =
  | { key: string; kind: "user" | "assistant"; text: string; voiceNoteId?: string | null; isSeed?: boolean }
  | { key: string; kind: "streaming"; text: string }
  | { key: string; kind: "system"; text: string }
  | { key: string; kind: "choices"; options: string[] }
  | { key: string; kind: "failed"; text: string; retryContent: string | null };

// Re-export để tránh import dư thừa từ bên ngoài (nếu cần)
export type { ProposedAction };
