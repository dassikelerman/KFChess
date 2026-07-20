from server.session import Session

BOARD = ["wK .", ". ."]


def test_first_connection_is_assigned_white():
    session = Session(BOARD)
    assert session.assign_role("conn-a") == "white"


def test_second_connection_is_assigned_black():
    session = Session(BOARD)
    session.assign_role("conn-a")
    assert session.assign_role("conn-b") == "black"


def test_third_and_later_connections_are_assigned_spectator():
    session = Session(BOARD)
    session.assign_role("conn-a")
    session.assign_role("conn-b")
    assert session.assign_role("conn-c") == "spectator"
    assert session.assign_role("conn-d") == "spectator"


def test_asking_again_for_the_same_connection_returns_its_existing_role():
    session = Session(BOARD)
    first = session.assign_role("conn-a")
    again = session.assign_role("conn-a")
    assert first == again == "white"


def test_tick_advances_the_engines_clock():
    session = Session(BOARD)
    before = session.components.engine.clock

    session.tick(500)

    assert session.components.engine.clock == before + 500
