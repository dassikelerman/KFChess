from client.ws_client import WsClient
from events.serialization import JumpIntent, MoveIntent, to_dict
from model.position import Position


def make_client():
    return WsClient("ws://unused")


def test_request_move_enqueues_a_serialized_move_intent():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 2))

    payload = client._outbound.get_nowait()
    assert payload == to_dict(MoveIntent(source=Position(0, 0), destination=Position(0, 2)))


def test_request_jump_enqueues_a_serialized_jump_intent():
    client = make_client()

    client.request_jump(Position(1, 1))

    payload = client._outbound.get_nowait()
    assert payload == to_dict(JumpIntent(position=Position(1, 1)))


def test_multiple_outbound_intents_queue_in_order():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 1))
    client.request_jump(Position(2, 2))

    first = client._outbound.get_nowait()
    second = client._outbound.get_nowait()
    assert first["type"] == "MoveIntent"
    assert second["type"] == "JumpIntent"


def test_request_move_does_not_touch_the_inbound_queue():
    client = make_client()

    client.request_move(Position(0, 0), Position(0, 1))

    assert client.inbound.empty()


def test_request_jump_does_not_touch_the_inbound_queue():
    client = make_client()

    client.request_jump(Position(0, 0))

    assert client.inbound.empty()
