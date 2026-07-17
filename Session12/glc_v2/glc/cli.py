"""glc CLI entry point. `uv run glc serve` boots the gateway."""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="glc")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="boot the gateway")
    p_serve.add_argument("--host", default=os.getenv("GLC_HOST", "0.0.0.0"))
    p_serve.add_argument("--port", type=int, default=int(os.getenv("GLC_PORT", "8111")))
    p_serve.add_argument("--reload", action="store_true")

    sub.add_parser("token", help="print the per-installation control token")
    sub.add_parser("channels", help="list channels discovered in the catalogue")

    args = parser.parse_args()

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("glc.main:app", host=args.host, port=args.port, reload=args.reload)
        return 0
    if args.cmd == "token":
        from glc.config import get_or_create_install_token

        print(get_or_create_install_token(_allow_in_process=True))  # LEAK-4: CLI tool only
        return 0
    if args.cmd == "channels":
        from glc.channels.registry import discover

        for name, cls in sorted(discover().items()):
            print(f"  {name:14}  {cls.__module__}.{cls.__name__}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
