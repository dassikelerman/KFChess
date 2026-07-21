import logging

from app.game_builder import build_game
from events.game_events import GameOverEvent, IllegalActionEvent
from events.serialization import JumpIntent, MoveIntent, from_dict
from model.piece import PieceColor

_ROLES_BY_INDEX = ("white", "black")
SPECTATOR_ROLE = "spectator"
_COLOR_BY_ROLE = {"white": PieceColor.WHITE, "black": PieceColor.BLACK}
_ROLE_BY_COLOR = {PieceColor.WHITE: "white", PieceColor.BLACK: "black"}

logger = logging.getLogger(__name__)


class Session:
    def __init__(self, board_text, user_store=None):
        self.components = build_game(board_text)
        self.network_publisher = None
        self._roles = {}
        self._usernames = {}
        self._user_store = user_store
        self._ratings_updated = False
        if user_store is not None:
            self.components.dispatcher.subscribe(GameOverEvent, self._on_game_over)

    def record_login(self, connection, username):
        self._usernames[connection] = username
        logger.info("connection logged in as %r", username)

    def disconnect(self, connection):
        self._usernames.pop(connection, None)
        self._roles.pop(connection, None)

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
        return _COLOR_BY_ROLE.get(role) == color

    def _reject(self, connection, piece, destination):
        event = IllegalActionEvent(
            piece_id=piece.id if piece is not None else None,
            destination=destination, at_ms=self.components.engine.clock,
        )
        self.network_publisher.unicast(connection, event)

    def _on_game_over(self, event):
        if self._ratings_updated:
            return
        self._ratings_updated = True

        white_username = self._usernames.get(self._connection_for_role("white"))
        black_username = self._usernames.get(self._connection_for_role("black"))
        if white_username is None or black_username is None:
            logger.warning(
                "game over but missing a username for a seat (white=%r, black=%r) - skipping rating update",
                white_username, black_username,
            )
            return

        winner_color = _ROLE_BY_COLOR.get(event.winner_color)
        self._user_store.update_ratings(white_username, black_username, winner_color)

    def _connection_for_role(self, role):
        for connection, assigned_role in self._roles.items():
            if assigned_role == role:
                return connection
        return None
