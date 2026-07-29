"""AuthGateway: the login handshake.

The one part of connection setup that maps to the API Gateway's REST-style
"authenticate" responsibility once services actually split apart (see
Server_Design.md, migration step 3). It still runs over the same live
WebSocket for now - the login handshake is the first message on the same
socket the game later runs on - but the class boundary here is exactly the
seam a future real API Gateway process would sit behind.
"""

import asyncio
import logging

import websockets

from protocol.lobby_messages import Login
from protocol.registry import decode_json_message
from server.user_store import LoginResult

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


class AuthGateway:
    def __init__(self, user_store):
        self._user_store = user_store

    async def authenticate(self, connection):
        try:
            raw = await asyncio.wait_for(connection.recv(), timeout=LOGIN_TIMEOUT_S)
        except asyncio.TimeoutError:
            await connection.close(code=REJECTED_LOGIN_CLOSE_CODE, reason="login timed out")
            return None
        except websockets.ConnectionClosed:
            return None

        username, password, rejection_reason = _decode_login(raw)
        if rejection_reason is not None:
            await connection.close(code=REJECTED_LOGIN_CLOSE_CODE, reason=rejection_reason)
            return None

        if self._user_store.create_or_verify(username, password) is LoginResult.WRONG_PASSWORD:
            await connection.close(code=REJECTED_LOGIN_CLOSE_CODE, reason="wrong password")
            return None

        return username
