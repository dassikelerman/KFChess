import inspect

import pytest

from model.position import Position
from protocol.game_messages import JumpIntent, MoveIntent
from protocol.lobby_messages import CreateRoomIntent, JoinRoomIntent, LoggedIn, Login, PlayIntent
from server.client_message_router import ClientMessageRouter, MessageRejected, RoomPlacementRejected
from server.contracts import Participant, ParticipantState
from server.matchmaker import AlreadyQueuedError, MatchFound

POSITION = Position(0, 0)


class FakeSession:
    def __init__(self):
        self.handle_move_calls = []
        self.handle_jump_calls = []

    def handle_move(self, connection, intent):
        self.handle_move_calls.append((connection, intent))

    def handle_jump(self, connection, intent):
        self.handle_jump_calls.append((connection, intent))


class FakeGameRoomRegistry:
    def __init__(self):
        self.create_private_room_calls = []
        self.join_private_room_calls = []
        self.create_matched_room_calls = []
        self.game_session_for_calls = []
        self.session = FakeSession()
        self.join_result = "joined"

    def create_private_room(self, participant):
        self.create_private_room_calls.append(participant)
        return "created"

    def join_private_room(self, participant, room_id):
        self.join_private_room_calls.append((participant, room_id))
        return self.join_result

    def create_matched_room(self, white, black):
        self.create_matched_room_calls.append((white, black))

    def game_session_for(self, participant):
        self.game_session_for_calls.append(participant)
        return self.session


class FakeMatchmaker:
    def __init__(self):
        self.enqueue_or_match_calls = []
        self.result = "queued"

    def enqueue_or_match(self, participant):
        self.enqueue_or_match_calls.append(participant)
        return self.result


def _make_participant(state, authenticated=True):
    return Participant(connection="fake", username="alice", authenticated=authenticated, state=state)


def _make_router():
    game_room_registry = FakeGameRoomRegistry()
    matchmaker = FakeMatchmaker()
    return ClientMessageRouter(game_room_registry, matchmaker), game_room_registry, matchmaker


def test_client_message_router_class_has_no_json_or_websocket_specific_dependencies():
    # ClientMessageRouter must stay fully decoupled from the wire format - it only ever
    # sees already-typed messages ClientSession decoded, never json or websockets.
    # RoomPlacementRejected (same module) does need message_to_payload, so this checks
    # the class's own source, not the whole file.
    source = inspect.getsource(ClientMessageRouter)
    assert "json" not in source
    assert "websockets" not in source


@pytest.mark.parametrize(
    "message_type, handler_name",
    [
        (Login, "_route_login"),
        (MoveIntent, "_route_move_intent"),
        (JumpIntent, "_route_jump_intent"),
        (PlayIntent, "_route_play_intent"),
        (CreateRoomIntent, "_route_create_room_intent"),
        (JoinRoomIntent, "_route_join_room_intent"),
    ],
)
def test_every_supported_message_type_is_registered_to_its_own_handler(message_type, handler_name):
    router, _, _ = _make_router()

    assert router._handlers_by_type[message_type] == getattr(router, handler_name)


def test_the_handler_registry_covers_exactly_the_supported_message_types():
    router, _, _ = _make_router()

    assert set(router._handlers_by_type) == {
        Login, MoveIntent, JumpIntent, PlayIntent, CreateRoomIntent, JoinRoomIntent,
    }


@pytest.mark.parametrize(
    "message",
    [
        Login(username="alice", password="hunter2"),
        MoveIntent(source=POSITION, destination=POSITION),
        JumpIntent(position=POSITION),
        PlayIntent(),
        CreateRoomIntent(),
        JoinRoomIntent(join_code="abc"),
    ],
    ids=lambda m: type(m).__name__,
)
def test_route_dispatches_every_supported_message_type_without_raising_unrecognized(message):
    # A message type this router doesn't know about raises MessageRejected with an
    # "unrecognized message type" reason (see test_an_unrecognized_message_type_is_
    # rejected below) - none of the genuinely supported types should ever hit that path,
    # regardless of what the participant's state does to the handler's own behavior.
    router, _, _ = _make_router()
    participant = _make_participant(ParticipantState.LOBBY, authenticated=False)

    try:
        router.route(participant, message)
    except MessageRejected as rejection:
        assert "unrecognized message type" not in rejection.reason


def test_a_second_login_after_authentication_is_rejected():
    router, _, _ = _make_router()
    participant = _make_participant(ParticipantState.LOBBY, authenticated=True)

    with pytest.raises(MessageRejected):
        router.route(participant, Login(username="alice", password="hunter2"))


def test_a_move_intent_while_in_the_lobby_is_rejected():
    router, _, _ = _make_router()
    participant = _make_participant(ParticipantState.LOBBY)

    with pytest.raises(MessageRejected):
        router.route(participant, MoveIntent(source=POSITION, destination=POSITION))


def test_a_jump_intent_while_searching_is_rejected():
    router, _, _ = _make_router()
    participant = _make_participant(ParticipantState.SEARCHING)

    with pytest.raises(MessageRejected):
        router.route(participant, JumpIntent(position=POSITION))


def test_a_move_intent_while_in_a_room_is_forwarded_to_the_rooms_session_as_a_typed_intent():
    router, game_room_registry, _ = _make_router()
    participant = _make_participant(ParticipantState.IN_ROOM)
    message = MoveIntent(source=POSITION, destination=POSITION)

    router.route(participant, message)

    assert game_room_registry.game_session_for_calls == [participant]
    # The exact same MoveIntent instance arrives - no object -> dict -> object round trip.
    assert game_room_registry.session.handle_move_calls == [(participant.connection, message)]


def test_a_jump_intent_while_in_a_room_is_forwarded_to_the_rooms_session_as_a_typed_intent():
    router, game_room_registry, _ = _make_router()
    participant = _make_participant(ParticipantState.IN_ROOM)
    message = JumpIntent(position=POSITION)

    router.route(participant, message)

    assert game_room_registry.session.handle_jump_calls == [(participant.connection, message)]


def test_a_move_intent_while_in_the_lobby_is_not_forwarded_to_any_session():
    router, game_room_registry, _ = _make_router()
    participant = _make_participant(ParticipantState.LOBBY)

    with pytest.raises(MessageRejected):
        router.route(participant, MoveIntent(source=POSITION, destination=POSITION))

    assert game_room_registry.game_session_for_calls == []
    assert game_room_registry.session.handle_move_calls == []


def test_a_room_intent_while_already_in_a_room_is_rejected():
    router, _, _ = _make_router()
    participant = _make_participant(ParticipantState.IN_ROOM)

    with pytest.raises(MessageRejected):
        router.route(participant, CreateRoomIntent())


def test_a_play_intent_while_already_in_a_room_is_rejected():
    router, _, _ = _make_router()
    participant = _make_participant(ParticipantState.IN_ROOM)

    with pytest.raises(MessageRejected):
        router.route(participant, PlayIntent())


def test_an_unrecognized_message_type_is_rejected():
    router, _, _ = _make_router()
    participant = _make_participant(ParticipantState.LOBBY)

    with pytest.raises(MessageRejected, match="unrecognized message type 'LoggedIn'"):
        router.route(participant, LoggedIn(username="alice", rating=1200))


def test_a_create_room_intent_dispatches_to_create_private_room():
    router, game_room_registry, _ = _make_router()
    participant = _make_participant(ParticipantState.LOBBY)

    router.route(participant, CreateRoomIntent())

    assert game_room_registry.create_private_room_calls == [participant]


def test_a_join_room_intent_dispatches_to_join_private_room_with_the_join_code():
    router, game_room_registry, _ = _make_router()
    participant = _make_participant(ParticipantState.LOBBY)

    router.route(participant, JoinRoomIntent(join_code="abc"))

    assert game_room_registry.join_private_room_calls == [(participant, "abc")]


def test_a_room_intent_while_searching_is_allowed_through_to_the_game_room_registry():
    router, game_room_registry, _ = _make_router()
    participant = _make_participant(ParticipantState.SEARCHING)

    router.route(participant, CreateRoomIntent())

    assert game_room_registry.create_private_room_calls == [participant]


def test_a_join_room_intent_to_an_unknown_room_returns_a_room_placement_rejected():
    router, game_room_registry, _ = _make_router()
    game_room_registry.join_result = None
    participant = _make_participant(ParticipantState.LOBBY)

    result = router.route(participant, JoinRoomIntent(join_code="no-such-code"))

    assert isinstance(result, RoomPlacementRejected)
    assert result.reason


# -- Play intent: matchmaking dispatch -----------------------------------------


def test_a_play_intent_dispatches_to_the_matchmaker():
    router, _, matchmaker = _make_router()
    participant = _make_participant(ParticipantState.LOBBY)

    router.route(participant, PlayIntent())

    assert matchmaker.enqueue_or_match_calls == [participant]


def test_a_play_intent_with_no_match_yet_marks_the_participant_searching():
    router, _, matchmaker = _make_router()
    participant = _make_participant(ParticipantState.LOBBY)
    matchmaker.result = "queued"  # anything that isn't a MatchFound

    router.route(participant, PlayIntent())

    assert participant.state is ParticipantState.SEARCHING


def test_a_play_intent_that_finds_a_match_creates_a_matched_room():
    router, game_room_registry, matchmaker = _make_router()
    white = _make_participant(ParticipantState.LOBBY)
    black = _make_participant(ParticipantState.LOBBY)
    matchmaker.result = MatchFound(white=white, black=black)

    router.route(black, PlayIntent())

    assert game_room_registry.create_matched_room_calls == [(white, black)]


def test_a_play_intent_already_queued_is_rejected():
    router, _, matchmaker = _make_router()

    def _raise_already_queued(participant):
        raise AlreadyQueuedError(f"{participant.username!r} is already queued for a match")

    matchmaker.enqueue_or_match = _raise_already_queued
    participant = _make_participant(ParticipantState.LOBBY)

    with pytest.raises(MessageRejected):
        router.route(participant, PlayIntent())
