"""ConnectionLifecycle: the seam between the API Gateway and the WS Gateway.

Registers a connection, hands it to AuthGateway (server/api_gateway/auth.py)
for the login handshake, and on success hands it to ConnectionHandler
(server/ws_gateway/connection_handler.py) for the rest of its life. This is
exactly the boundary Server_Design.md's migration step 3 describes: today
both sides are plain constructor arguments called in-process, but the split
means a future real API Gateway/WS Gateway only has to replace this class
with a network hop, not touch either side's own logic.
"""

import logging

from server.contracts import Participant, ParticipantState

logger = logging.getLogger(__name__)


class ConnectionLifecycle:
    def __init__(self, auth_gateway, connection_handler, on_disconnect):
        self._auth_gateway = auth_gateway
        self._connection_handler = connection_handler
        self._on_disconnect = on_disconnect

    async def run(self, connection) -> None:
        participant = self._register_connection(connection)
        try:
            if not await self._authenticate(participant):
                return
            await self._connection_handler.serve(participant)
        finally:
            await self._handle_disconnect(participant)

    def _register_connection(self, connection):
        participant = Participant(connection=connection)
        logger.info("connection opened: connection_id=%s", participant.connection_id)
        return participant

    async def _authenticate(self, participant):
        username = await self._auth_gateway.authenticate(participant.connection)
        if username is None:
            logger.warning("login rejected: connection_id=%s", participant.connection_id)
            return False

        participant.username = username
        participant.authenticated = True
        participant.state = ParticipantState.LOBBY
        logger.info("login succeeded: connection_id=%s username=%s", participant.connection_id, username)
        return True

    async def _handle_disconnect(self, participant):
        participant.state = ParticipantState.DISCONNECTED
        logger.info(
            "connection closed: connection_id=%s username=%s", participant.connection_id, participant.username,
        )
        await self._on_disconnect(participant)
