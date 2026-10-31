"""Unit tests for Mailer protocol and ConsoleMailer behavior."""

from app.core.mailer import ConsoleMailer


def test_console_mailer_prints_in_dev_environment(capsys: object) -> None:
    """ConsoleMailer prints the reset link when ENVIRONMENT == 'dev'."""
    mailer = ConsoleMailer(environment="dev")
    mailer.send_password_reset_email(
        to_email="asha@example.com",
        reset_token="sample-token-12345",
        reset_url="http://localhost:3000/auth/reset-password?token=sample-token-12345",
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "asha@example.com" in captured.out
    assert "sample-token-12345" in captured.out
    assert "http://localhost:3000/auth/reset-password?token=sample-token-12345" in captured.out


def test_console_mailer_silent_in_prod_environment(capsys: object) -> None:
    """ConsoleMailer prints nothing when ENVIRONMENT == 'prod'."""
    mailer = ConsoleMailer(environment="prod")
    mailer.send_password_reset_email(
        to_email="asha@example.com",
        reset_token="sample-token-12345",
        reset_url="http://localhost:3000/auth/reset-password?token=sample-token-12345",
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert captured.err == ""


def test_console_mailer_silent_in_test_environment(capsys: object) -> None:
    """ConsoleMailer prints nothing when ENVIRONMENT == 'test'."""
    mailer = ConsoleMailer(environment="test")
    mailer.send_password_reset_email(
        to_email="asha@example.com",
        reset_token="sample-token-12345",
        reset_url="http://localhost:3000/auth/reset-password?token=sample-token-12345",
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert captured.err == ""
