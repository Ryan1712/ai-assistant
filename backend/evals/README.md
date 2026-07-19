# Eval harness (Phase 0 — spec AI upgrade §4.2)

Chấm HÀNH VI agent với model thật — ngoài pytest CI (pytest chỉ test logic với
FakeLLMClient; eval test "model có chọn đúng tool không").

## Chạy

    # 4 thứ phải đang chạy: postgres, redis, API, worker + key LLM thật trong .env
    docker compose up -d postgres redis
    uvicorn app.main:app            # terminal 1
    arq app.agent.worker.WorkerSettings   # terminal 2
    python -m evals.run_evals       # terminal 3 (trong backend/, venv bật)

Tùy chọn: `--base-url`, `--phase N` (chạy cả scenario phase sau), `--only <id>`.
Mỗi lần chạy tạo workspace eval mới (email @eval.local) — không đụng data thật.
Scenario dừng ở awaiting_confirmation sẽ bị runner TỪ CHỐI sau khi chấm.

## Quy ước (bắt buộc — spec §4.2)

1. Chạy eval TRƯỚC MỖI LẦN đổi system prompt / model / toolset; kết quả baseline
   ghi vào `evals/BASELINE.md`.
2. Mỗi bug hành vi fix xong → thêm 1 scenario tái hiện bug đó.
3. Scenario của feature chưa làm → đặt `phase: N` để runner skip tới khi tới phase.

## Format scenario (`scenarios/*.yaml`)

    - id: ten-ngan-khong-dau
      actor: ceo | employee        # employee = Duy Phạm trong seed
      user_text: "câu tiếng Việt thật"
      expected_tools: [a, b]       # subsequence đúng thứ tự, cho phép chen tool khác
      forbidden_tools: [c]         # không được gọi (kể cả pending confirm)
      expected_status: done | awaiting_confirmation
      expected_pending_tool: lock_user   # tool đang chờ confirm (nếu có)
      phase: 0                     # mặc định 0
      notes: "vì sao scenario tồn tại"

Grader: `evals/grader.py` (unit test: `tests/test_eval_grader.py`).
