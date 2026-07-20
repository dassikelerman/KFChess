"""Step 5 of the client/server migration (docs/kf-chess-architecture-plan.md):
a single game/room, wrapping GameComponents. Handles client intents now;
ownership enforcement (rejecting a move/jump sent by the wrong color)
is still not implemented - see the TODO on handle_client_message."""

from app.game_builder import build_game
from events.serialization import JumpIntent, MoveIntent, from_dict

_ROLES_BY_INDEX = ("white", "black")
SPECTATOR_ROLE = "spectator"


class Session:
    def __init__(self, board_text):
        self.components = build_game(board_text)
        self._roles = {}  # connection -> role, in assignment order

    def assign_role(self, connection):
        if connection not in self._roles:
            index = len(self._roles)
            role = _ROLES_BY_INDEX[index] if index < len(_ROLES_BY_INDEX) else SPECTATOR_ROLE
            self._roles[connection] = role
        return self._roles[connection]

    def tick(self, dt_ms):
        self.components.engine.wait(dt_ms)

    def handle_client_message(self, connection, message_dict):
        # TODO(Step 6): check self._roles[connection] against the piece's
        # own color before calling request_move/request_jump below, and
        # reject (publish IllegalActionEvent, unicast to `connection`)
        # if they don't match - not implemented yet, every connection's
        # intent is routed straight to the engine regardless of role.
        intent = from_dict(message_dict)
        engine = self.components.engine
        if isinstance(intent, MoveIntent):
            engine.request_move(intent.source, intent.destination)
        elif isinstance(intent, JumpIntent):
            engine.request_jump(intent.position)
