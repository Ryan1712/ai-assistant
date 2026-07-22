"""So khớp mờ (fuzzy) thuần Python cho resolve_person/resolve_task (Phase 2 §6.3).

Không dùng Postgres pg_trgm: toàn bộ test suite chạy trên sqlite (xem
tests/conftest.py), pg_trgm chỉ Postgres mới có — sẽ buộc tách track test riêng
hoặc mock hành vi đang test. Ở quy mô workspace thật (~15-50 người/task), quét
trong RAM nhanh cỡ micro-giây, không cần index. Công thức dùng đúng Jaccard trên
tập trigram mà pg_trgm.similarity() dùng (ngưỡng mặc định 0.3) — sau này đổi sang
pg_trgm chỉ là thay hàm gọi, không phải viết lại logic.
"""
from app.services.continuity import normalize_vn

MATCH_THRESHOLD = 0.3
_TIER_A_CUTOFF = 0.9


def _trigrams(text: str) -> set[str]:
    padded = f"  {text} "  # đệm để trigram bắt được biên từ, khớp quy ước pg_trgm
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def trigram_similarity(a: str, b: str) -> float:
    """Jaccard trên tập trigram ký tự — 2 chuỗi ĐÃ normalize (không tự normalize lại)."""
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def match_score(query: str, target: str) -> float:
    """1.0 khớp nguyên văn (sau normalize) > 0.95 khớp TRỌN 1 TỪ (vd 'Duy' trong
    'Duy Phạm' — tên riêng VN hay gọi 1 từ) > trigram_similarity() (chịu lỗi
    chính tả/thiếu dấu)."""
    nq, nt = normalize_vn(query), normalize_vn(target)
    if nq == nt:
        return 1.0
    if nq in nt.split():
        return 0.95
    return trigram_similarity(nq, nt)


def pick_matches(scored: list[tuple], tier_cutoff: float = _TIER_A_CUTOFF,
                 threshold: float = MATCH_THRESHOLD) -> list[tuple]:
    """Nếu có candidate(s) ở tier chính xác/trọn-từ (score>=tier_cutoff), CHỈ những
    candidate đó cạnh tranh (bỏ qua nhiễu trigram yếu hơn dù có thể cũng qua
    threshold). Không thì rơi về pool trigram >= threshold. Trả [] / [1 phần tử] /
    [>=2 phần tử] — caller quyết not_found/found/ambiguous từ độ dài kết quả."""
    tier_a = [(item, s) for item, s in scored if s >= tier_cutoff]
    if tier_a:
        return sorted(tier_a, key=lambda pair: pair[1], reverse=True)
    tier_b = [(item, s) for item, s in scored if s >= threshold]
    return sorted(tier_b, key=lambda pair: pair[1], reverse=True)
