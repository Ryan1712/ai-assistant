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
  | { type: "tool_running"; chat_request_id: string; tool_name: string }
  | { type: "deep_analysis_started"; chat_request_id: string };

/**
 * Mở WS stream cho 1 conversation, TỰ NỐI LẠI khi rớt (mất mạng, BE restart);
 * trả hàm đóng kết nối. Không reconnect thì mọi event sau khi rớt (token,
 * request_failed...) mất hút — màn chat "đứng im" vĩnh viễn tới khi mở lại.
 * onReconnect gọi sau mỗi lần nối lại thành công để caller refresh trạng thái
 * (bù các event đã lỡ trong lúc đứt).
 */
export async function openConversationStream(
  conversationId: string,
  onEvent: (e: WsEvent) => void,
  onReconnect?: () => void,
): Promise<() => void> {
  let closed = false;
  let ws: WebSocket | null = null;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const connect = async (isReconnect: boolean) => {
    // Lấy token MỖI lần connect — token cũ có thể đã hết hạn trong lúc đứt mạng.
    const tokens = await getTokens();
    if (closed) return;
    const wsBase = API_URL.replace(/^http/, "ws");
    ws = new WebSocket(
      `${wsBase}/ws/conversations/${conversationId}?token=${tokens?.access_token ?? ""}`,
    );
    ws.onopen = () => {
      attempt = 0;
      if (isReconnect) onReconnect?.();
    };
    ws.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(String(ev.data)) as WsEvent);
      } catch {}
    };
    ws.onerror = () => ws?.close();
    ws.onclose = () => {
      if (closed) return;
      attempt += 1;
      const delayMs = Math.min(1000 * 2 ** (attempt - 1), 15000);
      timer = setTimeout(() => {
        connect(true);
      }, delayMs);
    };
  };

  await connect(false);
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    ws?.close();
  };
}
