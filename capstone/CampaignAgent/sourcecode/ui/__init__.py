"""The generative-UI layer, carried forward from Session 14.

Turns a graph outcome into a declarative A2UI surface, streams the durable
event journal as AG-UI events, and carries user actions back as validated
events. The runtime and this UI ship as one service; the UI reads the runtime's
graph in-process and executes none of the agent's text.

Session 15 adds a second consumer of the same journal — ``sourcecode.telemetry``
turns it into OpenTelemetry spans. One journal, three consumers: graph replay,
UI stream, trace export.
"""

__version__ = "0.1.0"
