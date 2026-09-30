"""The complete capability surface exposed to the S17 planner.

The planner sees descriptions and machine-checkable argument contracts. Workers
remain ordinary Python callables owned by the runtime; a model can select a
capability, but it cannot invent one or bypass its validation boundary.

Everything a generic component needs to know about a capability is *declared
here*, never switched on by name somewhere else:

* `Argument.format` carries value-level rules such as "this must be an absolute
  http(s) URL", so the validator stays a general loop;
* `Capability.evidence` declares how a result becomes answer-worker evidence,
  so adding a capability never means editing the runtime;
* `Capability.families` groups capabilities for components that need a class of
  capability ("which of these gather evidence?") rather than a specific one.

If you find yourself writing `if skill == "something"` outside this module, the
missing piece is a declaration here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any
from urllib.parse import urlparse

# A capability worker may report that it ran but could not obtain what was
# asked of it. These two optional result keys are the declared, registry-owned
# way to say so; the planner's evidence review reads them generically.
GAP_FIELDS = ("insufficient", "missing")


class CapabilityError(ValueError):
    """A proposed task does not satisfy the advertised capability contract."""


def _check_format(label: str, format_name: str, value: Any) -> None:
    """Validate a declared value format. Unknown formats are a configuration bug."""
    if format_name == "url":
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise CapabilityError(f"{label} must be an absolute http(s) URL")
        return
    if format_name == "iso_date":
        try:
            _date.fromisoformat(value)
        except (TypeError, ValueError):
            raise CapabilityError(f"{label} must be an ISO-8601 date (YYYY-MM-DD)") from None
        return
    raise CapabilityError(f"unsupported argument format {format_name!r} on {label}")


@dataclass(frozen=True)
class Argument:
    kind: str
    description: str
    required: bool = True
    default: Any = None
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()
    item_kind: str | None = None
    format: str | None = None

    def manifest(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.kind, "description": self.description}
        if not self.required:
            result["required"] = False
            if self.default is not None:
                result["default"] = self.default
        if self.minimum is not None:
            result["minimum"] = self.minimum
        if self.maximum is not None:
            result["maximum"] = self.maximum
        if self.choices:
            result["enum"] = list(self.choices)
        if self.item_kind:
            result["items"] = {"type": self.item_kind}
        if self.format:
            result["format"] = self.format
        return result


@dataclass(frozen=True)
class EvidenceProjection:
    """How one capability's result becomes evidence for the answer worker.

    The answer worker must be able to attribute every claim to a source. Before
    this existed, it carried a branch per capability, which quietly made every
    *new* capability a second-class citizen: its outcome was dumped as raw JSON
    with no source attribution. Declaring the projection beside the capability
    keeps the projector generic and gives a student-added capability exactly the
    same evidence quality as a built-in one.
    """

    kind: str = "capability"
    records: str | None = None          # result key holding ready-made evidence records
    record: str | None = None           # result key holding one ready-made record
    text: str | None = None             # result key holding the main text body
    join: str | None = None             # result key holding a list to join into the text
    prefix: str = ""                    # literal prefix for a joined text
    sources: tuple[str, ...] = ()       # result keys holding source URIs (str or list)
    source_template: str | None = None  # e.g. "file://{path}", formatted from the result
    items: str | None = None            # result key holding sub-items to expand one by one
    item_text: tuple[str, ...] = ()     # item keys joined with ": " to form each item's text
    item_source: str | None = None      # item key holding that item's URI
    item_kind: str | None = None        # kind label for expanded items
    summary: str | None = None          # template used when `items` is present but empty
    summary_kind: str | None = None     # kind label for that summary record
    prepend: bool = False               # put this evidence first (user statements outrank pages)
    external_sources: bool = False      # fall back to the run's collected external URLs

    def manifest(self) -> dict[str, Any]:
        return {"kind": self.kind, "expands": self.items, "prepend": self.prepend}


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    arguments: dict[str, Argument] = field(default_factory=dict)
    role: str | None = None
    side_effect: bool = False
    terminal_for: tuple[str, ...] = ()
    families: tuple[str, ...] = ()
    evidence: EvidenceProjection | None = None
    # Declare family "rerunnable" when the answer depends on the state of the
    # world and not only on the arguments. Searching the same query twice is
    # waste; running the same test suite twice, after an edit, is the whole
    # point of a coding loop. The planner's deduplication reads this.
    # An extra instruction this role needs. Declared here so the generic role
    # worker stays generic instead of carrying `if skill == ...` for one of them.
    role_rule: str = ""

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": {name: spec.manifest() for name, spec in self.arguments.items()},
            "side_effect": self.side_effect,
            "terminal_for": list(self.terminal_for),
        }


class CapabilityRegistry:
    def __init__(self, capabilities: list[Capability]) -> None:
        self._items = {item.name: item for item in capabilities}
        if len(self._items) != len(capabilities):
            raise ValueError("capability names must be unique")

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def get(self, name: str) -> Capability:
        try:
            return self._items[name]
        except KeyError as error:
            raise CapabilityError(f"unknown capability {name!r}") from error

    def manifest(self) -> list[dict[str, Any]]:
        return [item.manifest() for item in self._items.values()]

    def names(self) -> tuple[str, ...]:
        return tuple(self._items)

    def terminal_skills(self, respond_as: str) -> set[str]:
        return {item.name for item in self._items.values() if respond_as in item.terminal_for}

    def family(self, name: str) -> set[str]:
        """Every capability declaring membership of a named family.

        Components that care about a *class* of capability ask here instead of
        embedding a literal set of names that goes stale the moment somebody
        adds a capability.
        """
        return {item.name for item in self._items.values() if name in item.families}

    def projection(self, name: str) -> EvidenceProjection:
        capability = self._items.get(name)
        if capability is None or capability.evidence is None:
            # An undeclared capability still produces evidence; it simply gets
            # the generic projection rather than a tailored one.
            return EvidenceProjection(kind=f"capability:{name}")
        return capability.evidence

    def validate(self, name: str, values: Any) -> dict[str, Any]:
        capability = self.get(name)
        if not isinstance(values, dict):
            raise CapabilityError(f"arguments for {name} must be an object")
        unknown = set(values).difference(capability.arguments)
        if unknown:
            raise CapabilityError(f"unsupported arguments for {name}: {sorted(unknown)}")
        clean: dict[str, Any] = {}
        for key, spec in capability.arguments.items():
            if key not in values:
                if spec.required:
                    raise CapabilityError(f"{name} requires argument {key!r}")
                if spec.default is not None:
                    clean[key] = spec.default
                continue
            value = values[key]
            if spec.kind == "string":
                if not isinstance(value, str) or not value.strip():
                    raise CapabilityError(f"{name}.{key} must be a non-empty string")
                value = value.strip()
                if spec.maximum is not None and len(value) > spec.maximum:
                    raise CapabilityError(f"{name}.{key} exceeds {spec.maximum} characters")
            elif spec.kind == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise CapabilityError(f"{name}.{key} must be an integer")
                if spec.minimum is not None and value < spec.minimum:
                    raise CapabilityError(f"{name}.{key} must be >= {spec.minimum}")
                if spec.maximum is not None and value > spec.maximum:
                    raise CapabilityError(f"{name}.{key} must be <= {spec.maximum}")
            elif spec.kind == "array":
                if not isinstance(value, list):
                    raise CapabilityError(f"{name}.{key} must be an array")
                if spec.minimum is not None and len(value) < spec.minimum:
                    raise CapabilityError(f"{name}.{key} needs at least {spec.minimum} items")
                if spec.maximum is not None and len(value) > spec.maximum:
                    raise CapabilityError(f"{name}.{key} permits at most {spec.maximum} items")
                if spec.item_kind == "string" and not all(isinstance(item, str) and item.strip() for item in value):
                    raise CapabilityError(f"every {name}.{key} item must be a non-empty string")
                value = [item.strip() if isinstance(item, str) else item for item in value]
            elif spec.kind == "boolean":
                if not isinstance(value, bool):
                    raise CapabilityError(f"{name}.{key} must be a boolean")
            else:
                raise CapabilityError(f"unsupported contract type {spec.kind!r}")
            if spec.choices and value not in spec.choices:
                raise CapabilityError(f"{name}.{key} must be one of {list(spec.choices)}")
            # Value-level rules are declared on the argument, not switched on the
            # capability name. A new capability that accepts a URL therefore gets
            # scheme validation by declaring format="url", and cannot silently
            # ship without it because somebody forgot to extend a name switch.
            if spec.format:
                _check_format(f"{name}.{key}", spec.format, value)
            clean[key] = value

        return clean


def project_evidence(projection: EvidenceProjection, result: dict[str, Any], *,
                     fallback_source: str,
                     external_sources: list[str] | None = None) -> list[dict[str, Any]]:
    """Turn one capability result into evidence records, generically.

    This is the whole projector. It reads a declaration and a result; it never
    asks which capability produced them. Adding a capability means adding an
    `EvidenceProjection` beside it, not a branch here.
    """
    external = external_sources or []

    def resolve_sources() -> list[str]:
        found: list[str] = []
        for key in projection.sources:
            value = result.get(key)
            if isinstance(value, str) and value:
                found.append(value)
            elif isinstance(value, list):
                found.extend(item for item in value if isinstance(item, str) and item)
        if not found and projection.source_template:
            try:
                found.append(projection.source_template.format(**result))
            except (KeyError, IndexError):
                pass
        if not found and projection.external_sources:
            found = list(external)
        return found or [fallback_source]

    records: list[dict[str, Any]] = []

    # 1. Ready-made evidence records pass straight through.
    if projection.records:
        values = result.get(projection.records)
        if isinstance(values, list):
            records.extend(item for item in values if isinstance(item, dict))
    if projection.record:
        value = result.get(projection.record)
        if isinstance(value, dict):
            records.append(value)

    # 2. Expand a list of sub-items, each becoming its own attributable record.
    if projection.items:
        values = result.get(projection.items)
        expanded = 0
        if isinstance(values, list):
            shared = resolve_sources()
            for item in values:
                if not isinstance(item, dict):
                    continue
                text = ": ".join(str(item.get(key, "")) for key in projection.item_text).strip(": ").strip()
                if not text:
                    continue
                source = item.get(projection.item_source) if projection.item_source else None
                records.append({"text": text[:12_000],
                                "sources": [source] if isinstance(source, str) and source else shared,
                                "kind": projection.item_kind or projection.kind})
                expanded += 1
        if expanded == 0 and projection.summary:
            try:
                summary = projection.summary.format(**result)
            except (KeyError, IndexError):
                summary = projection.summary
            records.append({"text": summary, "sources": resolve_sources(),
                            "kind": projection.summary_kind or projection.kind})

    # 3. A main text body, joined from a list or taken from one field.
    body = ""
    if projection.join:
        values = result.get(projection.join)
        if isinstance(values, list) and values:
            body = projection.prefix + ", ".join(str(item) for item in values)
    elif projection.text:
        value = result.get(projection.text)
        if isinstance(value, str) and value.strip():
            body = projection.prefix + value
    if body:
        records.append({"text": body[:12_000], "sources": resolve_sources(), "kind": projection.kind})

    return records


def generic_evidence(result: dict[str, Any], *, skill: str, fallback_source: str,
                     drop: tuple[str, ...] = ()) -> dict[str, Any]:
    """The projection for a capability that declared none: never silently lost."""
    public = {key: value for key, value in result.items() if key not in drop}
    sources = [value for key, value in public.items()
               if key in {"uri", "url", "endpoint", "source_uri", "path"} and isinstance(value, str)]
    import json as _json
    return {"text": _json.dumps(public, ensure_ascii=False, default=str)[:12_000],
            "sources": sources or [fallback_source], "kind": f"capability:{skill}"}


def default_registry() -> CapabilityRegistry:
    def string(description: str, **kwargs: Any) -> Argument:
        return Argument("string", description, **kwargs)

    def integer(description: str, **kwargs: Any) -> Argument:
        return Argument("integer", description, **kwargs)

    def boolean(description: str, **kwargs: Any) -> Argument:
        return Argument("boolean", description, **kwargs)

    # Shared projections, so several capabilities that genuinely produce the
    # same shape of evidence say so once.
    role_output = EvidenceProjection(kind="role_output", text="text", external_sources=True)

    return CapabilityRegistry([
        Capability("load_skill",
                   "Load the full instructions for one skill named in the run's skill listing. "
                   "Call this BEFORE planning work the skill covers, so its guidance shapes the "
                   "nodes you add rather than arriving after they have run. Pass 'reference' to "
                   "fetch one of the extra files the loaded skill names.",
                   {"name": string("The skill name, exactly as it appears in the skill listing.", maximum=64),
                    "reference": string("Optional. A reference file named by the skill body, e.g. 'catalog.md'.",
                                        maximum=128, required=False)}),
        Capability("memory_recall", "Retrieve authorised facts, prior episodes, playbooks, and indexed document chunks relevant to a query.",
                   {"query": string("What must be recalled from durable scoped memory.", maximum=20_000)},
                   families=("evidence",),
                   evidence=EvidenceProjection(records="hits")),
        Capability("remember_explicit_fact", "Persist a fact only when the user explicitly asked to remember or correct it.",
                   {"text": string("The minimal fact to preserve, without conversational filler.", maximum=20_000)},
                   side_effect=True,
                   evidence=EvidenceProjection(record="fact", prepend=True)),
        Capability("web_search", "Search the public web and return titles, URLs, and snippets. Use fetch_url later when page text is needed.",
                   {"query": string("A complete standalone search query.", maximum=2_000),
                    "max_results": integer("Number of results.", required=False, default=3, minimum=1, maximum=5)},
                   families=("evidence",),
                   evidence=EvidenceProjection(items="hits", item_text=("title", "snippet"),
                                               item_source="url", item_kind="search_result")),
        Capability("fetch_url", "Read one concrete HTTP(S) URL discovered in the request or a previous outcome.",
                   {"url": string("Absolute HTTP(S) URL.", maximum=4_000, format="url")},
                   families=("evidence",),
                   evidence=EvidenceProjection(kind="web_page", text="text", sources=("url",))),
        Capability("researcher", "A bounded specialist agent: search, read the returned pages, and synthesize supported claims with URLs. Launch several together for genuinely independent questions; make queries favor primary sources.",
                   {"query": string("A precise, standalone research question containing its subject and requested evidence.", maximum=4_000),
                    "max_results": integer("Number of search results.", required=False, default=3, minimum=1, maximum=5),
                    "subject": string("Short label for attribution.", required=False, maximum=200)}, role="researcher",
                   families=("evidence",),
                   evidence=EvidenceProjection(kind="role_output", text="text", external_sources=True,
                                               items="hits", item_text=("title", "snippet"),
                                               item_source="url", item_kind="research")),
        Capability("read_file", "Read a UTF-8 file inside the configured sandbox. Paths are relative to the sandbox.",
                   {"path": string("Sandbox-relative file path.", maximum=2_000)},
                   families=("evidence",),
                   evidence=EvidenceProjection(kind="local_file", text="text",
                                               source_template="file://{path}")),
        Capability("write_file", "Write a UTF-8 text artifact inside the configured sandbox, then return its path and SHA-256 digest. Use only when the user explicitly requests a file or a repair.",
                   {"path": string("Sandbox-relative destination path.", maximum=2_000),
                    "content": string("Complete text to write.", maximum=60_000),
                    "overwrite": boolean("Whether an existing file may be replaced.", required=False, default=False)},
                   side_effect=True),
        Capability("copy_code_file",
                   "Duplicate a file inside the workspace byte for byte, without reading it. "
                   "Use this to work from a large base file: create_file cannot reproduce what "
                   "it has not read, and the command runner has no copy program.",
                   {"source": string("Workspace-relative path of the file to copy.", maximum=2_000),
                    "destination": string("Workspace-relative path to write.", maximum=2_000),
                    "overwrite": boolean("Whether an existing destination may be replaced.",
                                         required=False, default=False)},
                   side_effect=True, families=("coding",)),
        Capability("copy_file", "Copy one sandbox file byte-for-byte to another sandbox path and verify the source and destination digests. Prefer this over regenerating content when exact preservation is requested.",
                   {"source": string("Existing sandbox-relative source path.", maximum=2_000),
                    "destination": string("Sandbox-relative destination path.", maximum=2_000),
                    "overwrite": boolean("Whether an existing destination may be replaced.", required=False, default=False)},
                   side_effect=True),
        Capability("file_sha256", "Compute the SHA-256 digest and byte size of one sandbox file for deterministic artifact verification.",
                   {"path": string("Sandbox-relative file path.", maximum=2_000)}),
        Capability("verify_artifact", "Read and SHA-256 verify one file URI created by this run's artifact-producing capabilities.",
                   {"uri": string("A file:// URI returned by a completed capability.", maximum=4_000)}),
        Capability("calculate", "Evaluate a bounded arithmetic expression deterministically. Supports numbers, arithmetic, comparisons, and min/max/sum/round/abs.",
                   {"expression": string("Standalone arithmetic expression, with no assignments or imports.", maximum=2_000)}),
        Capability("query_csv", "Load one or more sandbox CSV files into an in-memory database and run one read-only SELECT query. Use for joins, grouping, filtering, and multi-row arithmetic instead of many scalar calculations.",
                   {"files": Argument("array", "Sandbox-relative CSV paths; each filename stem becomes its SQL table name.",
                                      minimum=1, maximum=10, item_kind="string"),
                    "sql": string("One read-only SQLite SELECT or WITH query.", maximum=10_000)}),
        Capability("current_datetime", "Return the current date and time in an IANA timezone. Use when relative dates or the meaning of current/today must be resolved.",
                   {"timezone": string("IANA timezone such as UTC or Asia/Kolkata.", required=False, default="UTC", maximum=100)}),
        Capability("date_shift", "Add or subtract an exact number of calendar days from an ISO date.",
                   {"date": string("ISO-8601 date (YYYY-MM-DD).", maximum=10),
                    "days": integer("Signed number of calendar days.", minimum=-10000, maximum=10000)}),
        Capability("list_directory", "List immediate subdirectories and files with one suffix inside a sandbox directory; use returned concrete paths in later tasks.",
                   {"path": string("Sandbox-relative directory.", maximum=2_000),
                    "suffix": string("File suffix including the leading dot.", required=False, default=".md", maximum=32)}),
        Capability("index_file", "Semantically chunk, embed, and atomically index one sandbox file into scoped memory.",
                   {"path": string("Sandbox-relative file path.", maximum=2_000)}, side_effect=True,
                   families=("evidence",),
                   evidence=EvidenceProjection(kind="indexed_chunk", items="manifest", item_text=("text",),
                                               sources=("source_uri",), summary_kind="index_report",
                                               summary="Indexed {chunks} semantic chunks from this document.")),
        Capability("create_calendar_events", "Create local iCalendar artifacts for explicit ISO dates requested by the user.",
                   {"title": string("Human-readable event title.", maximum=300),
                    "dates": Argument("array", "ISO-8601 dates (YYYY-MM-DD).", minimum=1, maximum=20, item_kind="string")},
                   side_effect=True,
                   evidence=EvidenceProjection(kind="calendar_artifact", join="artifacts",
                                               prefix="Calendar events created: ", sources=("artifacts",))),
        Capability("list_channels", "Ask GLC for the currently installed channel adapters and their connection state. The list is discovered at runtime, never encoded in the planner.",
                   {}),
        Capability("send_channel_message", "Send one text message through an installed GLC channel. Use only when the request or an authorised subscription explicitly identifies the channel and recipient.",
                   {"channel": string("Channel name returned by list_channels or supplied by authorised context.", maximum=100),
                    "recipient_id": string("Provider-native recipient, conversation, address, or account identifier.", maximum=2_000),
                    "text": string("Message to send.", maximum=20_000),
                    "thread_id": string("Existing provider thread identifier when replying in context.", required=False, maximum=2_000),
                    "voice_audio_ref": string("Existing audio artifact reference for a voice-capable channel.", required=False, maximum=4_000)},
                   side_effect=True),
        Capability("a2a_delegate", "Discover a remote A2A agent, verify its Agent Card under local trust policy, and delegate one task.",
                   {"agent_url": string("Base URL of the remote agent.", maximum=4_000, format="url"),
                    "message": string("Self-contained delegated task.", maximum=20_000)}, role="delegate",
                   evidence=role_output),
        Capability("launch_job", "Launch any program or agent that implements the asynchronous job contract. It returns immediately with a durable handle; a later signed completion event resumes this graph.",
                   {"endpoint": string("HTTP(S) endpoint that accepts the generic job envelope.", maximum=4_000, format="url"),
                    "task": string("Self-contained work request, with desired output contract.", maximum=20_000)},
                   role="delegate", side_effect=True),
        Capability("request_approval", "Pause this run and ask a human one concrete question before an irreversible or ambiguous action. A later approval event resumes from the response.",
                   {"question": string("Decision the human must make, including relevant consequences.", maximum=4_000),
                    "choices": Argument("array", "Short allowed responses.", required=False,
                                        maximum=10, item_kind="string")},
                   role="approval", side_effect=True, families=("human_gate",)),
        Capability("retriever", "Retrieve scoped memory and have a specialist summarize only the retrieved evidence.",
                   {"query": string("A precise retrieval question.", maximum=20_000)}, role="retriever",
                   evidence=role_output),
        Capability("distiller", "Synthesize completed upstream outcomes into the information needed by the goal.",
                   {"query": string("What to synthesize and the required output shape.", maximum=20_000)}, role="distiller",
                   families=("synthesis", "generic_role"), evidence=role_output),
        Capability("summariser", "Condense completed upstream outcomes without introducing unsupported claims.",
                   {"query": string("What to summarize and desired emphasis.", maximum=20_000)}, role="summariser",
                   families=("generic_role",), evidence=role_output),
        Capability("coder_validator", "Check completed upstream output for structural, numerical, or comparison errors.",
                   {"query": string("Explicit validation criteria.", maximum=20_000)}, role="coder_validator",
                   families=("generic_role",), evidence=role_output,
                   role_rule=("Validate that every compared item uses the same definition and a comparable basis, "
                              "and that each metric a ranking depends on is explicitly present. Reject a comparative "
                              "conclusion when those conditions are not met; do not fill missing values. ")),
        Capability("content", "Produce structured domain-neutral content for a UI from the goal and completed upstream outcomes.",
                   {"query": string("UI content goal.", maximum=20_000)}, role="content",
                   families=("synthesis",)),
        Capability("compose_surface", "Compose and validate an A2UI surface from completed upstream outcomes.",
                   {"query": string("Interface goal and important presentation constraints.", maximum=20_000)},
                   role="ui_composer", terminal_for=("ui",)),
        # ---- the coding surface (Session 17) --------------------------------
        # These are the first capabilities whose output is executed rather than
        # read. Every bound they need is declared here or enforced in
        # sourcecode/coding/, never asked for in a prompt.
        Capability("read_code", "Read part of a file in the workspace. Ranged by default: ask for the lines you need, not the whole file. Reading is what earns the right to edit it.",
                   {"path": string("Workspace-relative file path.", maximum=2_000),
                    "offset": integer("First line to read, 1-based.", required=False, default=1, minimum=1, maximum=1_000_000),
                    "limit": integer("How many lines to read.", required=False, default=200, minimum=1, maximum=2_000)},
                   families=("evidence", "coding", "rerunnable"),
                   evidence=EvidenceProjection(kind="source_code", text="text",
                                               source_template="file://{path}")),
        Capability("edit_code", "Replace one exact, unique string in a file you have already read. Include enough surrounding text that it names one place. This is how you change code: never rewrite a whole file you have not read.",
                   {"path": string("Workspace-relative file path.", maximum=2_000),
                    "old_string": string("Exact text to replace, including indentation.", maximum=20_000),
                    "new_string": string("Replacement text.", maximum=20_000),
                    "replace_all": boolean("Replace every occurrence. Only for renames.", required=False, default=False)},
                   side_effect=True, families=("coding",),
                   evidence=EvidenceProjection(kind="code_edit", text="summary",
                                               source_template="file://{path}")),
        Capability("create_file", "Create a new file in the workspace. Refuses to clobber an existing file unless you have read it and say so.",
                   {"path": string("Workspace-relative destination.", maximum=2_000),
                    "content": string("Complete file contents.", maximum=60_000),
                    "overwrite": boolean("Replace an existing file.", required=False, default=False)},
                   side_effect=True, families=("coding",)),
        Capability("glob_files", "List workspace files whose path matches a pattern. Use this to scope before searching.",
                   {"pattern": string("Glob such as *.py or sourcecode/**.", maximum=500)},
                   families=("coding", "rerunnable")),
        Capability("grep_code", "Search file contents for a regular expression. Returns file and line so you can then read exactly that part.",
                   {"pattern": string("Regular expression.", maximum=1_000),
                    "path_glob": string("Restrict to matching paths.", required=False, default="*", maximum=500),
                    "ignore_case": boolean("Case-insensitive.", required=False, default=False)},
                   families=("evidence", "coding", "rerunnable")),
        Capability("run_command", "Run one allowed command inside the workspace, usually the tests. No shell, no network by default, killed on a timeout. This is the judge: it decides whether the change worked.",
                   {"command": string("One command, for example: python -m pytest -q", maximum=2_000),
                    "timeout": integer("Seconds before it is killed.", required=False, default=120, minimum=1, maximum=600)},
                   side_effect=True, families=("coding", "verify", "rerunnable")),
        Capability("git_diff", "Show everything changed in the workspace so far, as a patch a human can read.",
                   {}, families=("coding", "rerunnable"),
                   evidence=EvidenceProjection(kind="patch", text="diff")),
        Capability("git_reset", "Throw away every change in the workspace. This is what rejecting an attempt looks like.",
                   {}, side_effect=True, families=("coding",)),

        Capability("validate_work", "Hand the work to a separate validation agent that starts fresh, is asked to find what is broken rather than confirm it is fine, and cannot edit anything. Use this before claiming a job is done. It returns findings; act on them.",
                   {"requirement": string("What the work was supposed to achieve, in full. The validator sees this and the files, and nothing else.", maximum=8_000),
                    "paths": Argument("array", "Files it should examine.", required=False, maximum=20, item_kind="string")},
                   side_effect=True, families=("coding", "verify", "rerunnable"),
                   evidence=EvidenceProjection(kind="validation", text="summary")),

        Capability("answer_with_evidence", "Produce the final grounded text answer from all completed graph outcomes. Use directly for tasks requiring no tools.",
                   {"query": string("The user's goal, including the requested answer format.", maximum=20_000)},
                   role="answer", terminal_for=("text",)),

        # ---- campaign & subscriber management (MCP) -------------------------
        # These call a remote, token-authenticated MCP server exposing generic
        # CRUD/transition tools. `fields`/`filters`/`criteria` carry a JSON
        # object as a string because the argument contract has no object kind;
        # workers in sourcecode/workers/campaign.py parse and forward it
        # unchanged. Every capability here is bound to exactly one MCP tool
        # name in runtime.py, never chosen by branching on the capability name.
        Capability("list_email_campaigns", "List email campaigns, optionally filtered by status or search text.",
                   {"status": string("Campaign status filter, e.g. draft, scheduled, sending, paused, cancelled, sent.",
                                     required=False, maximum=32),
                    "search": string("Free-text search over campaign name/subject.", required=False, maximum=200),
                    "limit": integer("Maximum records to return.", required=False, default=20, minimum=1, maximum=200)},
                   families=("campaign", "evidence")),
        Capability("get_email_campaign", "Get one email campaign by ID.",
                   {"id": string("EmailCampaign record ID.", maximum=100)}, families=("campaign",)),
        Capability("create_email_campaign", "Create a new draft email campaign.",
                   {"fields": string("JSON object of campaign fields, e.g. name, subject, body, list_id, audience_id.",
                                     maximum=8_000)},
                   side_effect=True, families=("campaign",)),
        Capability("update_email_campaign", "Update an existing email campaign.",
                   {"id": string("EmailCampaign record ID.", maximum=100),
                    "fields": string("JSON object of fields to change.", maximum=8_000)},
                   side_effect=True, families=("campaign",)),
        Capability("delete_email_campaign", "Delete an email campaign by ID.",
                   {"id": string("EmailCampaign record ID.", maximum=100)}, side_effect=True, families=("campaign",)),
        Capability("schedule_email_campaign", "Transition a draft email campaign to scheduled.",
                   {"id": string("EmailCampaign record ID.", maximum=100),
                    "fields": string("Optional JSON object, e.g. {\"scheduled_at\": \"...\"}.",
                                     required=False, maximum=2_000)},
                   side_effect=True, families=("campaign",)),
        Capability("cancel_scheduled_email_campaign", "Transition a scheduled email campaign to cancelled.",
                   {"id": string("EmailCampaign record ID.", maximum=100)}, side_effect=True, families=("campaign",)),
        Capability("pause_email_campaign", "Transition a sending email campaign to paused.",
                   {"id": string("EmailCampaign record ID.", maximum=100)}, side_effect=True, families=("campaign",)),
        Capability("cancel_paused_email_campaign", "Transition a paused email campaign to cancelled.",
                   {"id": string("EmailCampaign record ID.", maximum=100)}, side_effect=True, families=("campaign",)),
        Capability("save_email_campaign_draft", "Save an email campaign back to the draft state.",
                   {"id": string("EmailCampaign record ID.", maximum=100),
                    "fields": string("Optional JSON object of fields to change.", required=False, maximum=8_000)},
                   side_effect=True, families=("campaign",)),
        Capability("list_campaign_audiences", "List saved campaign audience segments.",
                   {"search": string("Free-text search over audience name.", required=False, maximum=200),
                    "limit": integer("Maximum records to return.", required=False, default=20, minimum=1, maximum=200)},
                   families=("campaign", "evidence")),
        Capability("get_campaign_audience", "Get one campaign audience segment by ID.",
                   {"id": string("CampaignAudience record ID.", maximum=100)}, families=("campaign",)),
        Capability("preview_campaign_audience",
                   "Preview which CRM contacts a segment definition matches, without saving it. "
                   "Use this to build a segment such as 'customers who bought last year' before creating a campaign.",
                   {"criteria": string("JSON object of segment criteria understood by the CRM audience builder.",
                                       maximum=8_000)},
                   families=("campaign", "evidence")),
        Capability("list_crm_campaign_audiences", "List CRM campaign audiences via the CRM endpoint (alternate to list_campaign_audiences).",
                   {"filters": string("Optional JSON object of query filters.", required=False, maximum=2_000)},
                   families=("campaign", "evidence")),
        Capability("list_campaign_links", "List tracked links belonging to a campaign.",
                   {"campaign_id": string("Restrict to one EmailCampaign ID.", required=False, maximum=100),
                    "limit": integer("Maximum records to return.", required=False, default=20, minimum=1, maximum=200)},
                   families=("campaign", "evidence")),
        Capability("get_campaign_link", "Get one campaign link by ID.",
                   {"id": string("CampaignLink record ID.", maximum=100)}, families=("campaign",)),
        Capability("list_campaign_recipients",
                   "List a campaign's recipients and their delivery/open/click/unsubscribe status.",
                   {"campaign_id": string("Restrict to one EmailCampaign ID.", required=False, maximum=100),
                    "status": string("Recipient status filter, e.g. sent, opened, clicked, bounced, unsubscribed.",
                                     required=False, maximum=32),
                    "limit": integer("Maximum records to return.", required=False, default=20, minimum=1, maximum=200)},
                   families=("campaign", "evidence")),
        Capability("get_campaign_recipient", "Get one campaign recipient by ID.",
                   {"id": string("CampaignRecipient record ID.", maximum=100)}, families=("campaign",)),
        Capability("list_subscribers",
                   "List mailing-list subscribers, optionally filtered by status (e.g. unsubscribed) or list.",
                   {"status": string("Subscriber status filter: active, unsubscribed, bounced, complained, or pending.",
                                     required=False, choices=("active", "unsubscribed", "bounced", "complained", "pending")),
                    "list_id": string("Restrict to one SubscriberList ID.", required=False, maximum=100),
                    "search": string("Free-text search over name/email.", required=False, maximum=200),
                    "limit": integer("Maximum records to return.", required=False, default=20, minimum=1, maximum=1_000)},
                   families=("campaign", "evidence")),
        Capability("get_subscriber", "Get one subscriber by ID.",
                   {"id": string("Subscriber record ID.", maximum=100)}, families=("campaign",)),
        Capability("create_subscriber", "Add a new subscriber to a mailing list.",
                   {"fields": string("JSON object of subscriber fields, e.g. email, name, list_id.", maximum=4_000)},
                   side_effect=True, families=("campaign",)),
        Capability("update_subscriber", "Update an existing subscriber, e.g. to mark them unsubscribed.",
                   {"id": string("Subscriber record ID.", maximum=100),
                    "fields": string("JSON object of fields to change.", maximum=4_000)},
                   side_effect=True, families=("campaign",)),
        Capability("delete_subscriber", "Remove a subscriber by ID.",
                   {"id": string("Subscriber record ID.", maximum=100)}, side_effect=True, families=("campaign",)),
        Capability("list_subscriber_lists", "List mailing lists.",
                   {"search": string("Free-text search over list name.", required=False, maximum=200),
                    "limit": integer("Maximum records to return.", required=False, default=20, minimum=1, maximum=200)},
                   families=("campaign", "evidence")),
        Capability("get_subscriber_list", "Get one mailing list by ID.",
                   {"id": string("SubscriberList record ID.", maximum=100)}, families=("campaign",)),
        Capability("create_subscriber_list", "Create a new mailing list.",
                   {"fields": string("JSON object of list fields, e.g. name, description.", maximum=2_000)},
                   side_effect=True, families=("campaign",)),
        Capability("update_subscriber_list", "Update an existing mailing list.",
                   {"id": string("SubscriberList record ID.", maximum=100),
                    "fields": string("JSON object of fields to change.", maximum=2_000)},
                   side_effect=True, families=("campaign",)),
        Capability("list_public_subscriber_lists", "List the mailing lists exposed on the public signup endpoint.",
                   {}, families=("campaign", "evidence")),
    ])
