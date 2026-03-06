from __future__ import annotations

from app.services.browser_automation import browser_automation_service

# Login checkpoint and resume state still live in the legacy automation service
# until the browser runtime split is completed.
browser_runtime_login_service = browser_automation_service
