from __future__ import annotations

from typing import Iterable
from email.message import EmailMessage
import smtplib

from rich.console import Console
from rich.table import Table

from domain_hunter.types import AppConfig, HistoryResult, ScoreResult


async def notify_results(
    scores: Iterable[ScoreResult],
    histories: Iterable[HistoryResult],
    config: AppConfig,
) -> None:
    score_list = list(scores)
    history_by_domain = {history.domain: history for history in histories}

    if not score_list and not config.send_empty_report:
        return

    if _email_configured(config):
        _send_email(config, score_list, history_by_domain)
        return
    _print_console(score_list, history_by_domain)


def _email_configured(config: AppConfig) -> bool:
    return bool(config.smtp_host and config.email_from and config.email_to)


def _send_email(
    config: AppConfig,
    scores: list[ScoreResult],
    history_by_domain: dict[str, HistoryResult],
) -> None:
    message = EmailMessage()
    message["Subject"] = "Domain Hunter - Candidate Report"
    message["From"] = config.email_from
    message["To"] = config.email_to
    message.set_content(_plain_text(scores, history_by_domain))
    message.add_alternative(_html_report(scores, history_by_domain), subtype="html")

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
        if config.smtp_use_tls:
            smtp.starttls()
        if config.smtp_username:
            smtp.login(config.smtp_username, config.smtp_password)
        smtp.send_message(message)


async def send_test_email(config: AppConfig) -> None:
    if not _email_configured(config):
        raise ValueError("请先配置 SMTP 主机、发件人和收件人。")

    message = EmailMessage()
    message["Subject"] = "Domain Hunter - Test Email"
    message["From"] = config.email_from
    message["To"] = config.email_to
    message.set_content("这是一封 Domain Hunter 测试邮件。")

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
        if config.smtp_use_tls:
            smtp.starttls()
        if config.smtp_username:
            smtp.login(config.smtp_username, config.smtp_password)
        smtp.send_message(message)


def _plain_text(scores: list[ScoreResult], history_by_domain: dict[str, HistoryResult]) -> str:
    if not scores:
        return "No clean available candidates found."
    lines = ["Domain Hunter candidates:"]
    for score in scores[:50]:
        history = history_by_domain.get(score.domain)
        history_note = history.notes if history else "not checked"
        lines.append(f"{score.domain} score={score.total_score} history={history_note}")
    return "\n".join(lines)


def _html_report(scores: list[ScoreResult], history_by_domain: dict[str, HistoryResult]) -> str:
    rows = []
    for score in scores[:100]:
        history = history_by_domain.get(score.domain)
        rows.append(
            "<tr>"
            f"<td>{_escape(score.domain)}</td>"
            f"<td>{score.total_score}</td>"
            f"<td>{_escape(', '.join(score.reasons))}</td>"
            f"<td>{_escape(history.notes if history else 'not checked')}</td>"
            "</tr>"
        )
    body = "\n".join(rows) or "<tr><td colspan='4'>No clean available candidates found.</td></tr>"
    return f"""
    <html>
      <body>
        <h2>Domain Hunter Candidate Report</h2>
        <table border="1" cellpadding="8" cellspacing="0">
          <thead>
            <tr><th>Domain</th><th>Score</th><th>Reasons</th><th>History</th></tr>
          </thead>
          <tbody>{body}</tbody>
        </table>
      </body>
    </html>
    """


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _print_console(scores: list[ScoreResult], history_by_domain: dict[str, HistoryResult]) -> None:
    console = Console()
    table = Table(title="Domain Hunter candidates")
    table.add_column("Domain")
    table.add_column("Score", justify="right")
    table.add_column("Reasons")
    table.add_column("History")

    for score in scores[:50]:
        history = history_by_domain.get(score.domain)
        history_note = history.notes if history else "not checked"
        table.add_row(score.domain, str(score.total_score), ", ".join(score.reasons), history_note)
    console.print(table)
