"""Import every message-family module for its registration side effects.

Each of snapshot_codec/event_codec/game_messages/lobby_messages calls registry.register()
once per message it defines, at import time. This file's only job is guaranteeing that
has already happened by the time anything calls registry.message_to_payload/
message_from_payload, no matter which submodule a caller happens to import first.
"""

from protocol import event_codec, game_messages, lobby_messages, snapshot_codec  # noqa: F401
