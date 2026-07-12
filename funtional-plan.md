# Trợ lý AI Cá nhân — Quản lý Công việc & Điều phối Đội nhóm
## Bản phân tích chức năng (Functional Plan)

---

## 1. Định vị sản phẩm

Một **app di động đa nền tảng (iOS + Android)** đóng vai trợ lý AI — **"bộ não thứ hai" của CEO**: luôn nhớ bối cảnh, đồng thời là **lớp điều phối** để manager và nhân viên cập nhật công việc, còn CEO nhận được bức tranh tổng hợp gần như theo thời gian thực.

**Giao diện chính là một khung chat hội thoại.** Gần như **mọi thao tác** (tạo task, giao việc, phân quyền, cập nhật tiến độ, gen báo cáo, gửi mail, khóa tài khoản...) đều thực hiện **bằng cách nhắn cho AI** — không đi vào từng menu. AI làm bất cứ điều gì bạn yêu cầu **nếu bạn có quyền**; nếu vượt quyền, AI từ chối và báo rõ.

**Đây là sản phẩm đa công ty (multi-tenant):** mỗi CEO sở hữu **một không gian công ty riêng**, dữ liệu **cách ly tuyệt đối** — không công ty nào thấy được dữ liệu của công ty khác.

Ba giá trị cốt lõi làm kim chỉ nam cho toàn bộ chức năng:

1. **Không bao giờ quên bối cảnh** — AI luôn biết bạn là ai, đang làm gì, ai trong đội.
2. **Thông tin task là nguồn chuẩn duy nhất** — mô tả một lần, mọi người truy vấn ra thông tin giống nhau và mới nhất, không lệ thuộc trí nhớ người báo.
3. **Tự động tổng hợp → báo cáo** — cập nhật rải rác của đội tự gom thành báo cáo/Excel cho CEO.

---

## 2. Các đối tượng hệ thống quản lý (mô hình khái niệm)

| Đối tượng | Thông tin chính nắm giữ | Liên kết với |
|---|---|---|
| **Công ty (Workspace)** | Chủ sở hữu (1 CEO), gói dịch vụ, mã mời, cấu hình | Chứa toàn bộ dữ liệu của công ty; **cách ly với công ty khác** |
| **Người dùng chủ (CEO)** | Hồ sơ, vai trò, bối cảnh đang làm, danh mục skill cá nhân | Sở hữu 1 công ty |
| **Tài khoản** | Thông tin đăng nhập, vai trò, **trạng thái (hoạt động / bị khóa)**, ngày tạo | Gắn 1 nhân sự, thuộc 1 công ty |
| **Thiết bị** | Mã thiết bị (device UUID), tên thiết bị, thời điểm đăng nhập gần nhất (log đầy đủ, không giới hạn) | Gắn 1 tài khoản |
| **Cuộc chat** | Mạch hội thoại, hàng đợi yêu cầu, thời gian, ngữ cảnh gắn kèm | Gắn 1 người dùng |
| **Instruction** | Chỉ dẫn/câu hỏi mẫu định hình cách AI hành xử, phiên bản, người tạo | Gắn 1 công ty (AI nạp) |
| **Skill** | Loại (hồ sơ năng lực / gói tri thức nghiệp vụ), nội dung, phiên bản, quyền truy cập | Gắn công ty; gắn người và/hoặc task |
| **Project** | Tên, mục tiêu, trạng thái, thời hạn, người phụ trách | Chứa nhiều task |
| **Task** | Mô tả, người thực hiện, trạng thái, % hoàn thành, deadline, mức ưu tiên, lịch sử cập nhật | Thuộc 1 project; gắn 1+ người; có thể gắn skill |
| **Nhân sự** | Họ tên, vai trò (Manager / Nhân viên), **thuộc manager nào**, task đang giữ, skill được cấp | Thực hiện task |
| **Ghi chú (Note)** | Nội dung (text/giọng nói), ngày, tag | Gắn ngày / người / task / project |
| **Ghi âm (Voice note)** | File âm thanh, transcript (đúng ngôn ngữ nói), tag, thời gian | Gắn task / project / người |
| **Báo cáo** | Nguồn (nội bộ **hoặc cổng ceo.9learning.edu.vn**), loại, phạm vi, kỳ, dữ liệu, file xuất | Tổng hợp từ task; gắn công ty |
| **Gói dịch vụ (Subscription)** | Loại (Basic / Advanced), trạng thái | Gắn 1 công ty |
| **Thông báo** | Sự kiện kích hoạt, người nhận, nội dung, trạng thái đọc | Gắn task / tài khoản + người |

---

## 3. Bảo mật, Vai trò & Ma trận tương tác

### Lớp bảo mật cao nhất — Cách ly theo công ty (multi-tenant)

- Mỗi CEO = **một công ty**. **Mọi phân quyền đều nằm TRONG phạm vi một công ty.**
- **Không người dùng nào — kể cả manager — thấy được dữ liệu của công ty khác.** Đây là lớp bảo mật trên cùng, nằm **trên cả** ma trận vai trò bên dưới.
- Nhân viên tự đăng ký phải **gắn vào đúng công ty** qua **mã mời** của công ty đó — đảm bảo không lộ thông tin sang công ty khác.

### Ba vai trò và quyền hạn (trong một công ty)

**CEO (bạn)** — Toàn quyền trong công ty của mình: tạo/sửa project & task, mô tả task, cấu hình **Instruction & Skill** (chỉ CEO sửa nội dung), xem toàn bộ tiến độ, yêu cầu báo cáo/Excel, đọc báo cáo từ cổng CEO, gửi mail cho mọi vai trò, nhận mọi thông báo. **Quản trị:** tạo tài khoản cho **mọi vai trò** (nhân viên/manager/CEO), xem log thiết bị, **khóa/mở khóa tài khoản** (chỉ CEO).

**Manager** — Xem project/task được phân; cập nhật tiến độ (của mình & nhân viên dưới quyền); tổng hợp nhóm; dùng skill được cấp; gửi mail cho CEO/manager/nhân viên; nhận thông báo liên quan.

**Nhân viên** — Xem task được giao; cập nhật tiến độ của mình; **dùng skill được cấp để lấy thông tin task chuẩn** rồi báo cáo lại; gửi mail cho CEO & manager; nhận thông báo liên quan.

### Ma trận "ai được tương tác với ai"

|  | CEO | Manager | Nhân viên |
|---|:---:|:---:|:---:|
| **CEO** | — | ✅ | ✅ |
| **Manager** | ✅ | ✅ | ✅ |
| **Nhân viên** | ✅ | ✅ | ❌ |

> Quy tắc duy nhất bị cấm: **Nhân viên ⇎ Nhân viên**. Manager ↔ Manager: **được tương tác tự do**.

### Cây phân cấp & thực thi quyền

- Hệ thống có **cây phân cấp báo cáo**: mỗi nhân viên thuộc một manager → quyết định ai xem được gì và ai nhận thông báo nào.
- **Quyền được kiểm tra ngay tại lệnh chat** (xem Mục 5.6): ai ra lệnh gì, AI thực hiện nếu có quyền; nếu không thì từ chối và báo rõ.

---

## 4. Instruction & Skill — kiến thức AI nạp vào

AI hoạt động dựa trên hai lớp kiến thức mà CEO cấu hình được; khi có thay đổi, AI **nạp lại (load)** ngay.

### 4.1 Instruction (chỉ dẫn cho AI)

- Là các **chỉ dẫn / câu hỏi mẫu** định hình cách AI hành xử: quy tắc nghiệp vụ, bối cảnh công ty, giọng điệu, ưu tiên khi trả lời.
- CEO cập nhật → AI **nạp lại ngay**, áp dụng cho các phản hồi sau.

### 4.2 Skill — hai loại

- **Hồ sơ năng lực (skill *của người*)** — mô tả người này (hoặc CEO) làm được gì. Dùng để AI hiểu năng lực đội, gợi ý phân task đúng người.
- **Gói tri thức nghiệp vụ (skill *gắn task/project*)** — CEO định nghĩa **một lần** toàn bộ thông tin của task A, B, C rồi đóng gói thành "skill".

### 4.3 Cơ chế "chống quên" (điểm mấu chốt)

Khi nhân viên **"dùng skill"**, họ **không** nhận bản copy tĩnh mà **truy vấn thẳng vào trạng thái hiện tại của task**. Vì nguồn là **một và duy nhất**, có đánh **phiên bản**, nên: (a) thông tin luôn mới nhất, (b) không lệ thuộc trí nhớ người báo, (c) mọi người đọc cùng một sự thật. Đây cũng là cách **CEO lấy "cập nhật mới nhất của task A, B, C"**.

### 4.4 Vòng đời & nạp lại

Tạo → **Cấp quyền** → **Sử dụng** → **Cập nhật** (tăng phiên bản, chỉ CEO) → Thu hồi. Mỗi lần cập nhật Instruction/Skill → **AI load lại**, không cần khởi động lại. Có nhật ký: ai đổi gì, khi nào.

---

## 5. Trải nghiệm Chat với AI — LÕI SẢN PHẨM

Đây là nơi bạn dành phần lớn thời gian, nên phải **nhanh, mượt, không chặn**. Mô hình tương tác lấy cảm hứng từ Claude Code.

### 5.1 Ô chat không bao giờ bị khóa
- **Gõ và gửi yêu cầu bất cứ lúc nào**, kể cả khi AI đang trả lời yêu cầu trước — luồng suy nghĩ không bị ngắt.

### 5.2 Hàng đợi yêu cầu (xử lý tuần tự)
- Nhiều yêu cầu liên tiếp → AI đang bận thì yêu cầu mới **vào hàng đợi**, xử lý **lần lượt theo đúng thứ tự**.
- **Hiển thị rõ**: cái nào đang xử lý, cái nào đang chờ ("đang xử lý 1/3").
- Trước khi tới lượt: **sửa / xóa / sắp xếp lại** hoặc **chèn ưu tiên**.
- **Khi một yêu cầu lỗi:** AI **bỏ qua, làm tiếp** yêu cầu kế, và **báo rõ cái nào lỗi + lý do** để bạn sửa.

### 5.3 Điều khiển khi đang chạy
- **Dừng ngay** yêu cầu đang chạy (như Esc), **hủy** một yêu cầu đang chờ, hoặc **dừng tất cả**.

### 5.4 Streaming
- Câu trả lời **hiện dần từng phần** → nhanh, mượt. Có chỉ báo trạng thái ("đang tạo báo cáo"...).

### 5.5 Ngữ cảnh liên tục & nối tiếp
- AI **nhớ toàn bộ mạch hội thoại** + bối cảnh (project, task, người).
- Yêu cầu sau **thấy kết quả** yêu cầu trước ("tạo task X" → "giao task đó cho An").
- Mọi cuộc chat được **lưu & tìm lại được**.

### 5.6 Chat để làm MỌI việc — kiểm tra quyền tại chỗ (agentic)
- **Mọi thao tác đều làm qua chat**, không cần vào từng menu.
- AI thực hiện **chỉ khi người ra lệnh có quyền**. Vượt quyền → **từ chối và báo rõ** (ví dụ: nhân viên đòi khóa tài khoản CEO → *"Bạn không có quyền làm điều này"*).
- Hành động nhạy cảm (khóa tài khoản, xóa, gửi mail) → AI **xác nhận trước khi thực hiện**.

### 5.7 Mất mạng & tiếp tục công việc
- Mất mạng / đóng app → hàng đợi **không tự chạy tiếp**. Việc dang dở **được ghi nhớ**; chỉ khi bạn gõ **"tiếp tục công việc"** thì AI mới làm nốt.

---

## 6. Chi tiết các nhóm chức năng

### 6.1 Đăng ký, Đăng nhập & Quản lý tài khoản/thiết bị

**Đăng ký & Đăng nhập**
- **Nút đăng ký cho nhân viên:** nhân viên **tự tạo tài khoản** (self sign-up), **gắn vào đúng công ty qua mã mời**.
- **Tài khoản CEO mặc định:** hệ thống **luôn có sẵn một tài khoản CEO** (quản trị gốc của công ty).
- **CEO tạo tài khoản:** CEO tạo được tài khoản cho **bất kỳ vai trò nào** — nhân viên, manager, CEO. (Manager không tạo tài khoản.)
- Đăng nhập thành công → vào đúng không gian công ty & vai trò.

**Ghi nhận thiết bị (không giới hạn số lượng, nhưng luôn log)**
- Mỗi lần đăng nhập lưu **device UUID + tên thiết bị + thời điểm**.
- Một tài khoản đăng nhập bao nhiêu thiết bị cũng được; **mọi thiết bị & lần đăng nhập đều được log** để CEO theo dõi.

**Khóa / Mở khóa TÀI KHOẢN (chỉ CEO)**
- CEO **khóa cả tài khoản** → **đăng xuất khỏi mọi thiết bị**, **không đăng nhập lại được** ở bất kỳ đâu.
- Khi bị khóa cố đăng nhập → tại màn hình đăng nhập có thể **gửi yêu cầu mở khóa** → **báo cho CEO** (kèm tên & mã thiết bị).
- CEO **mở khóa** → dùng lại. Mọi lần khóa/mở khóa vào **nhật ký**.

### 6.2 Bộ nhớ bền vững + Thiết lập
- AI nhớ **bạn là ai, đang làm gì**, xuyên suốt các phiên.
- CEO **"dựng thế giới"** (project, task, nhân sự, vai trò, skill) — tất cả qua chat; luôn phản ánh hiện trạng.

### 6.3 Ghi âm & hỗ trợ giọng nói
- **Ghi âm nhanh (một chạm)** → lưu ngay.
- Chuyển giọng nói → văn bản, **tự nhận diện ngôn ngữ**: nói tiếng nào lưu tiếng đó, **không tự dịch**.
- Gắn tag / task / project; **trích xuất bất cứ lúc nào** (nghe lại, đọc transcript, tìm theo từ khóa/ngày).
- Có thể **biến ghi âm thành task/cập nhật** bằng cách yêu cầu AI trong chat.

### 6.4 Email theo vai trò
- Ba vai trò gửi/nhận mail, **tuân ma trận tương tác** (nhân viên ⇎ nhân viên).
- AI **hỗ trợ soạn nhanh** và **gắn ngữ cảnh** tới task/project cụ thể.

### 6.5 Tổng hợp tiến độ + Báo cáo / Excel
- Đội cập nhật tiến độ → AI **gom về** theo project/người/kỳ.
- CEO **yêu cầu báo cáo qua chat** → **tóm tắt trên màn hình + file Excel** (task, trạng thái, %, người phụ trách, cập nhật mới, mốc thời gian).
- Có **mẫu mặc định** + **tùy biến cột ngay trong chat** ("thêm cột deadline", "chỉ lấy task chưa xong").
- *(Nâng cao)* Báo cáo **định kỳ tự động**.

### 6.6 Push notification (setup sẵn — bật mặc định)
- **Hoạt động ngay từ đầu.** Bắn thông báo cho **MỌI cập nhật tiến độ** tới người liên quan (không lọc).
- Các sự kiện khác: task mới được giao, sắp tới hạn, có mail/được nhắc tên, báo cáo sẵn sàng, **yêu cầu mở khóa tài khoản** (bắn cho CEO).
- **Kênh:** trong app / email / mobile. (Người dùng có thể tắt bớt loại thông báo nếu quá nhiều.)

### 6.7 Quản lý Instruction & Skill (kiến thức AI nạp)
- CEO **tạo/sửa Instruction & Skill qua chat** (xem khái niệm ở Mục 4).
- Cập nhật → AI **nạp lại (load) ngay**, áp dụng cho phản hồi sau; có phiên bản & nhật ký.

### 6.8 Tích hợp cổng báo cáo CEO (ceo.9learning.edu.vn)
- App **kết nối & đọc báo cáo** từ cổng **ceo.9learning.edu.vn**.
- CEO **hỏi AI ngay trong chat** về nội dung báo cáo ("tóm tắt báo cáo tuần này", "báo cáo X nói gì về doanh thu").
- AI dùng báo cáo làm **nguồn dữ liệu**, đối chiếu với tiến độ task trong app.
- **Chỉ CEO của đúng công ty** truy cập được báo cáo của mình (cách ly đa công ty).

### 6.9 Dashboard "Hôm nay"
- Màn hình tổng hợp nhanh khi mở app: **task của hôm nay** (đến hạn / đang làm / mới cập nhật) và **note/ghi chú trong ngày**.
- Chỉ số nhanh: task trễ hạn, task đang chờ mình, cập nhật mới từ đội.
- Mỗi vai trò thấy dashboard **theo phạm vi quyền** của mình.

### 6.10 Gói dịch vụ / Subscription (tạm mock)
- Hai gói: **Basic** và **Advanced**. Phần này **để mock/giả lập** — chưa gắn thanh toán thật; chỉ dựng khung để bật/tắt tính năng theo gói.
- Phân chia tính năng (tạm thời, sẽ chốt sau):

| Nhóm | Basic | Advanced |
|---|---|---|
| Chat + task + báo cáo cơ bản | ✅ | ✅ |
| Giới hạn project / nhân viên / skill | Có giới hạn | Mở rộng |
| Tích hợp cổng báo cáo CEO | ❌ | ✅ |
| Báo cáo định kỳ tự động | ❌ | ✅ |
| Dashboard đầy đủ | Rút gọn | ✅ |
| Instruction/Skill AI nạp | Giới hạn | Không giới hạn |

---

## 7. Các luồng công việc chính (User journeys)

**Luồng 1 — CEO khởi tạo:** Nhắn AI dựng project → tạo task A/B/C + mô tả → đóng gói thành skill → phân người + cấp quyền skill.

**Luồng 2 — Nhân viên thực thi:** Đăng nhập (thiết bị được log) → nhận thông báo được giao → **dùng skill lấy thông tin chuẩn** → làm → cập nhật tiến độ → hệ thống **bắn thông báo** lên manager & CEO.

**Luồng 3 — CEO nắm tình hình & báo cáo:** Nhắn AI xem tổng hợp / mở **Dashboard Hôm nay** → yêu cầu báo cáo (tùy biến cột) → nhận **tóm tắt + Excel**.

**Luồng 4 — Ghi âm ý tưởng:** Ghi âm nhanh → AI transcribe (đúng ngôn ngữ) & gắn project → tìm lại hoặc biến thành task.

**Luồng 5 — Khóa & mở khóa tài khoản:** CEO nhắn AI **khóa tài khoản** nhân viên → out mọi thiết bị, không vào lại được → người đó **gửi yêu cầu mở khóa** → CEO **nhận thông báo** → mở khóa hoặc giữ.

**Luồng 6 — Gửi nhiều yêu cầu cùng lúc:** CEO gõ liên tiếp 3 lệnh không chờ → AI xếp hàng đợi, xử lý 1/3 → 2/3 → 3/3; nếu lệnh 2 lỗi thì bỏ qua làm tiếp lệnh 3 rồi báo lỗi lệnh 2.

**Luồng 7 — Vượt quyền:** Nhân viên đòi "khóa tài khoản CEO" → AI kiểm tra quyền → **từ chối**: *"Bạn không có quyền làm điều này."*

**Luồng 8 — Hỏi về báo cáo cổng CEO:** CEO nhắn "tóm tắt báo cáo doanh thu tuần này" → AI **đọc báo cáo từ ceo.9learning.edu.vn** → tóm tắt & đối chiếu với tiến độ task, ngay trong chat.

---

## 8. Chức năng nền tảng nên bổ sung (những khoảng trống nên lấp)

- **Trạng thái & vòng đời task**: Chưa bắt đầu / Đang làm / Bị chặn / Hoàn thành — kèm ưu tiên & deadline.
- **Nhật ký thay đổi**: ai cập nhật gì/khi nào; ai đăng nhập từ thiết bị nào; lịch sử khóa/mở tài khoản; lịch sử sửa Instruction/Skill.
- **Thảo luận / bình luận trong task** + đính kèm tài liệu.
- **Tìm kiếm xuyên suốt**: task, ghi âm, note, người, skill, lịch sử chat, báo cáo.
- **Phân quyền chi tiết trên skill**: ai được xem / sửa / dùng.
- **Xử lý khi nhân sự nghỉ hoặc đổi vai trò**: bàn giao task + khóa tài khoản.

---

## 9. Các quyết định đã chốt (Design decisions)

- **Nền tảng:** app di động **đa nền tảng (iOS + Android)**.
- **Đa công ty (multi-tenant):** mỗi CEO một công ty, **cách ly dữ liệu tuyệt đối**; nhân viên đăng ký **gắn công ty qua mã mời**.
- **Cách vận hành:** làm **mọi việc qua chat**; AI thực thi nếu có quyền, không thì từ chối và báo rõ.
- **Manager ↔ Manager:** tương tác tự do. **Cây phân cấp:** mỗi nhân viên thuộc một manager.
- **Instruction & Skill:** CEO cấu hình; cập nhật → **AI nạp lại ngay**. Chỉ CEO sửa nội dung.
- **Khóa tài khoản:** khóa **cả tài khoản** (out mọi thiết bị); **chỉ CEO** khóa/mở.
- **Số thiết bị:** không giới hạn, **log đầy đủ**.
- **Thông báo:** **setup sẵn**, bắn **mọi** cập nhật.
- **Ghi âm:** **tự nhận diện ngôn ngữ**, nói tiếng nào lưu tiếng đó, không dịch.
- **Hàng đợi lỗi:** bỏ qua, làm tiếp, báo lỗi. **Mất mạng:** không tự chạy tiếp, chỉ tiếp tục khi gõ "tiếp tục công việc".
- **Báo cáo:** mẫu mặc định + tùy biến cột qua chat; **tích hợp đọc báo cáo từ ceo.9learning.edu.vn**.
- **Dashboard "Hôm nay":** tổng hợp **task + note trong ngày**.
- **Subscription:** 2 gói **Basic / Advanced** — **tạm mock**.
- **Tạo tài khoản:** nhân viên tự đăng ký (mã mời); CEO tạo cho mọi vai trò; luôn có tài khoản CEO mặc định; manager không tạo.

---

## 10. Gợi ý phân giai đoạn (prototype-first)

Sản phẩm là **app mobile đa nền tảng, đa công ty** ngay từ đầu.

- **Giai đoạn 1 — MVP:** **Cách ly đa công ty (multi-tenant) + mã mời**; đăng ký/đăng nhập theo vai trò + log thiết bị; **khung chat + hàng đợi tuần tự + streaming + dừng/hủy + bỏ qua khi lỗi + kiểm tra quyền tại lệnh**; bộ nhớ + thiết lập; **Instruction & Skill (cập nhật → AI nạp lại)**; cập nhật tiến độ; tổng hợp + Excel cơ bản.
- **Giai đoạn 2:** Ma trận tương tác + cây phân cấp đầy đủ; **khóa/mở tài khoản (chỉ CEO)** + thông báo & yêu cầu mở khóa; email theo vai trò; push notification (setup sẵn, mọi cập nhật); **Dashboard "Hôm nay"**; "tiếp tục công việc".
- **Giai đoạn 3:** Ghi âm (tự nhận diện ngôn ngữ) + tìm kiếm; **tích hợp cổng báo cáo ceo.9learning.edu.vn**; báo cáo định kỳ tự động + tùy biến cột; **khung subscription mock (Basic/Advanced)**; sắp xếp lại/chèn ưu tiên trong hàng đợi.
- **Giai đoạn 4 — nâng cao:** AI bóc việc từ ghi âm; gợi ý phân task theo hồ sơ năng lực; nhật ký & phân quyền chi tiết trên skill.

---

## Phụ lục — Ghi chú so với bản plan trước (2026-07-12)

Bản này thay bản cũ. Các điểm bản cũ có nhưng bản mới **không nhắc lại** — đội dev vẫn giữ nguyên trừ khi có quyết định ngược lại (đã hiện thực trong backend):

1. **Thực thi quyền ở tầng backend/service** (không ở prompt); danh tính lấy từ phiên đăng nhập; hành động nhạy cảm xác nhận 2 bước do backend cưỡng chế. (Trùng quy ước CLAUDE.md.)
2. **Cấu trúc 2 lớp của skill**: nội dung CEO soạn (có phiên bản) + trạng thái sống của task ghép lúc truy vấn.
3. **Hàng đợi — yêu cầu phụ thuộc vào yêu cầu đã lỗi**: báo rõ và bỏ qua, không tự chọn đối tượng thay thế.
4. **Ma trận tương tác chỉ áp cho email & nhắn trực tiếp**; bình luận trong task chung không bị giới hạn.

Các điểm bản mới **thay đổi/lược bỏ có chủ đích cần xác nhận lại với product**:
- Bỏ khái niệm **CEO gốc (root)** và quy tắc "chỉ CEO gốc khóa được tài khoản vai trò CEO" → bản mới chỉ còn "tài khoản CEO mặc định".
- **Email OAuth send-as** (gửi từ chính địa chỉ người gửi) không còn được nhắc → cần chốt lại cách gửi mail.
- Flow vào công ty đổi từ **lời mời kèm vai trò + manager** sang **self sign-up bằng mã mời chung** của công ty.
