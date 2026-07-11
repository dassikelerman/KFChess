import io

import app


def test_main_reads_stdin_and_runs_script(monkeypatch, capsys):
    script = "Board:\nwK . bK\nCommands:\nprint\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(script))
    app.main()
    out = capsys.readouterr().out
    assert out.strip() == "wK . bK"


def test_main_strips_trailing_whitespace_from_each_line(monkeypatch, capsys):
    script = "Board:  \nwK . bK\t\nCommands:\nprint\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(script))
    app.main()
    out = capsys.readouterr().out
    assert out.strip() == "wK . bK"
