"""The bootstrap authoring tools (`toprope-author`, the authoring MCP). Until the switch-over
(ADR-0037) they wrap the kernel's workspace (`toprope.workspace`); after it they are removed
and the generated Authoring domain is the tool."""

from ..workspace import *  # noqa: F401,F403
from ..workspace import CONFIG, AuthoringError, Workspace  # noqa: F401
