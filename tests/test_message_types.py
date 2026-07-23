from protocol.message_types import MessageType, RoomAction


def test_message_type_values_match_the_wire_tags_already_in_use():
    assert MessageType.GAME_SNAPSHOT == "GameSnapshot"
    assert MessageType.MOVE_COMPLETED == "MoveCompletedEvent"
    assert MessageType.CAPTURE == "CaptureEvent"
    assert MessageType.JUMP_COMPLETED == "JumpCompletedEvent"
    assert MessageType.MOTION_STOPPED == "MotionStoppedEvent"
    assert MessageType.PROMOTION == "PromotionEvent"
    assert MessageType.GAME_OVER == "GameOverEvent"
    assert MessageType.ILLEGAL_ACTION == "IllegalActionEvent"
    assert MessageType.PLAYER_DISCONNECTED == "PlayerDisconnectedEvent"
    assert MessageType.PLAYER_RECONNECTED == "PlayerReconnectedEvent"
    assert MessageType.MOVE_INTENT == "MoveIntent"
    assert MessageType.JUMP_INTENT == "JumpIntent"
    assert MessageType.LOGIN == "Login"
    assert MessageType.ROLE == "role"


def test_message_type_values_for_the_new_lobby_and_matchmaking_messages():
    assert MessageType.LOGGED_IN == "LoggedIn"
    assert MessageType.PLAY_INTENT == "PlayIntent"
    assert MessageType.ROOM_INTENT == "RoomIntent"
    assert MessageType.ROOM_CREATED == "RoomCreated"
    assert MessageType.ROOM_REJECTED == "RoomRejected"
    assert MessageType.MATCH_NOT_FOUND == "MatchNotFound"


def test_room_action_values():
    assert RoomAction.CREATE == "create"
    assert RoomAction.JOIN == "join"
