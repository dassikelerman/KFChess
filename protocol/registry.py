"""The message registry: maps each wire type tag to its class and codec functions.

Every message family (protocol/snapshot_codec.py, event_codec.py, game_messages.py,
lobby_messages.py) calls register() once per message it defines, instead of listing
every message in one giant central table. This module only owns the lookup itself and
the small public API everything else uses to cross the network boundary:
message_to_payload/message_from_payload work with plain dicts (for callers that still
need to add a field, like snapshot_codec's clock_ms, before sending); encode_json_message
and decode_json_message are the one-step versions for a single self-contained message.
Both directions fail loudly and specifically: UnregisteredMessageClassError names the
class that needs a register() call; UnknownMessageTypeError names the bad "type" tag (or
non-dict payload) and lists every type tag that *is* known.
"""

import json

_entries_by_type_name = {}
_type_name_by_class = {}


class UnknownMessageTypeError(Exception):
    """message_from_payload got a "type" tag with no registered codec."""


class UnregisteredMessageClassError(Exception):
    """message_to_payload got an object whose class was never passed to register()."""


def register(type_name, cls, fields_of, kwargs_from):
    _entries_by_type_name[type_name] = (cls, fields_of, kwargs_from)
    _type_name_by_class[cls] = type_name


def message_to_payload(message):
    message_class = type(message)
    type_name = _type_name_by_class.get(message_class)
    if type_name is None:
        raise UnregisteredMessageClassError(
            f"{message_class.__module__}.{message_class.__qualname__} is not registered - "
            "add a register(...) call for it in its module (see snapshot_codec.py/event_codec.py/"
            "game_messages.py/lobby_messages.py for examples)"
        )
    _, fields_of, _ = _entries_by_type_name[type_name]
    payload = fields_of(message)
    payload["type"] = type_name
    return payload


def message_from_payload(payload):
    if not isinstance(payload, dict):
        raise UnknownMessageTypeError(f"expected a JSON object, got {type(payload).__name__}: {payload!r}")
    type_name = payload.get("type")
    entry = _entries_by_type_name.get(type_name)
    if entry is None:
        raise UnknownMessageTypeError(
            f"no codec registered for message type {type_name!r} - "
            f"known types: {sorted(_entries_by_type_name)}"
        )
    cls, _, kwargs_from = entry
    return cls(**kwargs_from(payload))


def encode_json_message(message):
    return json.dumps(message_to_payload(message))


def decode_json_message(raw):
    return message_from_payload(json.loads(raw))
