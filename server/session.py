"""Step 3 of the client/server migration (docs/kf-chess-architecture-plan.md):
a single game/room, wrapping GameComponents. Move/jump handling and
ownership enforcement land in a later step - this only tracks seats and
ticks the engine."""

from app.game_builder import build_game

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
