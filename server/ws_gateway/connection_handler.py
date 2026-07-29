"""ConnectionHandler: the live connection, after authentication.

Owns everything that maps to the WS Gateway's responsibility once services
actually split apart (see Server_Design.md, migration step 3): entering the
lobby, trying to seat a reconnecting participant, the receive loop, decoding
each incoming message exactly once, handing it to ClientMessageRouter, and
translating whatever the router returns into the actual outbound JSON.
AuthGateway has already run by the time this class ever sees a participant.
"""

import json
import logging

from protocol.lobby_messages import LoggedIn, RoomRejected
from protocol.registry import decode_json_message, encode_json_message
from server.client_message_router import MessageRejected, RoomPlacementRejected
from server.rooms import RoomPlacement, build_room_placement_payloads

logger = logging.getLogger(__name__)


class ConnectionHandler:
    def __init__(self, rating_store, router):
        self._rating_store = rating_store
        self._router = router

    async def serve(self, participant):
        await self._enter_lobby(participant)
        await self._attempt_reconnect(participant)
        await self._receive_messages(participant)

    async def _enter_lobby(self, participant):
        participant.rating = self._rating_store.get_rating(participant.username)
        await self._send_message(participant, LoggedIn(username=participant.username, rating=participant.rating))
        logger.info(
            "entered lobby: connection_id=%s username=%s rating=%s",
            participant.connection_id, participant.username, participant.rating,
        )

    async def _attempt_reconnect(self, participant):
        placement = self._router.try_reconnect(participant)
        if placement is None:
            return
        await self._send_room_placement(participant, placement)
        logger.info(
            "reconnected: connection_id=%s username=%s room_id=%s role=%s",
            participant.connection_id, participant.username, placement.room_id, placement.role,
        )

    async def _receive_messages(self, participant):
        async for raw in participant.connection:
            await self._handle_incoming_message(participant, raw)

    async def _handle_incoming_message(self, participant, raw):
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

        await self._apply_route_result(participant, result)

    async def _apply_route_result(self, participant, result):
        if isinstance(result, RoomPlacement):
            await self._announce_room_placement(participant, result)
        elif isinstance(result, RoomPlacementRejected):
            await self._send_message(participant, RoomRejected(reason=result.reason))

    async def _announce_room_placement(self, participant, placement):
        await self._send_room_placement(participant, placement)
        logger.info(
            "placed in room: connection_id=%s username=%s room_id=%s role=%s",
            participant.connection_id, participant.username, placement.room_id, placement.role,
        )

    async def _send_room_placement(self, participant, placement):
        role_payload, snapshot_payload = build_room_placement_payloads(placement)
        await participant.connection.send(json.dumps(role_payload))
        await participant.connection.send(json.dumps(snapshot_payload))

    async def _send_message(self, participant, message):
        await participant.connection.send(encode_json_message(message))
