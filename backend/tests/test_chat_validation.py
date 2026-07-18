import pytest
from pydantic import ValidationError

from app.schemas import ChatRequestEditIn, MessageSendIn


@pytest.mark.parametrize("cls", [MessageSendIn, ChatRequestEditIn])
def test_content_rong_bi_tu_choi(cls):
    with pytest.raises(ValidationError):
        cls(content="")
    with pytest.raises(ValidationError):
        cls(content="   \n  ")


@pytest.mark.parametrize("cls", [MessageSendIn, ChatRequestEditIn])
def test_content_bi_strip_va_gioi_han(cls):
    assert cls(content="  hello  ").content == "hello"
    with pytest.raises(ValidationError):
        cls(content="x" * 8001)
