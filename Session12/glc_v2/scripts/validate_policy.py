"""Policy validator: loads policy.yaml through the engine. Passing means
the YAML parses, the rules satisfy the PolicyConfig schema, and the
engine accepts at least the five lecture-default rules.
"""

from __future__ import annotations

import sys

from glc.config import PACKAGED_POLICY
from glc.policy.engine import PolicyEngine


def main() -> int:
    eng = PolicyEngine.from_yaml(PACKAGED_POLICY)
    n = len(eng.config.rules)
    if n < 5:
        print(f"FAIL: policy.yaml has {n} rules, expected the lecture's 5 defaults")
        return 1
    # Force an evaluation of each tool referenced in the rules — the
    # engine should not throw on any of the defaults.
    for r in eng.config.rules:
        eng.evaluate(
            {"name": r.tool if r.tool != "*" else "probe.tool", "arguments": {}},
            {"channel": "x", "trust_level": "owner_paired"},
        )
    print(f"OK: policy.yaml loaded {n} rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
