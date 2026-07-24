from server.contracts import Participant, ParticipantState


def test_construction_defaults():
    client = Participant(connection="fake-connection")

    assert client.connection == "fake-connection"
    assert isinstance(client.connection_id, str)
    assert len(client.connection_id) == 8
    assert client.username is None
    assert client.rating is None
    assert client.role is None
    assert client.room_id is None
    assert client.authenticated is False
    assert client.state is ParticipantState.CONNECTED


def test_each_client_gets_its_own_connection_id():
    a = Participant(connection="conn-a")
    b = Participant(connection="conn-b")

    assert a.connection_id != b.connection_id


def test_fields_can_be_overridden_at_construction():
    client = Participant(
        connection="fake-connection", username="alice", rating=1200, role="white",
        room_id="room-1", authenticated=True, state=ParticipantState.IN_ROOM,
    )

    assert client.username == "alice"
    assert client.rating == 1200
    assert client.role == "white"
    assert client.room_id == "room-1"
    assert client.authenticated is True
    assert client.state is ParticipantState.IN_ROOM
