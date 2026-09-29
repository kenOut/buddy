"""Plain Python string templates — no templating framework or new
dependency (this project has none; see requirements.txt), and a single
welcome email doesn't justify adding one. Renders both the HTML and
plain-text bodies from the same inputs in one place, so the two can't
silently drift apart in *content* (only presentation differs) the way
they could if built separately at each call site.

Deliberately knows nothing about Employee/EmployeeInvitation/
SQLAlchemy — takes plain strings, returns a plain RenderedEmail. Keeps
this module usable and testable with zero database/app setup, same
reasoning as email_provider.py.
"""

from dataclasses import dataclass
from html import escape

WELCOME_EMAIL_SUBJECT = "Welcome to Kowri Technologies — Meet Your Buddy!"


@dataclass
class RenderedEmail:
    subject: str
    html: str
    text: str


def _first_name(full_name: str) -> str:
    stripped = full_name.strip()
    return stripped.split(" ")[0] if stripped else full_name


def render_welcome_invitation_email(*, employee_full_name: str, invitation_url: str) -> RenderedEmail:
    """The one Buddy email this project has (Section 7). `invitation_url`
    must already be the full, real URL the "Meet Heimdall" CTA should
    point at — this function does no URL construction of its own (see
    email_service.build_invitation_url) and has no opinion about
    tokens, hashing, or where the raw token came from."""
    first_name = _first_name(employee_full_name)

    text = (
        f"Hi {first_name},\n\n"
        "Welcome to Kowri Technologies.\n\n"
        "I'm Heimdall, your digital workplace companion.\n\n"
        "I'll help you get oriented, understand your team and responsibilities, "
        "and guide you through the work you'll complete as you get started.\n\n"
        "When you're ready, let's begin.\n\n"
        f"Meet Heimdall: {invitation_url}\n\n"
        "See you inside,\n"
        "Heimdall"
    )

    safe_name = escape(first_name)
    safe_url = escape(invitation_url, quote=True)
    html = f"""<!doctype html>
<html>
  <body style="font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a1a; max-width: 480px; margin: 0 auto; padding: 24px;">
    <p>Hi {safe_name},</p>
    <p>Welcome to Kowri Technologies.</p>
    <p>I&rsquo;m Heimdall, your digital workplace companion.</p>
    <p>I&rsquo;ll help you get oriented, understand your team and responsibilities, and guide you through the work you&rsquo;ll complete as you get started.</p>
    <p>When you&rsquo;re ready, let&rsquo;s begin.</p>
    <p>
      <a href="{safe_url}" style="display:inline-block;background:#0f9d58;color:#ffffff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600;">Meet Heimdall</a>
    </p>
    <p>See you inside,<br/>Heimdall</p>
  </body>
</html>
"""

    return RenderedEmail(subject=WELCOME_EMAIL_SUBJECT, html=html, text=text)
