import pytest

import client.run as client_run


def test_main_exits_cleanly_with_a_message_when_the_lobby_connection_drops(monkeypatch, capsys):
    monkeypatch.setattr(client_run.sys, "argv", ["client.run", "ws://server"])
    monkeypatch.setattr(client_run, "configure_logging", lambda path: None)

    def fake_run(ws_url):
        raise ConnectionError("connection closed: server went away")

    monkeypatch.setattr(client_run, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        client_run.main()

    assert excinfo.value.code == 1
    assert "connection closed: server went away" in capsys.readouterr().out


def test_main_does_not_swallow_unrelated_exceptions(monkeypatch):
    monkeypatch.setattr(client_run.sys, "argv", ["client.run", "ws://server"])
    monkeypatch.setattr(client_run, "configure_logging", lambda path: None)

    def fake_run(ws_url):
        raise RuntimeError("something unrelated to the connection")

    monkeypatch.setattr(client_run, "run", fake_run)

    with pytest.raises(RuntimeError):
        client_run.main()
