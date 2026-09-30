"""Process-wide test safety net — applies before any test file's own
module-level code runs (pytest imports conftest.py first).

EMAIL_PROVIDER is forced to "mock" here, unconditionally, overriding
whatever a developer's local `backend/.env` happens to contain. Real
environment variables take precedence over `.env` file values in
pydantic-settings (Settings.model_config's `env_file=".env"`), so
setting it here in `os.environ` — before any test constructs Settings —
guarantees the automated suite can never attempt a real SMTP send, no
matter what EMAIL_PROVIDER a developer has configured locally for
manual/integration testing (see P3.1's SMTPEmailProvider and README.md's
"Email delivery" section). A misconfigured local `.env` should never be
able to make `pytest -q` silently start sending real email to whatever
addresses the provisioning tests happen to construct.
"""

import os

os.environ["EMAIL_PROVIDER"] = "mock"
