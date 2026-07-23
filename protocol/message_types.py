from enum import StrEnum


class MessageType(StrEnum):
    GAME_SNAPSHOT = "GameSnapshot"
    MOVE_COMPLETED = "MoveCompletedEvent"
    CAPTURE = "CaptureEvent"
    JUMP_COMPLETED = "JumpCompletedEvent"
    MOTION_STOPPED = "MotionStoppedEvent"
    PROMOTION = "PromotionEvent"
    GAME_OVER = "GameOverEvent"
    ILLEGAL_ACTION = "IllegalActionEvent"
    PLAYER_DISCONNECTED = "PlayerDisconnectedEvent"
    PLAYER_RECONNECTED = "PlayerReconnectedEvent"
    MOVE_INTENT = "MoveIntent"
    JUMP_INTENT = "JumpIntent"
    LOGIN = "Login"
    LOGGED_IN = "LoggedIn"
    PLAY_INTENT = "PlayIntent"
    ROOM_INTENT = "RoomIntent"
    ROOM_CREATED = "RoomCreated"
    ROOM_REJECTED = "RoomRejected"
    MATCH_NOT_FOUND = "MatchNotFound"
    # Handshake-only, hand-built as a plain dict (see server/rooms.py) rather
    # than going through the protocol.registry message registry - hence lowercase,
    # unlike every class-name-derived tag above.
    ROLE = "role"


class RoomAction(StrEnum):
    CREATE = "create"
    JOIN = "join"
