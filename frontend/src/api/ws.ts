import { API_URL, tryRefresh } from "./client";
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
  | { type: "deep_analysis_started"; chat_request_id: string }
  | { type: "suggest_replies"; chat_request_id: string; options: string[] };

/**
 * Mở WS stream cho 1 conversation, TỰ NỐI LẠI khi rớt (mất mạng, BE restart);
 * trả hàm đóng kết nối. Không reconnect thì mọi event sau khi rớt (token,
 * request_failed...) mất hút — màn chat "đứng im" vĩnh viễn tới khi mở lại.
 * onReconnect gọi sau mỗi lần nối lại thành công để caller refresh trạng thái
 * (bù các event đã lỡ trong lúc đứt).
 */
// BE đóng WS bằng code 4401 khi token sai/hết hạn HOẶC conversation không truy
// cập được (xem api/ws.py). Phân biệt 2 ca bằng cách thử refresh token: refresh
// được + mở lại OK = ca token hết hạn; vẫn 4401 sau khi đã refresh = ca fatal
// (conversation mất/không quyền) → dừng, không loop 4401 vô hạn tốn pin.
const WS_AUTH_CLOSE = 4401;
const MAX_AUTH_RETRIES = 2;

export async function openConversationStream(
  conversationId: string,
  onEvent: (e: WsEvent) => void,
  onReconnect?: () => void,
  onFatal?: () => void,
): Promise<() => void> {
  let closed = false;
  let ws: WebSocket | null = null;
  let attempt = 0;
  let authRetries = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const scheduleReconnect = () => {
    attempt += 1;
    const delayMs = Math.min(1000 * 2 ** (attempt - 1), 15000);
    timer = setTimeout(() => connect(true), delayMs);
  };

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
      authRetries = 0;
      if (isReconnect) onReconnect?.();
    };
    ws.onmessage = (ev) => {
      try {
        onEvent(JSON.parse(String(ev.data)) as WsEvent);
      } catch {}
    };
    ws.onerror = () => ws?.close();
    ws.onclose = (ev) => {
      if (closed) return;
      const code = (ev as any)?.code;
      if (code === WS_AUTH_CLOSE) {
        // Đừng reconnect với đúng token chết (loop 4401 vô hạn). Thử refresh 1
        // lần rồi mở lại; hết lượt mà vẫn 4401 = fatal → dừng, báo caller.
        if (authRetries >= MAX_AUTH_RETRIES) {
          onFatal?.();
          return;
        }
        authRetries += 1;
        tryRefresh().then((ok) => {
          if (closed) return;
          if (ok) {
            attempt = 0;
            connect(true);
          } else {
            onFatal?.();
          }
        });
        return;
      }
      scheduleReconnect();
    };
  };

  await connect(false);
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    ws?.close();
  };
}
