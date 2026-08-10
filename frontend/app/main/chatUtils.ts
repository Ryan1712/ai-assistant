/**
 * Hàm thuần chuyển đổi Message[] → Row[] để hiển thị.
 * Tách ra file riêng để dễ unit-test và tránh phụ thuộc vào side-effect của chat.tsx.
 *
 * Mô hình mới (ChatGPT-style): mỗi conversation là 1 thread ĐỘC LẬP.
 * Không còn timeline xuyên conversation → không còn divider "— cuộc trò chuyện mới —".
 */
import type { Message } from "../../src/api/chat";
import type { Row } from "./chatTypes";

export const TOOL_LABELS: Record<string, string> = {
  create_project: "Tạo project",
  update_project: "Cập nhật project",
  list_projects: "Tra cứu project",
  create_task: "Tạo task",
  update_task: "Cập nhật task",
  list_tasks: "Tra cứu task",
  get_task: "Xem chi tiết task",
  assign_task: "Gán người vào task",
  unassign_task: "Bỏ gán task",
  add_task_update: "Cập nhật tiến độ",
  list_task_updates: "Tra lịch sử cập nhật",
  add_comment: "Thêm bình luận",
  list_comments: "Tra bình luận",
  create_skill: "Tạo skill",
  add_skill_version: "Cập nhật skill",
  grant_skill: "Cấp quyền skill",
  list_skills: "Tra cứu skill",
  use_skill: "Dùng skill",
  list_skill_grants: "Tra quyền skill",
  revoke_skill_grant: "Thu hồi quyền skill",
  list_users: "Tra danh bạ",
  add_employee: "Thêm vào danh sách nhân viên",
  lock_user: "Khóa tài khoản",
  unlock_user: "Mở khóa tài khoản",
  offboard_user: "Cho nghỉ việc",
  change_user_role: "Đổi vai trò",
  generate_report: "Tạo báo cáo",
  list_reports: "Tra báo cáo",
  create_report_schedule: "Tạo lịch báo cáo",
  list_report_schedules: "Tra lịch báo cáo",
  delete_report_schedule: "Hủy lịch báo cáo",
  list_audit_events: "Tra nhật ký",
  send_email: "Gửi email",
  create_instruction: "Tạo chỉ dẫn",
  update_instruction: "Cập nhật chỉ dẫn",
  list_instructions: "Tra chỉ dẫn",
  delete_instruction: "Xóa chỉ dẫn",
  list_portal_reports: "Tra báo cáo cổng CEO",
  get_portal_report: "Đọc báo cáo cổng CEO",
  list_voice_notes: "Tra ghi âm",
  get_voice_note: "Đọc ghi âm",
  list_task_attachments: "Tra tài liệu đính kèm",
  get_today_dashboard: "Tổng hợp hôm nay",
  create_note: "Tạo ghi chú",
  list_notes: "Tra ghi chú",
  search: "Tìm kiếm",
  list_notifications: "Tra thông báo",
  get_notification_preferences: "Tra cài đặt thông báo",
  set_notification_preference: "Đổi cài đặt thông báo",
  resolve_person: "Tra cứu người",
  resolve_task: "Tra cứu task",
  semantic_search: "Tìm theo ngữ nghĩa",
  delete_task: "Xóa task",
  delete_project: "Xóa project",
  list_memories: "Tra ghi nhớ",
  forget_memory: "Xóa ghi nhớ",
  add_example: "Lưu ví dụ xử lý",
  propose_actions: "Đề xuất hành động",
  create_directive: "Giao việc chính thức",
  get_directive_status: "Tra tình trạng việc đã giao",
  get_project_health: "Soi tình trạng project",
  get_progress_stats: "So sánh tiến độ kỳ này",
};

export function labelForTool(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
}

export function textOfMessage(m: Message): string {
  return m.content
    .map((b) => (b.type === "text" ? b.text : ""))
    .filter(Boolean)
    .join("\n");
}

/**
 * Dựng Row[] từ Message[] của 1 conversation đơn lẻ.
 * Mô hình mới: không còn cross-conversation, không chèn divider.
 */
export function messagesToRows(msgs: Message[]): Row[] {
  const out: Row[] = [];
  for (const m of msgs) {
    const text = textOfMessage(m);
    if (text)
      out.push({
        key: m.id,
        kind: m.role === "user" ? "user" : "assistant",
        text,
        voiceNoteId: m.voice_note_id,
        isSeed: m.is_seed,
      });
    // Lượt AI thuần thao tác (tạo task, gán người...) không có text — hiển thị
    // nhãn hành động để người dùng biết AI đã làm gì trong cuộc hội thoại.
    for (const b of m.content) {
      if (b.type === "tool_use") {
        if (b.name === "suggest_replies") {
          const options = (b.input as { options?: unknown })?.options;
          if (Array.isArray(options) && options.length > 0)
            out.push({ key: `${m.id}-${b.id}`, kind: "choices", options: options as string[] });
        } else {
          out.push({ key: `${m.id}-${b.id}`, kind: "system", text: labelForTool(b.name) });
        }
      }
    }
  }
  return out;
}
