"""Small, inspectable non-browser skills used by the live graph."""
from __future__ import annotations

import ast
import asyncio
import csv
import hashlib
import html
import math
import operator
import os
import re
import shutil
import sqlite3
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlsplit
from urllib.request import url2pathname
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from ddgs import DDGS


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.parts: list[str] = []; self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}: self.skip += 1
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr"}: self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip: self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip(): self.parts.append(data.strip() + " ")

    def text(self) -> str:
        value = html.unescape("".join(self.parts))
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", value)).strip()


def sandbox_path(path: str) -> Path:
    configured = os.getenv("S17_SANDBOX_ROOT")
    if not configured:
        raise PermissionError("local file skills require S17_SANDBOX_ROOT")
    root = Path(configured).expanduser().resolve()
    candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise PermissionError(f"path escapes S17_SANDBOX_ROOT: {path}")
    if not candidate.is_file():
        raise FileNotFoundError(path)
    return candidate


def sandbox_files(path: str, *, suffix: str = ".md") -> list[Path]:
    """Enumerate a sandbox directory without granting arbitrary traversal."""
    configured = os.getenv("S17_SANDBOX_ROOT")
    if not configured:
        raise PermissionError("local file skills require S17_SANDBOX_ROOT")
    root = Path(configured).expanduser().resolve()
    candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise PermissionError(f"path escapes S17_SANDBOX_ROOT: {path}")
    if not candidate.is_dir():
        raise NotADirectoryError(path)
    return sorted(item for item in candidate.iterdir() if item.is_file() and item.suffix.lower() == suffix.lower())


def sandbox_directories(path: str) -> list[Path]:
    configured = os.getenv("S17_SANDBOX_ROOT")
    if not configured:
        raise PermissionError("local file skills require S17_SANDBOX_ROOT")
    root = Path(configured).expanduser().resolve()
    candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise PermissionError(f"path escapes S17_SANDBOX_ROOT: {path}")
    if not candidate.is_dir():
        raise NotADirectoryError(path)
    return sorted(item for item in candidate.iterdir() if item.is_dir())


def sandbox_output_path(path: str) -> Path:
    """Resolve a possibly new output path without permitting root escape."""
    configured = os.getenv("S17_SANDBOX_ROOT")
    if not configured:
        raise PermissionError("local file skills require S17_SANDBOX_ROOT")
    root = Path(configured).expanduser().resolve()
    candidate = (root / path).resolve()
    if candidate == root or root not in candidate.parents:
        raise PermissionError(f"path escapes S17_SANDBOX_ROOT: {path}")
    return candidate


def write_text_file(path: str, content: str, *, overwrite: bool = False) -> dict:
    target = sandbox_output_path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    payload = target.read_bytes()
    return {"path": str(target), "uri": target.as_uri(), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}


def file_sha256(path: str) -> dict:
    target = sandbox_path(path)
    payload = target.read_bytes()
    return {"path": str(target), "uri": target.as_uri(), "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}


def copy_file(source: str, destination: str, *, overwrite: bool = False) -> dict:
    origin = sandbox_path(source)
    target = sandbox_output_path(destination)
    if target.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {destination}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origin, target)
    source_payload, destination_payload = origin.read_bytes(), target.read_bytes()
    source_hash = hashlib.sha256(source_payload).hexdigest()
    destination_hash = hashlib.sha256(destination_payload).hexdigest()
    return {"source": str(origin), "destination": str(target), "uri": target.as_uri(),
            "bytes": len(destination_payload), "source_sha256": source_hash,
            "destination_sha256": destination_hash, "match": source_hash == destination_hash}


def file_uri_to_path(uri: str) -> Path:
    """Convert a ``file://`` URI back into a filesystem path.

    ``Path.as_uri()`` on Windows emits a *triple*-slash URI for a drive-rooted
    path (``file:///C:/Users/...``) because the drive letter needs its own
    leading slash. Slicing that string by hand (``removeprefix("file://")`` or
    reading ``httpx.URL(uri).path`` directly) only strips two of the three
    slashes, leaving ``/C:/Users/...`` — a string pathlib refuses to treat as
    drive-rooted, since a bare leading slash makes ``C:`` look like an
    ordinary folder name. ``url2pathname`` is the stdlib's own inverse of
    ``as_uri()`` and handles this correctly on every platform.
    """
    parsed = urlsplit(uri)
    if parsed.scheme != "file":
        raise ValueError(f"expected a file:// URI, got {uri!r}")
    return Path(url2pathname(parsed.path))


_BINARY = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
            ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
_FUNCTIONS = {"abs": abs, "min": min, "max": max, "round": round, "sum": sum}


def _arithmetic(node: ast.AST, *, depth: int = 0):
    if depth > 20:
        raise ValueError("expression is too deeply nested")
    if isinstance(node, ast.Expression):
        return _arithmetic(node.body, depth=depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        if len(node.elts) > 100:
            raise ValueError("expression contains too many values")
        return [_arithmetic(item, depth=depth + 1) for item in node.elts]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _arithmetic(node.left, depth=depth + 1), _arithmetic(node.right, depth=depth + 1)
        if isinstance(node.op, ast.Pow) and abs(float(right)) > 12:
            raise ValueError("exponent exceeds the safe bound")
        return _BINARY[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_arithmetic(node.operand, depth=depth + 1))
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        return _COMPARE[type(node.ops[0])](_arithmetic(node.left, depth=depth + 1),
                                           _arithmetic(node.comparators[0], depth=depth + 1))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
        if node.keywords:
            raise ValueError("keyword arguments are not allowed")
        return _FUNCTIONS[node.func.id](*[_arithmetic(arg, depth=depth + 1) for arg in node.args])
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def calculate(expression: str) -> dict:
    tree = ast.parse(expression, mode="eval")
    result = _arithmetic(tree)
    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError("result is not finite")
    return {"expression": expression, "result": result}


def query_csv(files: list[str], sql: str) -> dict:
    statement = sql.strip()
    if not re.match(r"^(select|with)\b", statement, re.I):
        raise ValueError("query_csv permits only SELECT or WITH queries")
    if ";" in statement.rstrip(";") or re.search(
        r"\b(attach|detach|pragma|insert|update|delete|drop|alter|create|replace|vacuum)\b", statement, re.I
    ):
        raise ValueError("query_csv rejected a non-read-only SQL operation")
    connection = sqlite3.connect(":memory:")
    loaded: list[dict] = []
    try:
        for relative in files:
            path = sandbox_path(relative)
            table = re.sub(r"\W+", "_", path.stem).strip("_") or "data"
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                fieldnames = reader.fieldnames or []
                columns = [re.sub(r"\W+", "_", name).strip("_") or f"column_{index}"
                           for index, name in enumerate(fieldnames, 1)]
                if not columns:
                    raise ValueError(f"CSV has no header: {relative}")
                raw_rows = [tuple(row.get(name, "") for name in fieldnames) for row in reader]
                types: list[str] = []
                for index in range(len(columns)):
                    values = [str(row[index]).strip() for row in raw_rows if str(row[index]).strip()]
                    if values and all(re.fullmatch(r"[+-]?\d+", value) for value in values):
                        types.append("INTEGER")
                    elif values and all(re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value)
                                        for value in values):
                        types.append("REAL")
                    else:
                        types.append("TEXT")
                quoted = ",".join(f'"{column}" {kind}' for column, kind in zip(columns, types))
                connection.execute(f'CREATE TABLE "{table}" ({quoted})')
                placeholders = ",".join("?" for _ in columns)
                converters = {"INTEGER": int, "REAL": float, "TEXT": str}
                rows = [tuple(converters[kind](value) if str(value).strip() else None
                              for value, kind in zip(row, types)) for row in raw_rows]
                connection.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
            loaded.append({"file": relative, "table": table, "rows": len(rows),
                           "columns": columns, "types": types})
        cursor = connection.execute(statement)
        columns = [item[0] for item in cursor.description or []]
        rows = [dict(zip(columns, row)) for row in cursor.fetchmany(201)]
        truncated = len(rows) > 200
        return {"files": loaded, "sql": statement, "columns": columns,
                "rows": rows[:200], "row_count": min(len(rows), 200), "truncated": truncated}
    finally:
        connection.close()


def current_datetime(timezone: str = "UTC") -> dict:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"unknown IANA timezone: {timezone}") from error
    now = datetime.now(zone)
    return {"timezone": timezone, "iso": now.isoformat(), "date": now.date().isoformat(),
            "weekday": now.strftime("%A"), "utc_offset": now.strftime("%z")}


def date_shift(value: str, days: int) -> dict:
    try:
        original = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid ISO date: {value}") from error
    shifted = original + timedelta(days=days)
    return {"date": value, "days": days, "result": shifted.isoformat(),
            "weekday": shifted.strftime("%A")}


async def fetch_url(url: str, *, max_chars: int = 60_000) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("fetch_url permits only http(s)")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                 headers={"User-Agent": "GLC-S17/0.3 educational-agent"}) as client:
        response = await client.get(url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" in content_type:
        parser = _TextExtractor(); parser.feed(response.text); text = parser.text()
    else:
        text = response.text
    return {"url": str(response.url), "status": response.status_code,
            "content_type": content_type, "text": text[:max_chars], "truncated": len(text) > max_chars}


class _DDGParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.hits: list[dict] = []; self.current: dict | None = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs); classes = values.get("class", "")
        if tag == "a" and "result__a" in classes:
            href = values.get("href", "")
            target = parse_qs(urlparse(href).query).get("uddg", [href])[0]
            self.current = {"title": "", "url": unquote(target), "snippet": ""}; self.hits.append(self.current)
        elif tag in {"a", "div"} and "result__snippet" in classes and self.hits:
            self.current = self.hits[-1]

    def handle_data(self, data):
        if self.current and data.strip():
            key = "title" if not self.current["title"] else "snippet"
            self.current[key] = (self.current[key] + " " + data.strip()).strip()


def _search_with_ddgs(query: str, max_results: int) -> list[dict]:
    """Run the blocking multi-backend search client outside the event loop."""
    rows = DDGS(timeout=15).text(query, max_results=max_results)
    return [
        {
            "title": str(row.get("title", "")).strip(),
            "url": str(row.get("href", "")).strip(),
            "snippet": str(row.get("body", "")).strip(),
        }
        for row in rows
        if str(row.get("href", "")).startswith(("http://", "https://"))
    ]


async def web_search(query: str, *, max_results: int = 5) -> dict:
    max_results = max(1, min(max_results, 5))
    errors: list[str] = []
    try:
        hits = await asyncio.to_thread(_search_with_ddgs, query, max_results)
        if hits:
            return {"query": query, "hits": hits, "backend": "ddgs", "errors": errors}
        errors.append("ddgs returned no results")
    except Exception as exc:
        errors.append(f"ddgs: {type(exc).__name__}: {exc}")

    # Small dependency-free fallback. It is deliberately secondary because the
    # HTML endpoint can rate-limit automated clients.
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 GLC-S17"}) as client:
            response = await client.get("https://html.duckduckgo.com/html/", params={"q": query})
            response.raise_for_status()
        parser = _DDGParser(); parser.feed(response.text)
        hits = [hit for hit in parser.hits if hit["url"]][:max_results]
        if not hits:
            errors.append("duckduckgo-html returned no results")
        return {"query": query, "hits": hits, "backend": "duckduckgo-html", "errors": errors}
    except Exception as exc:
        errors.append(f"duckduckgo-html: {type(exc).__name__}: {exc}")
        return {"query": query, "hits": [], "backend": None, "errors": errors}
