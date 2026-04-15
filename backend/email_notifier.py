import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from models import DefectAnalysis, StoryAnalysis, TestExecutionSummary


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_email_body(
    *,
    user_story: str,
    story: StoryAnalysis,
    execution: TestExecutionSummary,
    defects: DefectAnalysis,
    session_id: str,
) -> tuple[str, str]:
    passed = sum(1 for item in execution.results if item.status == "pass")
    failed = sum(1 for item in execution.results if item.status == "fail")
    errors = sum(1 for item in execution.results if item.status == "error")
    skipped = sum(1 for item in execution.results if item.status == "skipped")
    total = len(execution.results)
    pass_rate = (passed / max(1, passed + failed + errors)) * 100
    critical = ", ".join(defects.critical_test_ids[:6]) or "None"
    modules = ", ".join(story.modules[:8]) or "None"
    run_time = datetime.now(timezone.utc).isoformat()

    top_risks = defects.module_risks[:5]
    risk_rows_html = "".join(
        f"<tr><td>{risk.module}</td><td>{risk.regression_risk}</td><td>{risk.defect_probability * 100:.1f}%</td></tr>"
        for risk in top_risks
    )
    if not risk_rows_html:
        risk_rows_html = "<tr><td colspan='3'>No module risk entries</td></tr>"

    text_body = (
        "IronTest Execution Summary\n"
        "==========================\n"
        f"Run Time (UTC): {run_time}\n"
        f"Session ID: {session_id}\n\n"
        f"Story Intent: {story.intent or 'N/A'}\n"
        f"Modules: {modules}\n\n"
        f"Confidence Score: {defects.overall_confidence_score}\n"
        f"Deployment Recommendation: {defects.deployment_recommendation}\n"
        f"Rationale: {defects.recommendation_rationale}\n"
        f"Critical Test IDs: {critical}\n\n"
        f"Execution Totals: {passed} pass, {failed} fail, {errors} error, {skipped} skipped (total {total})\n"
        f"Pass Rate: {pass_rate:.1f}%\n"
        f"Duration: {execution.duration_seconds:.2f}s\n\n"
        f"User Story (truncated): {user_story[:700]}\n"
    )

    html_body = f"""
    <html>
      <body style=\"font-family:Segoe UI,Arial,sans-serif;color:#0f172a;\">
        <h2 style=\"margin-bottom:4px;\">IronTest Execution Summary</h2>
        <p style=\"margin-top:0;color:#475569;\">Run Time (UTC): {run_time}</p>
        <p><strong>Session ID:</strong> {session_id}</p>
        <p><strong>Story Intent:</strong> {story.intent or 'N/A'}</p>
        <p><strong>Modules:</strong> {modules}</p>
        <hr />
        <p><strong>Confidence Score:</strong> {defects.overall_confidence_score}</p>
        <p><strong>Deployment Recommendation:</strong> {defects.deployment_recommendation}</p>
        <p><strong>Rationale:</strong> {defects.recommendation_rationale}</p>
        <p><strong>Critical Test IDs:</strong> {critical}</p>
        <hr />
        <p><strong>Execution Totals:</strong> {passed} pass, {failed} fail, {errors} error, {skipped} skipped (total {total})</p>
        <p><strong>Pass Rate:</strong> {pass_rate:.1f}%</p>
        <p><strong>Duration:</strong> {execution.duration_seconds:.2f}s</p>
        <h3>Top Module Risks</h3>
        <table style=\"border-collapse:collapse;width:100%;\" border=\"1\" cellpadding=\"6\">
          <thead style=\"background:#f1f5f9;\"><tr><th>Module</th><th>Regression Risk</th><th>Defect Probability</th></tr></thead>
          <tbody>{risk_rows_html}</tbody>
        </table>
        <p style=\"margin-top:16px;\"><strong>User Story (truncated):</strong> {user_story[:700]}</p>
      </body>
    </html>
    """

    return text_body, html_body


def send_execution_summary_email(
    *,
    recipient_email: str,
    user_story: str,
    story: StoryAnalysis,
    execution: TestExecutionSummary,
    defects: DefectAnalysis,
    session_id: str,
) -> tuple[bool, str]:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_user or "").strip()
    smtp_use_tls = _bool_env("SMTP_USE_TLS", True)
    smtp_use_ssl = _bool_env("SMTP_USE_SSL", False)

    if not smtp_host:
        return False, "Email skipped: SMTP_HOST is not configured."
    if not smtp_from:
        return False, "Email skipped: SMTP_FROM_EMAIL (or SMTP_USERNAME) is not configured."

    subject_prefix = os.getenv("EMAIL_SUBJECT_PREFIX", "IronTest")
    subject = f"{subject_prefix} Execution Result - {defects.deployment_recommendation} ({defects.overall_confidence_score})"

    text_body, html_body = _build_email_body(
        user_story=user_story,
        story=story,
        execution=execution,
        defects=defects,
        session_id=session_id,
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_from
    message["To"] = recipient_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        if smtp_use_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                if smtp_use_tls:
                    server.starttls()
                    server.ehlo()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(message)
        return True, f"Execution summary email sent to {recipient_email}."
    except Exception as exc:  # noqa: BLE001
        return False, f"Email delivery failed: {exc}"
