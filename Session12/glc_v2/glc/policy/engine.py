"""Declarative policy engine.

evaluate(tool_call, context) -> PolicyVerdict
  - first matching rule wins
  - ties resolve to deny
  - default allow when trust_level == 'owner_paired' and no rule matches
  - default deny otherwise

Hot reload on SIGHUP (process-level handler installed by main.py). Malformed
yaml is rejected: the engine falls back to a deny-everything safe-default
config and logs a warning so the gateway boots in a known-safe state.

LEAK-5 MITIGATION: Monkey-patching detection via signature validation.
Full fix requires separate policy engine process (capstone scope).
"""

from __future__ import annotations

import fnmatch
import hashlib
import inspect
import re
import threading
from pathlib import Path
from typing import Any

import yaml

from glc.policy.schemas import PolicyConfig, PolicyRule, PolicyVerdict

# LEAK-5 FIX: Track original evaluate() signature and bytecode
_ORIGINAL_EVALUATE_SIGNATURE: str | None = None
_EVALUATE_HASH: str | None = None

_SAFE_DEFAULT = PolicyConfig(
    rules=[
        PolicyRule(
            tool="*",
            trust_level="*",
            action="deny",
            reason="policy.yaml unreadable — falling back to deny-everything",
        )
    ]
)


def _matches_glob(value: Any, pattern: str) -> bool:
    if not isinstance(value, str):
        return False
    # fnmatch's ** support is weak; substitute ** for a regex-ish pattern.
    if "**" in pattern:
        regex = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        return bool(re.match(regex + "$", value))
    return fnmatch.fnmatch(value, pattern)


def _matches_condition(condition: dict[str, Any], params: dict[str, Any]) -> bool:
    for key, expected in condition.items():
        if key.endswith("_glob"):
            target = key[: -len("_glob")]
            if not _matches_glob(params.get(target), expected):
                return False
        elif key.endswith("_regex"):
            target = key[: -len("_regex")]
            val = params.get(target)
            if not isinstance(val, str) or not re.search(expected, val):
                return False
        elif key.endswith("_in"):
            target = key[: -len("_in")]
            if params.get(target) not in (expected or []):
                return False
        elif key == "command_matches":
            cmd = params.get("command", "")
            if not isinstance(cmd, str):
                return False
            patterns = expected if isinstance(expected, list) else [expected]
            if not any(p in cmd for p in patterns):
                return False
        elif key == "recipient_type":
            if params.get("recipient_type") != expected:
                return False
        elif isinstance(expected, list):
            if params.get(key) not in expected:
                return False
        else:
            if params.get(key) != expected:
                return False
    return True


class PolicyEngine:
    def __init__(self, config: PolicyConfig):
        self.config = config
        self._lock = threading.Lock()

    @classmethod
    def from_yaml(cls, path: Path | str) -> PolicyEngine:
        p = Path(path)
        if not p.exists():
            return cls(_SAFE_DEFAULT)
        try:
            raw = yaml.safe_load(p.read_text()) or {}
            cfg = PolicyConfig.model_validate(raw)
        except Exception as e:  # pragma: no cover
            print(f"[glc.policy] malformed {p}: {e!r} — using deny-everything safe default")
            cfg = _SAFE_DEFAULT
        return cls(cfg)

    def evaluate(self, tool_call: dict[str, Any], context: dict[str, Any]) -> PolicyVerdict:
        """tool_call = {'name': 'email.send', 'arguments': {...}}
        context   = {'channel': 'telegram', 'trust_level': 'owner_paired',
                     'channel_user_id': '...'}"""
        tool = tool_call.get("name", "")
        params = tool_call.get("arguments") or {}
        channel = context.get("channel", "")
        trust_level = context.get("trust_level", "untrusted")

        with self._lock:
            rules = list(self.config.rules)

        deny_match: tuple[int, PolicyRule] | None = None
        first_match: tuple[int, PolicyRule] | None = None
        for i, rule in enumerate(rules):
            if rule.tool != "*" and rule.tool != tool:
                continue
            if rule.channel != "*" and rule.channel != channel:
                continue
            if rule.trust_level != "*" and rule.trust_level != trust_level:
                continue
            if rule.condition and not _matches_condition(rule.condition, params):
                continue
            if first_match is None:
                first_match = (i, rule)
            if rule.action == "deny" and deny_match is None:
                deny_match = (i, rule)

        if deny_match is not None:
            i, r = deny_match
            return PolicyVerdict(action="deny", reason=r.reason or "denied by policy", matched_rule_index=i)
        if first_match is not None:
            i, r = first_match
            return PolicyVerdict(
                action=r.action, reason=r.reason or f"matched rule #{i}", matched_rule_index=i
            )
        if trust_level == "owner_paired":
            return PolicyVerdict(action="allow", reason="default-allow for owner_paired")
        return PolicyVerdict(action="deny", reason=f"default-deny for trust_level={trust_level}")

    def reload(self, path: Path | str) -> None:
        new = PolicyEngine.from_yaml(path)
        with self._lock:
            self.config = new.config


# Module-level singleton, lazily constructed from config.policy_yaml_path().
_engine: PolicyEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> PolicyEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            from glc.config import policy_yaml_path

            _engine = PolicyEngine.from_yaml(policy_yaml_path())
    return _engine


def reload_engine() -> None:
    from glc.config import policy_yaml_path

    eng = get_engine()
    eng.reload(policy_yaml_path())


def evaluate(tool_call: dict[str, Any], context: dict[str, Any]) -> PolicyVerdict:
    """LEAK-5 PROTECTED: Validate integrity before evaluation."""
    _verify_evaluate_integrity()
    return get_engine().evaluate(tool_call, context)


def _compute_function_hash(func) -> str:
    """Compute hash of function bytecode to detect tampering."""
    return hashlib.sha256(func.__code__.co_code).hexdigest()


def _init_evaluate_protection():
    """Initialize evaluate() integrity tracking."""
    global _ORIGINAL_EVALUATE_SIGNATURE, _EVALUATE_HASH
    _ORIGINAL_EVALUATE_SIGNATURE = str(inspect.signature(evaluate))
    _EVALUATE_HASH = _compute_function_hash(evaluate)


def _verify_evaluate_integrity():
    """Check if evaluate() has been monkey-patched.

    LEAK-5 MITIGATION: Detect function signature or bytecode changes.
    Raises RuntimeError if tampering detected.
    """
    global _ORIGINAL_EVALUATE_SIGNATURE, _EVALUATE_HASH

    if _ORIGINAL_EVALUATE_SIGNATURE is None:
        _init_evaluate_protection()
        return

    current_sig = str(inspect.signature(evaluate))
    current_hash = _compute_function_hash(evaluate)

    if current_sig != _ORIGINAL_EVALUATE_SIGNATURE or current_hash != _EVALUATE_HASH:
        raise RuntimeError(
            f"[LEAK-5] Policy engine tampering detected! "
            f"evaluate() has been modified. "
            f"Expected signature: {_ORIGINAL_EVALUATE_SIGNATURE}, "
            f"Got: {current_sig}"
        )
