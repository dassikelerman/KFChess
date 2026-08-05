"""ClientSession: authenticate a connection, seat it, keep it fed - the ordered story.

authenticate (via AuthService) -> enter the lobby -> try to reconnect it into a room it
was disconnected from -> hand every following message to ClientMessageRouter and send
back whatever it decides to send - until the connection ends, at which point
on_disconnect runs exactly once. Every result the router hands back (see
server/rooms.py's RoomPlacement, server/client_message_router.py's
RoomPlacementRejected) already knows how to turn itself into outbound payloads via
outbound_payloads() - this class never inspects a result's type to decide what to send,
so a new result type never requires a change here. AuthService/ClientMessageRouter are
synchronous and typed; this class only ever talks to them and to ClientConnection
(server/client_connection.py), never directly to a socket or to json.
"""

import logging

from protocol.lobby_messages import LoggedIn, Login
from protocol.registry import decode_json_message, message_to_payload
from server.client_connection import ClientConnection
from server.client_message_router import MessageRejected
from server.contracts import Participant, ParticipantState

logger = logging.getLogger(__name__)

LOGIN_TIMEOUT_S = 5
REJECTED_LOGIN_CLOSE_CODE = 1008


def _decode_login(raw):
    """Decode a Login off the wire through the same registry as every other message,
    then apply login's own business rules (trimmed, non-empty) on top of the typed
    result - the registry only guarantees shape, not that the fields are meaningful."""
    try:
        message = decode_json_message(raw)
    except Exception:
        return None, None, "expected a Login message"

    if not isinstance(message, Login):
        return None, None, "expected a Login message"
    if not isinstance(message.username, str):
        return None, None, "username must be a string"
    if not isinstance(message.password, str):
        return None, None, "password must be a string"

    username = message.username.strip()
    if not username:
        return None, None, "username must not be empty"
    if not message.password:
        return None, None, "password must not be empty"

    return username, message.password, None


async def await_login(connection, auth_service):
    raw = await connection.recv(timeout_s=LOGIN_TIMEOUT_S)
    if raw is None:
        await connection.close(REJECTED_LOGIN_CLOSE_CODE, "login timed out")
        return None

    username, password, rejection_reason = _decode_login(raw)
    if rejection_reason is not None:
        await connection.close(REJECTED_LOGIN_CLOSE_CODE, rejection_reason)
        return None

    identity = await auth_service.authenticate(username, password)
    if identity is None:
        await connection.close(REJECTED_LOGIN_CLOSE_CODE, "wrong password")
        return None

    return identity


class ClientSession:
    def __init__(self, auth_service, router, on_disconnect):
        self._auth_service = auth_service
        self._router = router
        self._on_disconnect = on_disconnect

    async def run(self, raw_connection) -> None:
        connection = ClientConnection(raw_connection)
        participant = self._register_connection(raw_connection)
        try:
            if not await self._authenticate(participant, connection):
                return
            await self._enter_lobby(participant, connection)
            await self._attempt_reconnect(participant, connection)
            await self._receive_messages(participant, connection)
        finally:
            await self._handle_disconnect(participant)

    def _register_connection(self, raw_connection):
        participant = Participant(connection=raw_connection)
        logger.info("connection opened: connection_id=%s", participant.connection_id)
        return participant

    async def _authenticate(self, participant, connection):
        identity = await await_login(connection, self._auth_service)
        if identity is None:
            logger.warning("login rejected: connection_id=%s", participant.connection_id)
            return False

        participant.username = identity.username
        participant.rating = identity.rating
        participant.authenticated = True
        participant.state = ParticipantState.LOBBY
        logger.info("login succeeded: connection_id=%s username=%s", participant.connection_id, identity.username)
        return True

    async def _enter_lobby(self, participant, connection):
        await connection.send_payload(
            message_to_payload(LoggedIn(username=participant.username, rating=participant.rating))
        )
        logger.info(
            "entered lobby: connection_id=%s username=%s rating=%s",
            participant.connection_id, participant.username, participant.rating,
        )

    async def _attempt_reconnect(self, participant, connection):
        placement = self._router.try_reconnect(participant)
        if placement is None:
            return
        for payload in placement.outbound_payloads():
            await connection.send_payload(payload)

    async def _receive_messages(self, participant, connection):
        async for raw in connection:
            await self._handle_incoming_message(participant, connection, raw)

    async def _handle_incoming_message(self, participant, connection, raw):
        try:
            message = decode_json_message(raw)
        except Exception:
            logger.warning("malformed or unrecognized message: connection_id=%s", participant.connection_id)
            return

        try:
            result = self._router.route(participant, message)
        except MessageRejected:
            return  # the router already logged the rejection with its reason
        except Exception:
            logger.exception("unexpected failure routing a message: connection_id=%s", participant.connection_id)
            return

        if result is None:
            return
        for payload in result.outbound_payloads():
            await connection.send_payload(payload)

    async def _handle_disconnect(self, participant):
        participant.state = ParticipantState.DISCONNECTED
        logger.info(
            "connection closed: connection_id=%s username=%s", participant.connection_id, participant.username,
        )
        await self._on_disconnect(participant)
