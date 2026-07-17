"""Channel adapter layer.

Public surface:
  - envelope.ChannelMessage / ChannelReply / Attachment / TrustLevel
  - base.ChannelAdapter (ABC)
  - registry.discover() / registry.get(name)
"""

from glc.channels.base import ChannelAdapter
from glc.channels.envelope import (
    Attachment,
    ChannelMessage,
    ChannelReply,
    TrustLevel,
)

__all__ = [
    "Attachment",
    "ChannelAdapter",
    "ChannelMessage",
    "ChannelReply",
    "TrustLevel",
]
