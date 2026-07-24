"""GameSession: one game room's authoritative state - roles, moves, disconnects, rating.

Owns exactly one live GameEngine plus the bookkeeping a networked game needs on top of
it: which connection is white/black/spectator, the disconnect-countdown/reconnect
dance, and (once the game ends) handing the result to a RatingRepository. It knows
nothing about sockets or JSON - GameRoomRegistry builds it fully wired, and
NetworkPublisher turns its dispatcher events into wire messages.

handle_move/handle_jump take already-decoded MoveIntent/JumpIntent objects - the typed
message ConnectionLifecycle decoded off the wire, unchanged all the way from
ClientMessageRouter. Nothing in this file ever converts to or from a dict.

Disconnect countdowns are simulated time, not real time: tick(dt_ms) - the same call
that advances the engine's clock - is the only thing that ever advances a countdown.
There is no asyncio task or sleep here, so an idle room costs nothing and the whole
server can run off one shared loop (see GameRoomRegistry.tick / server/ws_server.py).
"""

import logging
from dataclasses import dataclass

import constants
from app.game_builder import build_game
from events.game_events import (
    GameOverEvent,
    IllegalActionEvent,
    PlayerDisconnectedEvent,
    PlayerReconnectedEvent,
)
from model.piece import PieceColor
from protocol.game_messages import JumpIntent, MoveIntent
from server.contracts import RatingRepository

# "role" (who a connection is: white/black/spectator) and PieceColor (which
# side a piece belongs to) are deliberately separate representations, not a
# duplication to unify - a spectator has a role but no color, so PieceColor
# has no member for it and shouldn't grow one just for this. These two dicts
# are the only translation between the two, kept narrow on purpose.
_ROLES_BY_INDEX = ("white", "black")
SPECTATOR_ROLE = "spectator"
_COLOR_BY_ROLE = {"white": PieceColor.WHITE, "black": PieceColor.BLACK}
_ROLE_BY_COLOR = {PieceColor.WHITE: "white", PieceColor.BLACK: "black"}

logger = logging.getLogger(__name__)


@dataclass
class DisconnectCountdown:
    remaining_ms: int
    last_published_second: int


class GameSession:
    def __init__(
        self, board_text, make_network_publisher,
        rating_store: RatingRepository | None = None,
        disconnect_countdown_seconds: int = constants.DISCONNECT_COUNTDOWN_SECONDS,
    ):
        self.components = build_game(board_text)
        self._network_publisher = make_network_publisher(self.components.dispatcher)
        self._rating_store = rating_store
        self._disconnect_countdown_ms = disconnect_countdown_seconds * 1000
        self._roles = {}
        self._usernames = {}
        self._ratings_updated = False
        self._countdowns_by_color = {}
        if rating_store is not None:
            self.components.dispatcher.subscribe(GameOverEvent, self._on_game_over)

    # -- roles and login ----------------------------------------------------

    def assign_role(self, connection):
        if connection not in self._roles:
            index = len(self._roles)
            role = _ROLES_BY_INDEX[index] if index < len(_ROLES_BY_INDEX) else SPECTATOR_ROLE
            self._roles[connection] = role
        return self._roles[connection]

    def record_login(self, connection, username):
        self._usernames[connection] = username
        logger.info("connection logged in as %r", username)

    # -- disconnect and reconnect --------------------------------------------

    def begin_disconnect_countdown(self, connection):
        role = self._roles.get(connection)
        if role not in _COLOR_BY_ROLE:
            return

        color = _COLOR_BY_ROLE[role]
        if color in self._countdowns_by_color:
            return
        countdown = DisconnectCountdown(remaining_ms=self._disconnect_countdown_ms, last_published_second=-1)
        self._countdowns_by_color[color] = countdown
        self._publish_countdown_if_changed(color, countdown)

    def reconnect(self, new_connection, username):
        old_connection = self._connection_for_username(username)
        if old_connection is None:
            return None

        color = _COLOR_BY_ROLE.get(self._roles.get(old_connection))
        if color not in self._countdowns_by_color:
            return None
        del self._countdowns_by_color[color]

        role = self._roles.pop(old_connection)
        self._usernames.pop(old_connection)
        self._roles[new_connection] = role
        self._usernames[new_connection] = username
        self.components.dispatcher.publish(PlayerReconnectedEvent(color=color))
        return role

    # -- tick and engine actions ---------------------------------------------

    def tick(self, dt_ms):
        self.components.engine.wait(dt_ms)
        if self.components.engine.game_over:
            self._countdowns_by_color.clear()
            return
        for color in list(self._countdowns_by_color):
            self._advance_countdown(color, dt_ms)

    def _advance_countdown(self, color, dt_ms):
        countdown = self._countdowns_by_color[color]
        countdown.remaining_ms = max(0, countdown.remaining_ms - dt_ms)
        self._publish_countdown_if_changed(color, countdown)
        if countdown.remaining_ms <= 0:
            del self._countdowns_by_color[color]
            self.components.engine.resign(color)

    def _publish_countdown_if_changed(self, color, countdown):
        displayed_second = -(-countdown.remaining_ms // 1000)  # ceil(remaining_ms / 1000)
        if displayed_second == countdown.last_published_second:
            return
        countdown.last_published_second = displayed_second
        self.components.dispatcher.publish(PlayerDisconnectedEvent(color=color, seconds_remaining=displayed_second))

    def handle_move(self, connection, intent: MoveIntent):
        engine = self.components.engine
        piece = engine.piece_at(intent.source)
        if not self._owns(connection, piece):
            self._reject(connection, piece, intent.source)
            return

        result = engine.request_move(intent.source, intent.destination)
        if not result.is_accepted:
            self._reject(connection, piece, intent.destination)

    def handle_jump(self, connection, intent: JumpIntent):
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
        role = self._roles.get(connection)
        return _COLOR_BY_ROLE.get(role) == piece.color

    def _reject(self, connection, piece, destination):
        event = IllegalActionEvent(
            piece_id=piece.id if piece is not None else None,
            destination=destination, at_ms=self.components.engine.clock,
        )
        self._network_publisher.unicast(connection, event)

    # -- rating ---------------------------------------------------------------

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
        self._rating_store.update_ratings(white_username, black_username, winner_color)

    # -- lookups ----------------------------------------------------------------

    def _connection_for_username(self, username):
        for connection, name in self._usernames.items():
            if name == username:
                return connection
        return None

    def _connection_for_role(self, role):
        for connection, assigned_role in self._roles.items():
            if assigned_role == role:
                return connection
        return None
