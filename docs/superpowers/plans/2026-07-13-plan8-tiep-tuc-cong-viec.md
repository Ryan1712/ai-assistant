# Plan 8 â€” "Tiáº¿p tá»¥c cÃ´ng viá»‡c" (funtional-plan 5.7)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Checkbox (`- [ ]`) Ä‘á»ƒ tracking.

**Goal:** Máº¥t máº¡ng / Ä‘Ã³ng app â†’ hÃ ng Ä‘á»£i chat **khÃ´ng tá»± cháº¡y tiáº¿p**; viá»‡c dang dá»Ÿ Ä‘Æ°á»£c ghi nhá»›; chá»‰ khi user gÃµ **"tiáº¿p tá»¥c cÃ´ng viá»‡c"** thÃ¬ AI má»›i lÃ m ná»‘t (spec 5.7 + má»¥c 9).

**Architecture:** WS disconnect (socket cuá»‘i cÃ¹ng cá»§a conversation) â†’ set cá» `conversations.queue_held`. Worker kiá»ƒm tra cá» má»—i vÃ²ng láº·p (nhÆ° Ä‘Ã£ kiá»ƒm tra `awaiting_confirmation`) â†’ dá»«ng xá»­ lÃ½ khi held. Tin nháº¯n má»›i match cá»¥m "tiáº¿p tá»¥c cÃ´ng viá»‡c" (khÃ´ng phÃ¢n biá»‡t hoa thÆ°á»ng/dáº¥u/khoáº£ng tráº¯ng thá»«a) â†’ clear cá»; request cá»§a chÃ­nh tin Ä‘Ã³ váº«n vÃ o queue nhÆ° thÆ°á»ng nÃªn AI tráº£ lá»i nÃ³ SAU KHI lÃ m ná»‘t viá»‡c cÅ© â€” Ä‘Ãºng ngá»¯ nghÄ©a "lÃ m ná»‘t". Presence Ä‘áº¿m in-process (single API instance â€” Ä‘á»§ cho hiá»‡n táº¡i; multi-instance cáº§n chuyá»ƒn redis, ghi chÃº trong code).

**Tech Stack:** BE nhÆ° cÅ© (khÃ´ng thÃªm dependency). FE: banner + nÃºt trong mÃ n chat.

## Global Constraints (CLAUDE.md)
- workspace_id má»i báº£ng; quyá»n á»Ÿ service layer; actor tá»« JWT; TDD, má»—i task 1 commit; export openapi khi Ä‘á»•i contract.

## Quyáº¿t Ä‘á»‹nh thiáº¿t káº¿
- **Ngá»¯ nghÄ©a hold:** hold = TOÃ€N Bá»˜ queue cá»§a conversation dá»«ng (ká»ƒ cáº£ tin má»›i gá»­i khi Ä‘ang held â€” vÃ¬ queue tuáº§n tá»±, khÃ´ng thá»ƒ cháº¡y tin má»›i trÆ°á»›c tin cÅ© mÃ  khÃ´ng phÃ¡ thá»© tá»± lá»‹ch sá»­). FE hiá»ƒn thá»‹ banner giáº£i thÃ­ch. Request Ä‘ang `running` lÃºc disconnect: cháº¡y ná»‘t request Ä‘Ã³ (worker chá»‰ cháº·n TRÆ¯á»šC khi láº¥y item káº¿ tiáº¿p).
- **Chá»‰ socket cuá»‘i cÃ¹ng disconnect má»›i hold** (user má»Ÿ 2 thiáº¿t bá»‹: táº¯t 1 cÃ¡i khÃ´ng dá»«ng queue) â€” Ä‘áº¿m presence per-conversation.
- **Reconnect KHÃ”NG tá»± clear hold** â€” spec: chá»‰ cá»¥m tá»« "tiáº¿p tá»¥c cÃ´ng viá»‡c" má»›i resume.
- **Chá»‰ hold khi cÃ³ viá»‡c dang dá»Ÿ** (queued/running); queue rá»—ng thÃ¬ disconnect khÃ´ng set cá».
- **Match cá»¥m tá»«:** casefold + strip + gá»™p khoáº£ng tráº¯ng + bá» dáº¥u (NFD, Ä‘â†’d) rá»“i so `"tiep tuc cong viec"`. Match khi KHÃ”NG held â†’ tin nháº¯n thÆ°á»ng, vÃ´ háº¡i.
- **KhÃ´ng thÃªm endpoint má»›i** â€” resume Ä‘i qua chÃ­nh POST messages (YAGNI); nÃºt FE chá»‰ lÃ  shortcut gá»­i Ä‘Ãºng cá»¥m tá»«.

### Task 1: Service presence + continuity (TDD)
- [x] `app/services/presence.py`: Ä‘áº¿m socket per-conversation, in-process (`dict[uuid.UUID, int]` module-level). API: `connect(conversation_id) -> int` (count sau khi tÄƒng), `disconnect(conversation_id) -> int` (count sau khi giáº£m, floor 0, xÃ³a key khi 0), `reset()` (cho test). Docstring ghi rÃµ giá»›i háº¡n single-instance.
- [x] `app/services/continuity.py`:
  ```python
  RESUME_PHRASE = "tiep tuc cong viec"

  def _normalize(text: str) -> str:
      # casefold, Ä‘â†’d, bá» dáº¥u (NFD bá» combining), gá»™p khoáº£ng tráº¯ng
      text = text.casefold().replace("Ä‘", "d")
      text = unicodedata.normalize("NFD", text)
      text = "".join(c for c in text if not unicodedata.combining(c))
      return " ".join(text.split())

  def is_resume_phrase(text: str) -> bool:
      return _normalize(text) == RESUME_PHRASE

  async def hold_queue_if_pending(db, conversation_id) -> bool:
      # True náº¿u cÃ³ request queued/running â†’ set conversations.queue_held=True + commit
  ```
- [x] Test `tests/test_continuity.py`: phrase â€” `"tiáº¿p tá»¥c cÃ´ng viá»‡c"`, `"  Tiáº¿p Tá»¥c  CÃ´ng Viá»‡c "`, `"TIEP TUC CONG VIEC"` â†’ True; `"tiáº¿p tá»¥c"`, `"lÃ m ná»‘t cÃ´ng viá»‡c"` â†’ False. Presence: 2Ã—connect â†’ 2; disconnect â†’ 1; disconnect â†’ 0; disconnect láº§n ná»¯a váº«n 0. hold: conv cÃ³ request queued â†’ True + cá» set; conv rá»—ng â†’ False + cá» khÃ´ng set.
- [x] Commit `feat(be): presence + continuity service (resume phrase, hold queue)`.

### Task 2: Model + worker gate (TDD)
- [x] `models.py`: `Conversation.queue_held: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")`.
- [x] `worker.py::process_conversation`: trong vÃ²ng while, sau check `awaiting_confirmation`, thÃªm:
  ```python
  conv = await db.get(Conversation, conversation_id)
  if conv is not None and conv.queue_held:
      return  # 5.7: máº¥t máº¡ng â†’ khÃ´ng tá»± cháº¡y tiáº¿p, chá» "tiáº¿p tá»¥c cÃ´ng viá»‡c"
  ```
- [x] Test thÃªm vÃ o `tests/test_worker.py`: conversation `queue_held=True` cÃ³ 1 request queued â†’ `process_conversation` return, request váº«n `queued`, `llm.calls == 0`. Mirror fixture style test hiá»‡n cÃ³ (Workspace/User/Conversation/ChatRequest + FakeLLMClient + FakeEventPublisher).
- [x] Commit `feat(be): conversations.queue_held + worker dung khi held`.

### Task 3: Wire WS disconnect + resume phrase + contract (TDD)
- [x] `app/api/ws.py::conversation_ws`: sau `accept()` â†’ `presence.connect(conversation_id)`; trong `finally`: `if presence.disconnect(conversation_id) == 0: await continuity.hold_queue_if_pending(db, conversation_id)`.
- [x] `app/api/chat.py::send_message`: sau khi táº¡o req/Message, trÆ°á»›c commit:
  ```python
  if conv.queue_held and continuity.is_resume_phrase(body.content):
      conv.queue_held = False
  ```
  (enqueue_conversation Ä‘Ã£ gá»i sáºµn sau commit â€” khÃ´ng Ä‘á»•i.)
- [x] `schemas.py::ConversationOut`: thÃªm `queue_held: bool = False`.
- [x] Test (thÃªm `tests/test_continuity_api.py`): (1) conv held + POST message "tiáº¿p tá»¥c cÃ´ng viá»‡c" â†’ GET /conversations tháº¥y `queue_held == False` vÃ  request má»›i náº±m CUá»I queue; (2) conv held + POST message thÆ°á»ng â†’ váº«n held; (3) conv khÃ´ng held + POST "tiáº¿p tá»¥c cÃ´ng viá»‡c" â†’ váº«n khÃ´ng held, request táº¡o bÃ¬nh thÆ°á»ng; (4) GET /conversations tráº£ field `queue_held`.
- [x] Commit `feat(be): ws disconnect hold queue + resume bang cum "tiep tuc cong viec"`.

### Task 4: Migration + openapi
- [x] Migration tay: `conversations.queue_held` Boolean NOT NULL server_default false. Full pytest. `python scripts/export_openapi.py`. Commit `chore(be): plan8 migration + openapi refresh`.

### Task 5: FE banner + nÃºt tiáº¿p tá»¥c
- [x] `src/api/chat.ts`: `Conversation` thÃªm `queue_held: boolean`.
- [x] `app/(main)/chat.tsx`: state `held` (khá»Ÿi táº¡o tá»« conversation lÃºc mount). Khi `held`:
  banner (mÃ u `warningBg`/`warningText` theo theme) trÃªn khá»‘i queue: "â¸ Viá»‡c dang dá»Ÿ Ä‘ang chá» â€” gÃµ 'tiáº¿p tá»¥c cÃ´ng viá»‡c' Ä‘á»ƒ AI lÃ m ná»‘t" + nÃºt "â–¶ Tiáº¿p tá»¥c" (gá»­i Ä‘Ãºng cá»¥m `tiáº¿p tá»¥c cÃ´ng viá»‡c` qua sendMessage, set `held=false` optimistic). Gá»­i tay tin nháº¯n match cá»¥m (so sÃ¡nh phÃ­a FE: lowercase+trim) cÅ©ng set `held=false`.
- [x] Typecheck + expo export. Commit `feat(fe): banner "tiep tuc cong viec" + nut resume queue`.

## Ghi chÃº
- Presence in-process: náº¿u sau nÃ y API cháº¡y nhiá»u instance â†’ chuyá»ƒn counter sang redis (INCR/DECR + TTL), interface giá»¯ nguyÃªn.
- FE khÃ´ng thá»ƒ biáº¿t held Ä‘á»•i real-time khi chÃ­nh nÃ³ offline (hiá»ƒn nhiÃªn) â€” fetch láº¡i `GET /conversations` lÃºc mount lÃ  Ä‘á»§.
