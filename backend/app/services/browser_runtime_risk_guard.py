from __future__ import annotations

from typing import Any


_RISK_KEYWORDS = (
  "delete",
  "remove",
  "submit",
  "send",
  "confirm",
  "pay",
  "payment",
  "checkout",
  "购买",
  "支付",
  "提交",
  "发送",
  "删除",
  "确认",
)


class BrowserRiskGuard:
  @staticmethod
  def _is_high_risk(action: str, *, target: str = "", value: str = "", url: str = "") -> bool:
    act = str(action or "").strip().lower()
    if act not in {"click", "type", "submit"}:
      return False
    text = " ".join(
      [
        str(target or ""),
        str(value or ""),
        str(url or ""),
      ]
    ).lower()
    if not text:
      return False
    return any(token in text for token in _RISK_KEYWORDS)

  def check_high_risk(self, *, action: str, args: dict[str, Any]) -> dict[str, Any] | None:
    if bool(args.get("confirm")):
      return None
    target = str(args.get("target") or args.get("selector") or args.get("text") or "").strip()
    value = str(args.get("value") or "").strip()
    url = str(args.get("url") or "").strip()
    if not self._is_high_risk(action, target=target, value=value, url=url):
      return None
    next_args = dict(args or {})
    next_args["confirm"] = True
    return {
      "ok": False,
      "error": "confirmation_required",
      "requires_confirmation": True,
      "confirm_kind": "high_risk_action",
      "risk_level": "high",
      "action": str(action or "").strip().lower(),
      "next_call": {
        "tool": "browser_use",
        "action": str(action or "").strip().lower(),
        "args": next_args,
      },
    }

