from app.game_builder import build_game
from events.dispatcher import EventDispatcher


class _SomeEvent:
    pass


def test_build_game_returns_only_the_core_components():
    game = build_game(["wK .", ". ."])

    assert set(vars(game).keys()) == {"engine", "board", "dispatcher"}
    assert isinstance(game.dispatcher, EventDispatcher)


def test_build_game_does_not_expose_ui_only_trackers():
    game = build_game(["wK .", ". ."])

    assert not hasattr(game, "score_tracker")
    assert not hasattr(game, "action_history")
    assert not hasattr(game, "sound_system")


def test_the_dispatcher_returned_by_build_game_is_functional():
    game = build_game(["wK .", ". ."])
    received = []
    game.dispatcher.subscribe(_SomeEvent, received.append)

    event = _SomeEvent()
    game.dispatcher.publish(event)

    assert received == [event]
