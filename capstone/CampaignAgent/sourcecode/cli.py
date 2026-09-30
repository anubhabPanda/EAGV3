from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="sourcecode")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=int(os.getenv("S17_PORT", "8113")))
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("sourcecode.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
