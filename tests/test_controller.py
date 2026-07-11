from unittest.mock import Mock

from input.controller import _dispatch


def test_dispatch_ignores_blank_command():
    # Should not raise for an empty command line.
    _dispatch("", engine=None, renderer=None)


def test_dispatch_click_calls_handle_click_with_int_coords():
    engine = Mock()
    _dispatch("click 10 20", engine=engine, renderer=None)
    engine.handle_click.assert_called_once_with(10, 20)


def test_dispatch_jump_calls_handle_jump_with_int_coords():
    engine = Mock()
    _dispatch("jump 30 40", engine=engine, renderer=None)
    engine.handle_jump.assert_called_once_with(30, 40)


def test_dispatch_wait_calls_wait_with_int_duration():
    engine = Mock()
    _dispatch("wait 500", engine=engine, renderer=None)
    engine.wait.assert_called_once_with(500)


def test_dispatch_print_prints_rendered_board(capsys):
    engine = Mock()
    engine.render.return_value = "wK . bK"
    renderer = Mock()
    _dispatch("print", engine=engine, renderer=renderer)
    engine.render.assert_called_once_with(renderer)
    assert capsys.readouterr().out.strip() == "wK . bK"


def test_dispatch_ignores_unknown_action():
    engine = Mock()
    _dispatch("frobnicate 1 2", engine=engine, renderer=None)
    engine.handle_click.assert_not_called()
    engine.handle_jump.assert_not_called()
    engine.wait.assert_not_called()
