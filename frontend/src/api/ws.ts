import { API_URL } from "./client";
import { getTokens } from "../auth/tokenStore";
import type { ProposedAction } from "./chat";

export type WsEvent =
  | { type: "token"; chat_request_id: string; text: string }
  | { type: "status_update"; chat_request_id: string; status: string }
  | { type: "request_done"; chat_request_id: string; result_summary: string }
  | { type: "request_failed"; chat_request_id: string; error: string }
  | {
      type: "confirmation_required";
      kind: "tool";
      chat_request_id: string;
      tool_name: string;
      tool_input: unknown;
    }
  | {
      type: "confirmation_required";
      kind: "proposal";
      chat_request_id: string;
      actions: ProposedAction[];
      reasoning: string;
    }
  | { type: "tool_running"; chat_request_id: string; tool_name: string };

/** Mở WS stream cho 1 conversation; trả hàm đóng kết nối. */
export async function openConversationStream(
  conversationId: string,
  onEvent: (e: WsEvent) => void,
  onClose?: () => void,
): Promise<() => void> {
  const tokens = await getTokens();
  const wsBase = API_URL.replace(/^http/, "ws");
  const ws = new WebSocket(
    `${wsBase}/ws/conversations/${conversationId}?token=${tokens?.access_token ?? ""}`,
  );
  ws.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(String(ev.data)) as WsEvent);
    } catch {}
  };
  ws.onclose = () => onClose?.();
  ws.onerror = () => ws.close();
  return () => ws.close();
}
