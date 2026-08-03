# Public Reports API — thiết kế

**Ngày:** 2026-08-03
**Trạng thái:** Đã duyệt (brainstorm), chờ viết plan triển khai.

## Bối cảnh

Dev bên app mobile 9learning gửi tài liệu mô tả 1 cơ chế đã tồn tại ở backend
NestJS khác của họ: 3 endpoint đọc report (`list`, `detail`, `content`) không
cần đăng nhập, xác thực bằng header tĩnh `X-App-Bundle-Id` khớp allowlist
trong env, cấp quyền đọc *toàn bộ* report kể cả `draft`.

Yêu cầu thực tế: app mobile 9learning cần gọi API tương tự **từ backend
`ai-assistant`** để đọc report mà không cần user đăng nhập trước.

## Vì sao không bê nguyên cơ chế gốc

- `Report` hiện có (`backend/app/models.py:509`) gắn chặt `workspace_id`,
  chỉ CEO xem (`backend/app/api/reports.py`), tự sinh Excel từ dữ liệu task
  nội bộ (`report_service.generate_report`). Đây là báo cáo quản trị nội bộ,
  khác bản chất hoàn toàn với "báo cáo public" mà app 9learning cần.
- Cấp scope "bundle-id → super_admin thấy hết kể cả draft" phù hợp với hệ
  thống 9learning gốc (không multi-tenant theo kiểu ai-assistant), nhưng nếu
  bê nguyên vào đây sẽ vi phạm nguyên tắc "mọi bảng (trừ `workspaces`) có
  `workspace_id`; mọi query phải lọc theo workspace" (CLAUDE.md) — bundle-id
  không xác thực danh tính nên không được phép chọn workspace tuỳ ý.
- Vì vậy: tách hẳn model mới, thu hẹp phạm vi lộ dữ liệu xuống chỉ nội dung
  đã `published`, và giới hạn vào **1 workspace cố định** cấu hình qua env.

## Model mới: `PublicReport`

Bảng riêng, không đụng `Report`/`report_service.py` hiện có.

```python
class PublicReport(Base):
    __tablename__ = "public_reports"
    id: Mapped[uuid.UUID]
    workspace_id: Mapped[uuid.UUID]  # FK workspaces.id
    title: Mapped[str]
    description: Mapped[str | None]
    status: Mapped[PublicReportStatus]  # draft | published
    content_type: Mapped[str]           # vd text/html, application/pdf, image/*
    file_path: Mapped[str]              # tái dùng storage_dir local, giống Report.file_path
    size_bytes: Mapped[int]
    created_by: Mapped[uuid.UUID]       # FK users.id
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

Storage: tái dùng `get_settings().storage_dir` + path cục bộ (không thêm S3
— file gốc 9learning nhắc `s3Key` nhưng repo này chưa có S3 integration).

## Xác thực: bundle-id scope

Dependency mới song song `get_current_user` (`backend/app/deps.py`):

- Đọc header `X-App-Bundle-Id`.
- So khớp với env `PUBLIC_APP_BUNDLE_IDS` (danh sách phân tách dấu phẩy,
  mặc định rỗng = tính năng tắt hoàn toàn).
- Khớp → trả về scope gắn cứng với `PUBLIC_REPORT_WORKSPACE_ID` (env, 1
  workspace cố định — KHÔNG phải giá trị do client truyền).
- Không khớp và không có Bearer token hợp lệ → `401`.

Rủi ro bundle-id không phải bí mật (decompile app lấy được) — **chấp nhận
có chủ đích**, vì nội dung lộ ra qua kênh này chỉ giới hạn ở report đã
`published` của 1 workspace cố định, không phải dữ liệu nhạy cảm hay đa
tenant.

## Endpoint đọc (không cần đăng nhập, qua bundle-id hoặc JWT)

Router mới `/api/v1/public-reports`, dùng chung dependency
`get_bundle_or_user`:

- `GET /api/v1/public-reports` — list, **chỉ `status=published`** (khác
  file gốc 9learning: ở đây `draft` là nội dung CEO đang soạn, không được
  lộ qua kênh không-đăng-nhập).
- `GET /api/v1/public-reports/{id}` — chi tiết; `404` nếu không tồn tại,
  không `published`, hoặc khác workspace cố định.
- `GET /api/v1/public-reports/{id}/content` — trả file trực tiếp
  (`FileResponse`), kèm header `X-Content-Type-Options: nosniff`,
  `Cache-Control: no-store`.

## Endpoint quản trị (CEO, JWT bình thường)

Cùng router hoặc router riêng, dùng `Depends(get_current_user)` +
`require_ceo` (pattern có sẵn ở `permissions.py`):

- Tạo `PublicReport` (upload file + metadata, mặc định `draft`).
- Sửa metadata.
- Publish / unpublish (đổi `status`).
- Xoá.

## Việc cần làm (tổng quan, chi tiết ở plan triển khai)

1. Model `PublicReport` + enum `PublicReportStatus` + migration Alembic.
2. Config: `PUBLIC_APP_BUNDLE_IDS`, `PUBLIC_REPORT_WORKSPACE_ID` trong
   `app/config.py` + `.env.example`.
3. Dependency `get_bundle_or_user` trong `app/deps.py`.
4. Service `public_report_service.py`: list/get/content (đọc, lọc
   published) + create/update/publish/delete (ghi, CEO).
5. Router `app/api/public_reports.py`, đăng ký vào `main.py`.
6. Schemas Pydantic (`PublicReportOut`, request tạo/sửa).
7. Tests: bundle-id hợp lệ/không hợp lệ, tắt hoàn toàn khi env rỗng, không
   lộ draft, không lộ workspace khác, CEO CRUD, phân quyền JWT vẫn hoạt
   động song song.
8. `python scripts/export_openapi.py` sau khi route ổn định (đổi API
   contract cho FE/app).

## Ngoài phạm vi (chưa làm ở lần này)

- Không thêm rate-limit hay secret riêng ngoài bundle-id (đã chốt: chấp
  nhận rủi ro bundle-id tĩnh).
- Không hỗ trợ nhiều workspace qua bundle-id (chỉ 1 workspace cố định).
- Không có UI quản trị PublicReport trên mobile app hiện có (endpoint ghi
  chỉ cần hoạt động qua API/Swagger trước; UI có thể làm sau nếu cần).
