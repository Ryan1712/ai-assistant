import pytest

from app.services import email_service


@pytest.mark.asyncio
async def test_smtp_client_builds_message_and_sends(monkeypatch):
    captured = {}

    async def fake_send(msg, **kwargs):
        captured["msg"] = msg
        captured["kwargs"] = kwargs

    import aiosmtplib
    monkeypatch.setattr(aiosmtplib, "send", fake_send)

    await email_service.SmtpEmailClient().send(
        from_email="boss@a.vn", to_email="user@a.vn",
        subject="Mã đặt lại", body="Ma cua ban la 123456",
    )

    msg = captured["msg"]
    assert msg["To"] == "user@a.vn"
    assert msg["Subject"] == "Mã đặt lại"
    assert "123456" in msg.get_content()
    # settings mặc định smtp_from/smtp_user rỗng → người gửi = from_email
    assert msg["From"] == "boss@a.vn"
    assert captured["kwargs"]["port"] == 587


def test_get_email_client_returns_mock_when_email_mock_true():
    # email_mock=True mặc định → vẫn dùng mock (không gửi thật)
    assert email_service.get_email_client() is email_service.mock_email_client


def test_smtp_password_alias_accepts_smtp_pass_env():
    from app.config import Settings
    settings = Settings(_env_file=None, SMTP_PASS="xyz")
    assert settings.smtp_password == "xyz"


def test_smtp_password_alias_still_accepts_smtp_password_env():
    from app.config import Settings
    settings = Settings(_env_file=None, SMTP_PASSWORD="abc")
    assert settings.smtp_password == "abc"


@pytest.mark.asyncio
async def test_smtp_client_uses_use_tls_when_secure(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "smtp_secure", True)

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["kwargs"] = kwargs

    import aiosmtplib
    monkeypatch.setattr(aiosmtplib, "send", fake_send)

    await email_service.SmtpEmailClient().send(
        from_email="boss@a.vn", to_email="user@a.vn",
        subject="S", body="B",
    )
    assert captured["kwargs"]["use_tls"] is True
    assert captured["kwargs"]["start_tls"] is False


@pytest.mark.asyncio
async def test_smtp_client_uses_start_tls_when_not_secure(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "smtp_secure", False)
    monkeypatch.setattr(get_settings(), "smtp_starttls", True)

    captured = {}

    async def fake_send(msg, **kwargs):
        captured["kwargs"] = kwargs

    import aiosmtplib
    monkeypatch.setattr(aiosmtplib, "send", fake_send)

    await email_service.SmtpEmailClient().send(
        from_email="boss@a.vn", to_email="user@a.vn",
        subject="S", body="B",
    )
    assert captured["kwargs"]["use_tls"] is False
    assert captured["kwargs"]["start_tls"] is True
