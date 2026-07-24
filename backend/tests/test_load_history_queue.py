import uuid
from datetime import datetime, timedelta, timezone

from app.agent.loop import MAX_HISTORY_MESSAGES, _load_history
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole


async def _mk_conv(db):
    ws, user = uuid.uuid4(), uuid.uuid4()
    conv = Conversation(workspace_id=ws, user_id=user)
    db.add(conv)
    await db.flush()
    return conv


async def _mk_req(db, conv, content, pos, status=ChatRequestStatus.queued):
    req = ChatRequest(workspace_id=conv.workspace_id, conversation_id=conv.id,
                      user_id=conv.user_id, content=content, queue_position=pos,
                      status=status)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "text", "text": content}]))
    return req


async def test_tin_queued_khac_khong_lot_vao_history(db_session):
    conv = await _mk_conv(db_session)
    req1 = await _mk_req(db_session, conv, "tin 1", 1.0)
    await _mk_req(db_session, conv, "tin 2 (cho xu ly)", 2.0)
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req1.id)
    texts = [b["text"] for m in history for b in m["content"] if b.get("type") == "text"]
    assert "tin 1" in texts
    assert all("tin 2" not in t for t in texts)


async def test_tin_da_xong_van_trong_history(db_session):
    conv = await _mk_conv(db_session)
    await _mk_req(db_session, conv, "tin cu da xong", 1.0, status=ChatRequestStatus.done)
    req2 = await _mk_req(db_session, conv, "tin moi", 2.0)
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req2.id)
    texts = [b["text"] for m in history for b in m["content"] if b.get("type") == "text"]
    assert "tin cu da xong" in texts and "tin moi" in texts


async def test_history_bi_cat_va_bat_dau_bang_user_text(db_session):
    conv = await _mk_conv(db_session)
    req = None
    for i in range(MAX_HISTORY_MESSAGES + 20):
        req = await _mk_req(db_session, conv, f"tin {i}", float(i),
                            status=ChatRequestStatus.done)
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               chat_request_id=req.id, role=MessageRole.assistant,
                               content=[{"type": "text", "text": f"tra loi {i}"}]))
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req.id)
    assert len(history) <= MAX_HISTORY_MESSAGES
    first = history[0]
    assert first["role"] == "user"
    assert first["content"][0]["type"] == "text"


async def test_history_bi_cat_truot_qua_tool_result_mo_coi(db_session):
    """Cua so 80-message co the roi dung vao giua 1 cap tool_use/tool_result — phai
    truot toi user-text tiep theo, KHONG duoc mo dau bang tool_result mo coi (Anthropic
    API tu choi message nhu vay)."""
    conv = await _mk_conv(db_session)
    ws, user = conv.workspace_id, conv.user_id
    # created_at ep tuong minh, tang dan tung ms — nhieu insert lien tiep trong 1 flush
    # co the trung created_at (do phan giai dong ho), luc do thu tu roi vao id.asc()
    # (UUID ngau nhien) chu khong con theo thu tu tao — test can thu tu XAC DINH.
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Chu ky 3 message lap lai: user text -> assistant tool_use -> user tool_result.
    # Tong 91 message: cua so 80 cuoi bat dau dung tai vi tri tool_result (index 11,
    # 11 % 3 == 2), user-text an toan gan nhat la message ke tiep (index 12).
    for i in range(91):
        step = i % 3
        if step == 0:
            content, role = [{"type": "text", "text": f"tin {i}"}], MessageRole.user
        elif step == 1:
            content = [{"type": "tool_use", "id": f"tu{i}", "name": "list_tasks", "input": {}}]
            role = MessageRole.assistant
        else:
            content = [{"type": "tool_result", "tool_use_id": f"tu{i - 1}", "content": "[]"}]
            role = MessageRole.user
        db_session.add(Message(workspace_id=ws, conversation_id=conv.id, chat_request_id=None,
                               role=role, content=content, created_at=base + timedelta(milliseconds=i)))
    marker_req = ChatRequest(workspace_id=ws, conversation_id=conv.id, user_id=user,
                             content="marker", queue_position=9999.0,
                             status=ChatRequestStatus.done)
    db_session.add(marker_req)
    await db_session.commit()

    history = await _load_history(db_session, conv.id, marker_req.id)
    assert len(history) == 79  # 80 - 1 (message tool_result index 11 bi truot qua)
    first = history[0]
    assert first["role"] == "user"
    assert first["content"][0]["type"] == "text"
    assert first["content"][0]["text"] == "tin 12"


async def test_ack_message_khong_lot_vao_history_dung_request_dang_ack(db_session):
    """Phat hien qua verify tay Phase 4 (duong sau §8.2): run_deep_ack_turn ghi 1
    Message role=assistant, is_ack=True GAN VOI CUNG chat_request_id, TRUOC khi
    run_deep_analysis goi lai run_agent_loop cho DUNG request do. Neu _load_history
    khong loai no, lich su ket thuc bang message assistant nay, Anthropic tu choi
    thang ("model does not support assistant message prefill... must end with a
    user message")."""
    conv = await _mk_conv(db_session)
    req = await _mk_req(db_session, conv, "phan tich rui ro du an", 1.0,
                        status=ChatRequestStatus.deep_running)
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           chat_request_id=req.id, role=MessageRole.assistant,
                           content=[{"type": "text", "text": "Dang phan tich..."}],
                           is_ack=True))
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req.id)
    assert history[-1]["role"] == "user"
    assert history[-1]["content"][0]["text"] == "phan tich rui ro du an"


async def test_ack_message_bi_loai_ke_ca_khi_nam_giua_lich_su(db_session):
    """Lan verify dau tien chi cat message assistant O CUOI (trailing) — khong du:
    tu vong lap 2 tro di, tool_use dau tien cua chinh job duoc ghi NGAY SAU ack,
    dat no vao GIUA (user goc -> ack -> tool_use), pha luat user/assistant xen ke
    bat buoc cua Anthropic ("unexpected tool_use_id... must have a corresponding
    tool_use block in the previous message"). is_ack phai loai no BAT KE VI TRI."""
    conv = await _mk_conv(db_session)
    req = ChatRequest(workspace_id=conv.workspace_id, conversation_id=conv.id,
                      user_id=conv.user_id, content="phan tich rui ro du an",
                      queue_position=1.0, status=ChatRequestStatus.deep_running)
    db_session.add(req)
    await db_session.flush()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           chat_request_id=req.id, role=MessageRole.user,
                           content=[{"type": "text", "text": "phan tich rui ro du an"}],
                           created_at=base + timedelta(milliseconds=0)))
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           chat_request_id=req.id, role=MessageRole.assistant,
                           content=[{"type": "text", "text": "Dang phan tich..."}],
                           is_ack=True, created_at=base + timedelta(milliseconds=1)))
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           chat_request_id=req.id, role=MessageRole.assistant,
                           content=[{"type": "tool_use", "id": "t1",
                                    "name": "get_project_health", "input": {}}],
                           created_at=base + timedelta(milliseconds=2)))
    db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                           chat_request_id=req.id, role=MessageRole.user,
                           content=[{"type": "tool_result", "tool_use_id": "t1",
                                    "content": "{}"}],
                           created_at=base + timedelta(milliseconds=3)))
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req.id)
    roles = [m["role"] for m in history]
    assert roles == ["user", "assistant", "user"]  # ack (assistant) da bi loai het


async def test_history_khong_co_diem_bat_dau_an_toan_tra_ve_rong(db_session):
    """Neu ca cua so 80 message khong co message nao role=user + content text dau
    tien (chi co the xay ra ve sau neu MAX_ITERATIONS tang), tra ve [] thay vi doan
    bua msgs[-1:] — message cuoi cung chua chac an toan."""
    conv = await _mk_conv(db_session)
    for i in range(MAX_HISTORY_MESSAGES + 5):
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               chat_request_id=None, role=MessageRole.assistant,
                               content=[{"type": "text", "text": f"tra loi {i}"}]))
    # ChatRequest "trần" — chỉ dùng làm current_request_id, không tạo Message user-text
    # đi kèm (khác _mk_req) để cửa sổ 80 message thật sự không có điểm an toàn nào.
    marker_req = ChatRequest(workspace_id=conv.workspace_id, conversation_id=conv.id,
                             user_id=conv.user_id, content="marker",
                             queue_position=9999.0, status=ChatRequestStatus.done)
    db_session.add(marker_req)
    await db_session.commit()

    history = await _load_history(db_session, conv.id, marker_req.id)
    assert history == []


async def test_load_history_since_bo_message_cu(db_session):
    from sqlalchemy import select
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conv = await _mk_conv(db_session)
    old = await _mk_req(db_session, conv, "tin cu da nen", 1.0, status=ChatRequestStatus.done)
    new = await _mk_req(db_session, conv, "tin moi verbatim", 2.0, status=ChatRequestStatus.done)
    # created_at tuong minh (base / base+1p) — tranh hai message trung microsecond
    # khien since `>` loai ca hai (test tung flaky).
    for req_id, at in ((old.id, base), (new.id, base + timedelta(minutes=1))):
        msg = (await db_session.execute(
            select(Message).where(Message.chat_request_id == req_id))).scalar_one()
        msg.created_at = at
    await db_session.commit()

    history = await _load_history(db_session, conv.id, new.id, since=base)
    texts = [b["text"] for m in history for b in m["content"] if b.get("type") == "text"]
    assert "tin cu da nen" not in texts
    assert "tin moi verbatim" in texts
