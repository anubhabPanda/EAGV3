"""Setup utilities for the Microsoft Teams adapter.

These are operator-facing tools that run outside the agent runtime:

- ``emulator_runner`` — local aiohttp stub server (``POST /api/messages``)
  for driving the adapter with curl or the Bot Framework Emulator.
  Run via ``python -m glc.channels.catalogue.teams.setup.emulator_runner``.

- ``trust_setup`` — CLI for pairing/unpairing trusted Teams users
  against the ``glc.security.pairing`` store that the adapter
  consults at runtime via ``classify("teams", ...)``.
"""

from __future__ import annotations
