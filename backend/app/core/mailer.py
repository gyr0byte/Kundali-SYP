"""Mailer protocol and ConsoleMailer implementation."""

from typing import Protocol


class Mailer(Protocol):
    """Protocol for sending email notifications."""

    def send_password_reset_email(self, to_email: str, reset_token: str, reset_url: str) -> None:
        """Send a password reset email to the recipient."""
        ...


class ConsoleMailer:
    """Development mailer that prints to stdout only when in dev environment."""

    def __init__(self, environment: str = "prod") -> None:
        self.environment = environment

    def send_password_reset_email(self, to_email: str, reset_token: str, reset_url: str) -> None:
        """Print password reset link to stdout if in dev environment."""
        if self.environment == "dev":
            print(
                f"[ConsoleMailer] Password reset email for: {to_email}\n"
                f"  Token: {reset_token}\n"
                f"  Reset Link: {reset_url}\n"
            )
