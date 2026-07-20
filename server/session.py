"""Step 7 of the client/server migration (docs/kf-chess-architecture-plan.md):
a single game/room, wrapping GameComponents, enforcing color ownership
on every client intent - with an explicit, off-by-default escape hatch
for a single dev connection to control both colors. network_publisher
is wired in by the caller after construction (see
server/ws_server.py::main - it in turn needs this Session's own
dispatcher to build) - handle_client_message uses it to unicast a
rejection straight back to whichever connection sent it, whether the
rejection came from the ownership check here or from GameEngine's own
ActionResult; never broadcast."""

from app.game_builder import build_game
from events.game_events import IllegalActionEvent
from events.serialization import JumpIntent, MoveIntent, from_dict
from model.piece import PieceColor

_ROLES_BY_INDEX = ("white", "black")
SPECTATOR_ROLE = "spectator"
_COLOR_BY_ROLE = {"white": PieceColor.WHITE, "black": PieceColor.BLACK}


class Session:
    def __init__(self, board_text, *, allow_single_client_both_colors=False):
        self.components = build_game(board_text)
        self.network_publisher = None  # wired in by the caller - see server/ws_server.py
        self._roles = {}  # connection -> role, in assignment order
        self._allow_single_client_both_colors = allow_single_client_both_colors

    def assign_role(self, connection):
        if connection not in self._roles:
            index = len(self._roles)
            role = _ROLES_BY_INDEX[index] if index < len(_ROLES_BY_INDEX) else SPECTATOR_ROLE
            self._roles[connection] = role
        return self._roles[connection]

    def tick(self, dt_ms):
        self.components.engine.wait(dt_ms)

    def handle_client_message(self, connection, message_dict):
        intent = from_dict(message_dict)
        if isinstance(intent, MoveIntent):
            self._handle_move(connection, intent)
        elif isinstance(intent, JumpIntent):
            self._handle_jump(connection, intent)

    def _handle_move(self, connection, intent):
        engine = self.components.engine
        piece = engine.piece_at(intent.source)
        if not self._owns(connection, piece):
            self._reject(connection, piece, intent.source)
            return

        result = engine.request_move(intent.source, intent.destination)
        if not result.is_accepted:
            self._reject(connection, piece, intent.destination)

    def _handle_jump(self, connection, intent):
        engine = self.components.engine
        piece = engine.piece_at(intent.position)
        if not self._owns(connection, piece):
            self._reject(connection, piece, intent.position)
            return

        result = engine.request_jump(intent.position)
        if not result.is_accepted:
            self._reject(connection, piece, intent.position)

    def _owns(self, connection, piece):
        if piece is None:
            return False
        return self._connection_owns_color(connection, piece.color)

    def _connection_owns_color(self, connection, color):
        role = self._roles.get(connection)
        if _COLOR_BY_ROLE.get(role) == color:
            return True
        # Dev-only escape hatch, off by default: lets one connection play
        # both sides without opening two windows. Assumes exactly one
        # real connection is ever attached this way - it isn't designed
        # to coexist correctly with a second real player joining at the
        # same time, and that's fine/expected for a dev-only flag.
        if self._allow_single_client_both_colors and role == "white" and color == PieceColor.BLACK:
            return True
        return False

    def _reject(self, connection, piece, destination):
        event = IllegalActionEvent(
            piece_id=piece.id if piece is not None else None,
            destination=destination, at_ms=self.components.engine.clock,
        )
        self.network_publisher.unicast(connection, event)
