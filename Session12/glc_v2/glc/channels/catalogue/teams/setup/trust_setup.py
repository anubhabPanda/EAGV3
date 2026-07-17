"""CLI for managing Teams pairings in the GLC pairing store.

The Teams adapter (``glc/channels/catalogue/teams/adapter.py``) classifies
inbound senders by calling ``classify("teams", from.id)`` against the
shared pairing store. This CLI is how an operator populates that store
without going through the WebUI pairing flow.

The pairing store is sqlite-backed at ``~/.glc/pairings.sqlite`` by
default; override with ``GLC_PAIRING_DB``. All operations here are
scoped to the ``teams`` channel.

Subcommands
-----------

``owner <user_id> [--handle NAME]``
    Pair a user as the installation owner directly. Equivalent to
    ``PairingStore.force_pair_owner``. Use this for the demo + tests
    where you want trust_level=owner_paired without going through the
    six-digit code dance.

``invite <user_id> [--handle NAME] [--trust user_paired]``
    Issue a six-digit pairing code. The operator (or the user) then
    runs ``confirm <code>`` to complete the pairing. Mirrors the
    WebUI flow.

``confirm <code>``
    Confirm a previously-issued pairing code.

``list``
    Print all current teams pairings as a table.

``revoke <user_id>``
    Remove a single pairing.

``revoke-all [--yes]``
    Remove every teams pairing. Requires ``--yes`` to actually delete.

Examples
--------

::

    python -m glc.channels.catalogue.teams.setup.trust_setup owner "29:42"
    python -m glc.channels.catalogue.teams.setup.trust_setup invite "29:99" --handle alice
    python -m glc.channels.catalogue.teams.setup.trust_setup confirm 042913
    python -m glc.channels.catalogue.teams.setup.trust_setup list
    python -m glc.channels.catalogue.teams.setup.trust_setup revoke "29:99"
    python -m glc.channels.catalogue.teams.setup.trust_setup revoke-all --yes

Note on Bot Framework user IDs
------------------------------

Teams ``from.id`` values arrive over the wire with prefixes — ``29:``
for users, ``28:`` for bots, ``8:orgid:`` for organisation-scoped
users. Store and pass them verbatim including the prefix; the
adapter's ``classify()`` call uses the full string for lookup.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from glc.security.pairing import PairingRecord, get_pairing_store

CHANNEL = "teams"


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _print_record(rec: PairingRecord) -> None:
    print(
        f"  {rec.channel_user_id:<24} {rec.trust_level:<14} handle={rec.user_handle or '-':<16} paired_at={_fmt_ts(rec.paired_at)}"
    )


def _filter_teams(pairings: list[PairingRecord]) -> list[PairingRecord]:
    return [p for p in pairings if p.channel == CHANNEL]


def cmd_owner(args: argparse.Namespace) -> int:
    """Pair a user as ``owner_paired`` directly."""
    store = get_pairing_store()
    rec = store.force_pair_owner(CHANNEL, args.user_id, user_handle=args.handle or "owner", _allow_in_process=True)
    print(f"Paired {rec.channel_user_id!r} as owner_paired on channel {CHANNEL!r}.")
    _print_record(rec)
    return 0


def cmd_invite(args: argparse.Namespace) -> int:
    """Issue a six-digit pairing code; operator runs ``confirm`` to finish."""
    if args.trust not in {"user_paired", "owner_paired"}:
        print(f"error: --trust must be 'user_paired' or 'owner_paired', got {args.trust!r}", file=sys.stderr)
        return 2
    store = get_pairing_store()
    code, expires_at = store.issue_code(
        CHANNEL,
        args.user_id,
        user_handle=args.handle or "",
        requested_trust_level=args.trust,
    )
    print(f"Pairing code for {args.user_id!r} on channel {CHANNEL!r}: {code}")
    print(f"  expires:       {_fmt_ts(expires_at)}")
    print(f"  trust_level:   {args.trust}")
    print()
    print(f"Confirm with:  python -m glc.channels.catalogue.teams.setup.trust_setup confirm {code}")
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    """Confirm a pairing code issued by ``invite``."""
    store = get_pairing_store()
    rec = store.confirm_code(args.code)
    if rec is None:
        print(f"error: code {args.code!r} not found or expired", file=sys.stderr)
        return 1
    if rec.channel != CHANNEL:
        print(f"error: code is for channel {rec.channel!r}, not {CHANNEL!r}", file=sys.stderr)
        return 1
    print(f"Confirmed pairing for {rec.channel_user_id!r}.")
    _print_record(rec)
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    """List all teams pairings."""
    store = get_pairing_store()
    pairings = _filter_teams(store.all_pairings())
    if not pairings:
        print(f"No pairings on channel {CHANNEL!r}.")
        return 0
    print(f"Pairings on channel {CHANNEL!r} ({len(pairings)} total):")
    for rec in pairings:
        _print_record(rec)
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    """Remove a single pairing."""
    store = get_pairing_store()
    removed = store.revoke(CHANNEL, args.user_id)
    if not removed:
        print(f"No pairing found for {args.user_id!r} on channel {CHANNEL!r}.", file=sys.stderr)
        return 1
    print(f"Revoked pairing for {args.user_id!r} on channel {CHANNEL!r}.")
    return 0


def cmd_revoke_all(args: argparse.Namespace) -> int:
    """Remove every teams pairing (requires --yes)."""
    if not args.yes:
        print("error: refusing to delete without --yes (destructive operation)", file=sys.stderr)
        return 2
    store = get_pairing_store()
    pairings = _filter_teams(store.all_pairings())
    removed = 0
    for rec in pairings:
        if store.revoke(CHANNEL, rec.channel_user_id):
            removed += 1
    print(f"Revoked {removed} pairing(s) on channel {CHANNEL!r}.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trust_setup",
        description="Manage Microsoft Teams pairings in the GLC pairing store.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    p_owner = subparsers.add_parser("owner", help="pair a user as owner_paired (direct, no code)")
    p_owner.add_argument("user_id", help='Teams from.id value, e.g. "29:42"')
    p_owner.add_argument("--handle", help="optional display handle", default=None)
    p_owner.set_defaults(func=cmd_owner)

    p_invite = subparsers.add_parser("invite", help="issue a 6-digit pairing code")
    p_invite.add_argument("user_id", help='Teams from.id value, e.g. "29:42"')
    p_invite.add_argument("--handle", help="optional display handle", default=None)
    p_invite.add_argument(
        "--trust",
        choices=("user_paired", "owner_paired"),
        default="user_paired",
        help="requested trust level (default: user_paired)",
    )
    p_invite.set_defaults(func=cmd_invite)

    p_confirm = subparsers.add_parser("confirm", help="confirm a 6-digit pairing code")
    p_confirm.add_argument("code", help="the 6-digit code from `invite`")
    p_confirm.set_defaults(func=cmd_confirm)

    p_list = subparsers.add_parser("list", help="list all teams pairings")
    p_list.set_defaults(func=cmd_list)

    p_revoke = subparsers.add_parser("revoke", help="remove a single pairing")
    p_revoke.add_argument("user_id", help='Teams from.id value, e.g. "29:42"')
    p_revoke.set_defaults(func=cmd_revoke)

    p_revoke_all = subparsers.add_parser("revoke-all", help="remove every teams pairing")
    p_revoke_all.add_argument("--yes", action="store_true", help="confirm destructive action")
    p_revoke_all.set_defaults(func=cmd_revoke_all)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
