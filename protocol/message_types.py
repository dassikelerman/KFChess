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
    ROOM_REJECTED = "RoomRejected"
    MATCH_NOT_FOUND = "MatchNotFound"
    ROLE_ASSIGNED = "RoleAssigned"


class RoomAction(StrEnum):
    CREATE = "create"
    JOIN = "join"
