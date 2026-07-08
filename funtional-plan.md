# Trợ lý AI Cá nhân — Quản lý Công việc & Điều phối Đội nhóm
## Bản phân tích chức năng (Functional Plan)

---

## 1. Định vị sản phẩm

Một **app di động đa nền tảng (iOS + Android)** đóng vai trợ lý AI — **"bộ não thứ hai" của CEO**: luôn nhớ bối cảnh, đồng thời là **lớp điều phối** để manager và nhân viên cập nhật công việc, còn CEO nhận được bức tranh tổng hợp gần như theo thời gian thực.

**Giao diện chính là một khung chat hội thoại.** Gần như **mọi thao tác** (tạo task, giao việc, phân quyền, cập nhật tiến độ, gen báo cáo, gửi mail, khóa tài khoản...) đều thực hiện **bằng cách nhắn cho AI** — không đi vào từng menu. AI làm bất cứ điều gì bạn yêu cầu **nếu bạn có quyền**; nếu vượt quyền, AI từ chối và báo rõ. Vì vậy trải nghiệm chat phải nhanh và mượt (xem Mục 5).

Ba giá trị cốt lõi làm kim chỉ nam cho toàn bộ chức năng:

1. **Không bao giờ quên bối cảnh** — AI luôn biết bạn là ai, đang làm gì, ai trong đội.
2. **Thông tin task là nguồn chuẩn duy nhất** — mô tả một lần, mọi người truy vấn ra thông tin giống nhau và mới nhất, không lệ thuộc trí nhớ người báo.
3. **Tự động tổng hợp → báo cáo** — cập nhật rải rác của đội tự gom thành báo cáo/Excel cho CEO.

Toàn bộ vận hành trên nền **kiểm soát truy cập chặt**: mỗi người một tài khoản, mọi thiết bị được ghi log, và CEO nắm quyền khóa/mở khóa tài khoản.

---

## 2. Các đối tượng hệ thống quản lý (mô hình khái niệm)

| Đối tượng | Thông tin chính nắm giữ | Liên kết với |
|---|---|---|
| **Người dùng chủ (CEO)** | Hồ sơ, vai trò, bối cảnh đang làm, danh mục skill cá nhân | Sở hữu toàn bộ project |
| **Tài khoản** | Thông tin đăng nhập, vai trò, **trạng thái (hoạt động / bị khóa)**, ngày tạo | Gắn 1 nhân sự |
| **Thiết bị** | Mã thiết bị (device UUID), tên thiết bị, thời điểm đăng nhập gần nhất (log đầy đủ, không giới hạn số lượng) | Gắn 1 tài khoản |
| **Cuộc chat** | Mạch hội thoại, hàng đợi yêu cầu, thời gian, ngữ cảnh gắn kèm | Gắn 1 người dùng |
| **Project** | Tên, mục tiêu, trạng thái, thời hạn, người phụ trách | Chứa nhiều task |
| **Task** | Mô tả (do CEO định nghĩa), người thực hiện, trạng thái, % hoàn thành, deadline, mức ưu tiên, lịch sử cập nhật | Thuộc 1 project; gắn 1+ người; có thể gắn skill |
| **Nhân sự** | Họ tên, vai trò (Manager / Nhân viên), **thuộc manager nào**, task đang giữ, skill được cấp | Thực hiện task |
| **Skill** | Loại (hồ sơ năng lực / gói tri thức nghiệp vụ), nội dung, phiên bản, quyền truy cập, người tạo | Gắn với người và/hoặc task |
| **Ghi âm (Voice note)** | File âm thanh, bản chuyển văn bản (đúng ngôn ngữ nói), tag, thời gian | Gắn task / project / người |
| **Báo cáo** | Loại, phạm vi, kỳ, dữ liệu tổng hợp, file xuất | Tổng hợp từ task |
| **Thông báo** | Sự kiện kích hoạt, người nhận, nội dung, trạng thái đọc | Gắn task / tài khoản + người |

---

## 3. Vai trò & Ma trận tương tác

### Ba vai trò và quyền hạn

**CEO (bạn)** — Toàn quyền: tạo/sửa project & task, mô tả task, cấp skill (**chỉ CEO được sửa nội dung skill**), xem toàn bộ tiến độ, yêu cầu báo cáo/Excel, gửi mail cho mọi vai trò, nhận mọi thông báo liên quan, ghi âm. **Quản trị:** tạo tài khoản cho **mọi vai trò** (nhân viên/manager/CEO), xem log thiết bị của từng người, **khóa/mở khóa tài khoản** (chỉ CEO).

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

- Hệ thống có **cây phân cấp báo cáo**: mỗi nhân viên thuộc một manager. Điều này quyết định **ai xem được gì** và **ai nhận thông báo nào**.
- **Quyền được kiểm tra ngay tại lệnh chat**, không có menu quản trị riêng (xem Mục 5.6). Ai ra lệnh gì, AI thực hiện nếu người đó có quyền; nếu không thì từ chối và báo rõ.

---

## 4. Khái niệm "Skill" — điểm khác biệt của hệ thống

Đây là phần cốt lõi giải quyết bài toán "không còn bị quên". Có **hai loại skill**:

### 4.1 Hai loại skill

- **Hồ sơ năng lực (skill *của người*)** — mô tả người này (hoặc chính CEO) làm được gì, chuyên môn gì. Dùng để: AI hiểu năng lực đội, gợi ý phân task đúng người.
- **Gói tri thức nghiệp vụ (skill *gắn task/project*)** — CEO định nghĩa **một lần** toàn bộ thông tin của task A, B, C (bối cảnh, yêu cầu, tiêu chí hoàn thành, tài liệu liên quan) rồi đóng gói thành "skill".

### 4.2 Cơ chế "chống quên" (điểm mấu chốt)

Khi nhân viên **"dùng skill"**, họ **không** nhận một bản copy tĩnh mà **truy vấn thẳng vào trạng thái hiện tại của task** trong hệ thống. Vì nguồn thông tin là **một và duy nhất**, lại có đánh **phiên bản**, nên:

- **(a)** Thông tin lấy ra luôn là mới nhất.
- **(b)** Không lệ thuộc trí nhớ của người báo cáo.
- **(c)** Mọi người cùng đọc một sự thật.

Chính cơ chế này cũng là cách **CEO lấy "cập nhật mới nhất của task A, B, C"** — bạn và nhân viên dùng cùng một nguồn.

**Cấu trúc 2 lớp của một skill** (để "có phiên bản" và "luôn mới nhất" không mâu thuẫn):

- **(1) Nội dung do CEO soạn** — bối cảnh, yêu cầu, tiêu chí hoàn thành, tài liệu liên quan. Phần này **có phiên bản**: CEO sửa → tăng version.
- **(2) Trạng thái sống của task** — người thực hiện, % hoàn thành, cập nhật mới nhất. Phần này **không đóng gói** mà được hệ thống **ghép vào tại thời điểm truy vấn**.

Khi ai đó "dùng skill", họ nhận: nội dung phiên bản mới nhất **(1)** + trạng thái task ngay lúc đó **(2)**.

### 4.3 Vòng đời một skill

Tạo → **Cấp quyền** (ai được dùng) → **Sử dụng** (truy vấn) → **Cập nhật** (đổi nội dung → tăng phiên bản, **chỉ CEO**) → Thu hồi. Có nhật ký: ai đã dùng skill nào, khi nào, **ở phiên bản nội dung nào**.

---

## 5. Trải nghiệm Chat với AI — LÕI SẢN PHẨM

Đây là nơi bạn dành phần lớn thời gian, nên phải **nhanh, mượt, không chặn**. Mô hình tương tác lấy cảm hứng từ Claude Code.

### 5.1 Nguyên tắc: ô chat không bao giờ bị khóa

- Bạn **gõ và gửi yêu cầu bất cứ lúc nào**, kể cả khi AI đang trả lời yêu cầu trước đó.
- Không phải chờ AI trả lời xong mới nhập tiếp — luồng suy nghĩ của bạn không bị ngắt.

### 5.2 Hàng đợi yêu cầu (xử lý tuần tự)

- Gửi nhiều yêu cầu liên tiếp → nếu AI đang bận, yêu cầu mới **tự động vào hàng đợi**.
- AI **giải quyết lần lượt theo đúng thứ tự** gửi (cái nào gửi trước làm trước).
- **Hiển thị rõ hàng đợi**: cái nào đang xử lý, cái nào đang chờ (ví dụ: "đang xử lý 1/3").
- Trước khi tới lượt, bạn có thể **sửa / xóa / sắp xếp lại** yêu cầu trong hàng đợi.
- Có thể **chèn một yêu cầu ưu tiên** lên đầu hàng đợi.
- **Khi một yêu cầu lỗi/thất bại:** AI **không dừng cả hàng đợi** — nó **bỏ qua và làm tiếp** yêu cầu kế, đồng thời **báo rõ yêu cầu nào lỗi và lý do** (ví dụ: lỗi 429, mất kết nối DB) để bạn sửa rồi gửi lại.
- **Yêu cầu phụ thuộc vào yêu cầu đã lỗi:** kết quả lỗi được giữ trong ngữ cảnh; nếu yêu cầu kế tiếp phụ thuộc vào yêu cầu vừa thất bại (ví dụ "giao *task đó*" khi task chưa tạo được), AI **báo rõ và bỏ qua** yêu cầu đó — **không tự chọn đối tượng thay thế**. Các yêu cầu độc lập vẫn chạy bình thường.

### 5.3 Điều khiển khi đang chạy

- **Dừng ngay** yêu cầu đang chạy (giống nhấn Esc trong Claude Code).
- **Hủy** một yêu cầu bất kỳ đang chờ trong hàng đợi.
- **Dừng tất cả** để làm lại từ đầu.

### 5.4 Phản hồi theo thời gian thực (streaming)

- Câu trả lời **hiện dần từng phần** thay vì đợi xong mới hiện → cảm giác nhanh, mượt.
- Có chỉ báo trạng thái rõ ràng: "đang suy nghĩ", "đang tạo báo cáo", "đang gửi mail"...

### 5.5 Ngữ cảnh liên tục & nối tiếp

- AI **nhớ toàn bộ mạch hội thoại** + bối cảnh (project, task, người) khi xử lý từng yêu cầu.
- Yêu cầu sau **thấy được kết quả — kể cả thất bại — ** của yêu cầu trước trong hàng đợi. Ví dụ: gửi "tạo task X" rồi "giao task đó cho An" — AI hiểu "task đó" là X vừa tạo; nếu tạo X thất bại, AI biết điều đó và không giao nhầm task khác.
- Mỗi cuộc chat được **lưu lại và tìm lại được**.

### 5.6 Chat để làm MỌI việc — kiểm tra quyền tại chỗ (agentic)

- **Mọi thao tác đều làm qua chat**: tạo/sửa task, giao việc, phân quyền, cập nhật tiến độ, gen báo cáo & Excel, gửi mail, khóa tài khoản... **Không cần đi vào từng menu.**
- AI thực hiện **chỉ khi người ra lệnh có quyền**. Vượt quyền → AI **từ chối và báo rõ**. Ví dụ: nhân viên yêu cầu khóa tài khoản CEO hoặc xóa dữ liệu ngoài quyền → AI trả lời *"Bạn không có quyền làm điều này."*
- **Quyền được THỰC THI ở tầng backend (tool/API), không phải ở prompt:** danh tính người gọi lấy từ **phiên đăng nhập** (token), không bao giờ do AI tự khai. Mỗi tool (tạo task, khóa tài khoản, gửi mail...) tự kiểm tra vai trò + cây phân cấp trước khi chạy; không đủ quyền thì backend trả lỗi và AI chỉ truyền đạt lại. Nhờ vậy kể cả khi AI bị lừa qua prompt injection, hành động vượt quyền vẫn bị chặn.
- **Xác nhận hành động nhạy cảm cũng do backend cưỡng chế:** các tool nhạy cảm thiết kế 2 bước (đề xuất → người dùng xác nhận → thực thi), không phụ thuộc vào việc AI "tự giác" hỏi lại.
- Mỗi yêu cầu → AI làm → **báo kết quả** ngay trong khung chat.
- Với hành động nhạy cảm (khóa tài khoản, xóa dữ liệu, gửi mail), AI **xác nhận trước khi thực hiện**.

### 5.7 Mất mạng & tiếp tục công việc

- Khi **mất mạng hoặc đóng app**, hàng đợi **không tự động chạy tiếp** khi kết nối trở lại — tránh việc AI âm thầm thực hiện hàng loạt thao tác ngoài tầm kiểm soát của bạn.
- Nhưng các yêu cầu đang dang dở **được ghi nhớ**. Chỉ khi bạn **chủ động gõ "tiếp tục công việc"** (hoặc lệnh tương tự), AI mới **làm tiếp những việc bị gián đoạn** do mất mạng.

---

## 6. Chi tiết các nhóm chức năng

### 6.1 Đăng ký, Đăng nhập & Quản lý tài khoản/thiết bị

**Mô hình workspace (SaaS đa tenant, kiểu Slack)**
- Sản phẩm là **SaaS thương mại**: mỗi công ty là một **workspace** tách biệt hoàn toàn về dữ liệu (multi-tenant từ ngày đầu trong schema).
- **Người tạo workspace trở thành CEO gốc (root)** — tài khoản quản trị cao nhất, **không ai khóa/hạ quyền được**.
- **Vào workspace chỉ qua lời mời:** CEO gửi **link/mã mời** kèm sẵn **vai trò** và (với nhân viên) **manager trực thuộc** — trả lời luôn câu hỏi "nhân viên mới thuộc ai". **Không có đăng ký tự do** vào workspace.

**Đăng ký & Đăng nhập**
- Nhân viên/manager **tự tạo tài khoản** (self sign-up) nhưng chỉ vào được workspace **qua lời mời**.
- **CEO mời/tạo tài khoản** cho **bất kỳ vai trò nào** — nhân viên, manager, hoặc CEO khác. (Manager không mời/tạo tài khoản.)
- **CEO khác (không phải gốc):** đủ quyền CEO, nhưng **không khóa được CEO gốc**; chỉ **CEO gốc** khóa/mở được tài khoản mang vai trò CEO.
- Đăng nhập thành công → vào đúng không gian theo vai trò.

**Ghi nhận thiết bị (không giới hạn số lượng, nhưng luôn log)**
- Mỗi lần đăng nhập, hệ thống lưu **mã thiết bị (device UUID)** + **tên thiết bị** + thời điểm.
- Một tài khoản **đăng nhập trên bao nhiêu thiết bị cũng được** — không giới hạn — nhưng **mọi thiết bị & lần đăng nhập đều được ghi log** để CEO theo dõi.

**Khóa / Mở khóa TÀI KHOẢN (chỉ CEO)**
- CEO **khóa cả tài khoản** của một nhân viên.
- Tài khoản bị khóa: **bị đăng xuất khỏi mọi thiết bị** và **không đăng nhập lại được trên bất kỳ thiết bị nào**.
- **Chỉ CEO** có quyền khóa / mở khóa tài khoản.
- Khi người bị khóa cố đăng nhập → ngay tại màn hình đăng nhập, họ có thể **gửi yêu cầu mở khóa** → hệ thống **báo cho CEO** (kèm tên & mã thiết bị đang thử).
- CEO **mở khóa** → tài khoản dùng lại bình thường (hoặc CEO giữ nguyên khóa).
- Mọi lần khóa / mở khóa đều được ghi vào **nhật ký**.

### 6.2 Bộ nhớ bền vững + Thiết lập

- AI nhớ **bạn là ai, đang làm gì**, xuyên suốt các phiên (không phải khai lại mỗi lần).
- CEO **"dựng thế giới"**: tạo project, tạo task, thêm nhân sự & gán vai trò, khai báo skill — **tất cả qua chat**.
- Mọi thứ chỉnh sửa được và luôn phản ánh hiện trạng.
- *Đầu ra:* một lớp bối cảnh nền mà AI luôn dựa vào khi trả lời và tổng hợp.

### 6.3 Ghi âm & hỗ trợ giọng nói

- **Ghi âm nhanh (một chạm)** → lưu ngay lập tức.
- Chuyển giọng nói → văn bản, **tự nhận diện ngôn ngữ**: nói tiếng nào lưu tiếng đó (Việt ra Việt, Anh ra Anh), **không tự dịch**.
- Gắn tag / liên kết tới task, project, người.
- **Trích xuất bất cứ lúc nào:** nghe lại, đọc transcript, tìm theo từ khóa / task / ngày.
- Có thể **biến ghi âm thành task/cập nhật** bằng cách yêu cầu AI ngay trong chat.

### 6.4 Email theo vai trò

- **Email thật, gửi từ chính địa chỉ của người gửi** (CEO gửi thì đi từ mail của CEO): kết nối tài khoản Gmail/Outlook qua **OAuth (quyền send-as)** — không lưu mật khẩu mail của người dùng.
- Ba vai trò gửi/nhận mail, **tuân theo ma trận tương tác** ở mục 3 (nhân viên ⇎ nhân viên). Ma trận này **chỉ áp cho email & nhắn trực tiếp** — bình luận trong task chung (Mục 8) không bị giới hạn.
- Gửi mail là **hành động nhạy cảm** → luôn qua bước xác nhận trước khi gửi (Mục 5.6).
- AI **hỗ trợ soạn nhanh**: tóm tắt tiến độ, nhắc việc, yêu cầu cập nhật.
- Mail **gắn ngữ cảnh**: có thể tham chiếu trực tiếp tới một task/project cụ thể.

### 6.5 Tổng hợp tiến độ + Báo cáo / Excel

- Manager & nhân viên cập nhật tiến độ → AI **gom về** theo project / người / kỳ.
- CEO **yêu cầu báo cáo** (theo project, theo người, theo khoảng thời gian) — **qua chat**.
- *Đầu ra:* tóm tắt trên màn hình **+ file Excel tải về** (danh sách task, trạng thái, % hoàn thành, người phụ trách, cập nhật mới nhất, mốc thời gian).
- Có **mẫu mặc định** sẵn, và CEO **tùy biến cột/nội dung ngay trong chat** (ví dụ: "thêm cột deadline", "chỉ lấy task chưa xong").
- *(Nâng cao)* Báo cáo **định kỳ tự động** (ví dụ: bản tổng hợp cuối mỗi tuần).

### 6.6 Push notification

- **Bắn thông báo cho MỌI cập nhật tiến độ** tới người liên quan (không lọc).
- Cùng các sự kiện khác: task mới được giao, sắp tới hạn, có mail/được nhắc tên, báo cáo đã sẵn sàng, và **yêu cầu mở khóa tài khoản** (bắn cho CEO).
- **Gửi đúng người liên quan:** người phụ trách task, manager của họ, CEO, người cùng cộng tác.
- **Kênh:** trong app / email / mobile. (Người dùng có thể tắt bớt loại thông báo nếu quá nhiều.)

---

## 7. Các luồng công việc chính (User journeys)

**Luồng 1 — CEO khởi tạo**
Nhắn cho AI: dựng project → tạo task A/B/C và mô tả chi tiết → đóng gói thành skill → phân người thực hiện + cấp quyền dùng skill. Tất cả bằng chat.

**Luồng 2 — Nhân viên thực thi**
Đăng nhập (thiết bị được ghi log) → nhận thông báo được giao → **dùng skill lấy thông tin chuẩn của task** → làm việc → cập nhật tiến độ → hệ thống **bắn thông báo** lên manager & CEO.

**Luồng 3 — CEO nắm tình hình & báo cáo**
Nhắn AI xem tổng hợp → thấy % từng task → yêu cầu báo cáo kỳ này (tùy biến cột nếu cần) → nhận **tóm tắt + file Excel**.

**Luồng 4 — Ghi âm ý tưởng**
CEO bấm ghi âm nhanh khi họp / di chuyển → AI chuyển văn bản (đúng ngôn ngữ) & gắn vào project → sau đó tìm lại hoặc yêu cầu AI biến thành task.

**Luồng 5 — Khóa & mở khóa tài khoản**
CEO nhắn AI **khóa tài khoản** của một nhân viên → tài khoản **bị đăng xuất khỏi mọi thiết bị, không vào lại được** → người đó **gửi yêu cầu mở khóa** từ màn hình đăng nhập → CEO **nhận thông báo** → CEO mở khóa hoặc giữ khóa.

**Luồng 6 — Gửi nhiều yêu cầu cùng lúc (điểm nhấn trải nghiệm)**
CEO gõ liên tiếp: "tạo task Q4 report" → "giao cho An" → "gen báo cáo tuần này ra Excel" mà không chờ. AI **xếp 3 yêu cầu vào hàng đợi**, xử lý lần lượt, hiện "đang xử lý 1/3 → 2/3 → 3/3", báo kết quả từng cái. Nếu yêu cầu 2 lỗi → AI **bỏ qua, làm tiếp yêu cầu 3**, và báo lại yêu cầu 2 hỏng ở đâu để CEO sửa.

**Luồng 7 — Nhân viên vượt quyền**
Nhân viên nhắn AI "khóa tài khoản CEO" → AI kiểm tra quyền → **từ chối** và trả lời *"Bạn không có quyền làm điều này."*

---

## 8. Chức năng nền tảng nên bổ sung (những khoảng trống nên lấp)

Các chức năng này không nằm trong các nhóm ban đầu nhưng gần như bắt buộc để hệ thống chạy mượt:

- **Trạng thái & vòng đời task**: Chưa bắt đầu / Đang làm / Bị chặn / Hoàn thành — kèm mức ưu tiên & deadline.
- **Nhật ký thay đổi**: ai cập nhật gì, khi nào; ai đăng nhập từ thiết bị nào; lịch sử khóa/mở khóa tài khoản — phục vụ minh bạch, bảo mật & báo cáo.
- **Thảo luận / bình luận trong task** + đính kèm tài liệu.
- **Bảng tổng quan (dashboard) cho CEO**: sức khỏe project, task trễ hạn, tải công việc theo từng người, thiết bị đang hoạt động.
- **Tìm kiếm xuyên suốt**: tìm trong task, ghi âm, người, skill, lịch sử chat.
- **Phân quyền chi tiết trên skill**: ai được xem / sửa / dùng.
- **Xử lý khi nhân sự nghỉ hoặc đổi vai trò**: bàn giao task + khóa tài khoản.

---

## 9. Các quyết định đã chốt (Design decisions)

Danh sách chốt để đội phát triển bám theo:

- **Nền tảng:** app di động **đa nền tảng (iOS + Android)**, vận hành dạng **SaaS đa tenant** — mỗi công ty một **workspace** kiểu Slack, vào bằng **lời mời** (kèm vai trò & manager trực thuộc), không đăng ký tự do.
- **Cách vận hành:** làm **mọi việc qua chat**, không đi vào từng menu. AI thực thi nếu người ra lệnh có quyền; nếu không, từ chối và báo rõ.
- **Thực thi quyền:** kiểm tra ở **tầng backend/tool** dựa trên phiên đăng nhập — không dựa vào prompt; hành động nhạy cảm dùng tool 2 bước (đề xuất → xác nhận).
- **Manager ↔ Manager:** được tương tác tự do.
- **Cây phân cấp:** có — mỗi nhân viên thuộc một manager (quyết định phạm vi xem & nhận thông báo).
- **Sửa nội dung skill:** chỉ CEO. Skill có **cấu trúc 2 lớp**: nội dung CEO soạn (có phiên bản) + trạng thái task sống ghép lúc truy vấn.
- **Khóa tài khoản:** khóa **cả tài khoản** (không cho đăng nhập trên mọi thiết bị); **chỉ CEO** được khóa/mở.
- **Số thiết bị:** không giới hạn, nhưng **log đầy đủ**.
- **Thông báo:** bắn **mọi** cập nhật tiến độ.
- **Ghi âm:** speech-to-text **tự nhận diện ngôn ngữ**, nói tiếng nào lưu tiếng đó, không tự dịch.
- **Hàng đợi khi lỗi:** bỏ qua, làm tiếp cái sau, báo lỗi để sửa. Yêu cầu **phụ thuộc** vào cái đã lỗi → báo & bỏ qua, không tự chọn đối tượng thay thế.
- **Email:** gửi **email thật từ địa chỉ của chính người gửi** (OAuth send-as), luôn xác nhận trước khi gửi. Ma trận tương tác chỉ áp cho email & nhắn trực tiếp; bình luận trong task không bị giới hạn.
- **Mất mạng:** không tự chạy tiếp; chỉ tiếp tục khi gõ "tiếp tục công việc".
- **Báo cáo Excel:** có mẫu mặc định, tùy biến cột ngay trong chat.
- **Tạo tài khoản:** vào workspace **chỉ qua lời mời**; **CEO** mời/tạo được **mọi vai trò** (nhân viên/manager/CEO); người tạo workspace là **CEO gốc** — không ai khóa/hạ quyền được, và chỉ CEO gốc khóa/mở được tài khoản vai trò CEO; **manager không** tạo tài khoản.

---

## 10. Gợi ý phân giai đoạn (prototype-first)

Ưu tiên dựng **vòng lặp lõi CEO ↔ nhân viên** trước, tính năng nặng đẩy về sau. Sản phẩm là **app mobile đa nền tảng ngay từ đầu**.

- **Giai đoạn 1 — MVP (chứng minh giá trị):** Đăng ký / đăng nhập theo vai trò + log thiết bị (không giới hạn); **khung chat + hàng đợi tuần tự + streaming + dừng/hủy + bỏ qua khi lỗi + kiểm tra quyền tại lệnh** (lõi sản phẩm); bộ nhớ + thiết lập project/task/người; skill gói tri thức task; cập nhật tiến độ; tổng hợp + xuất Excel cơ bản.
- **Giai đoạn 2:** Ma trận tương tác + cây phân cấp đầy đủ; **khóa/mở khóa tài khoản (chỉ CEO)** + thông báo & yêu cầu mở khóa; email theo vai trò; push notification (bắn mọi cập nhật); "tiếp tục công việc" sau khi mất mạng.
- **Giai đoạn 3:** Ghi âm/giọng nói (tự nhận diện ngôn ngữ) + tìm kiếm; báo cáo định kỳ tự động + tùy biến cột; dashboard tổng quan; sắp xếp lại / chèn ưu tiên trong hàng đợi.
- **Giai đoạn 4 — nâng cao:** AI bóc việc từ ghi âm; gợi ý phân task theo hồ sơ năng lực; nhật ký & phân quyền chi tiết trên skill.
