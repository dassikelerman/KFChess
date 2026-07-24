"""Structural checks for the packaging/timing/docs refactor itself - not one module's
behavior, but "did the old mechanisms actually go away" and "do the docs match reality".
"""

import importlib
import importlib.metadata
import pathlib

import pytest

import server.ws_server as ws_server
from server.rating import RatingStore
from server.rooms import GameRoomRegistry
from server.session import GameSession

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class _FakeNetworkPublisher:
    def unicast(self, connection, event):
        pass


# -- packaging ------------------------------------------------------------------


def test_conftest_sys_path_hack_is_gone():
    assert not (REPO_ROOT / "conftest.py").exists()


def test_kf_chess_is_installed_as_a_package_not_found_via_sys_path():
    # If this raised, these tests could only be running because of a sys.path hack,
    # not a real `pip install -e .` - see pyproject.toml / README "Installing".
    version = importlib.metadata.version("kf-chess")
    assert version


# -- no remaining per-room game-loop tasks ---------------------------------------


def test_game_room_registry_has_no_per_room_task_bookkeeping():
    registry = GameRoomRegistry(lambda connection, payload: None, RatingStore(":memory:"))
    assert not hasattr(registry, "_game_loop_tasks_by_room_id")
    assert hasattr(registry, "tick")


def test_server_game_loop_module_no_longer_exists():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("server.game_loop")


# -- no remaining matchmaking-expiry loop ----------------------------------------


def test_ws_server_has_no_separate_expiry_loop():
    assert not hasattr(ws_server, "_run_expiry_loop")
    assert not hasattr(ws_server, "EXPIRY_POLL_S")
    assert hasattr(ws_server, "_run_server_loop")


# -- no remaining disconnect sleeper task ----------------------------------------


def test_game_session_has_no_sleeper_or_countdown_task_bookkeeping():
    session = GameSession(["wK .", ". ."], make_network_publisher=lambda dispatcher: _FakeNetworkPublisher())
    assert not hasattr(session, "_countdown_tasks_by_color")
    assert not hasattr(session, "_sleep")
    assert hasattr(session, "_countdowns_by_color")


def test_server_interfaces_module_no_longer_exists():
    # Sleeper lived here - the whole module (and MessageSender/RatingRepository with
    # it) was merged into server/contracts.py, not just the one Protocol removed.
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("server.interfaces")


def test_server_router_and_participant_modules_no_longer_exist():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("server.router")
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("server.participant")


# -- documentation matches the real file layout ----------------------------------


def test_readme_project_layout_paths_all_exist():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for path in (
        "model/", "rules/", "realtime/", "engine/", "board_io/", "events/", "app/",
        "input/", "view/", "text/", "protocol/", "server/", "client/", "scripts/", "tests/",
    ):
        assert path in readme, f"README no longer mentions {path!r}"
        assert (REPO_ROOT / path).is_dir(), f"README references {path!r} but it doesn't exist"


def test_readme_no_longer_references_deleted_files():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for stale in ("config/settings.py", "board/board_interface.py", "game/engine.py", "main.py"):
        assert stale not in readme


def test_architecture_doc_exists_and_is_referenced_by_readme():
    architecture_doc = REPO_ROOT / "docs" / "architecture.md"
    assert architecture_doc.is_file()
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/architecture.md" in readme


def test_architecture_doc_mentions_the_one_server_loop():
    architecture_doc = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    assert "tick(dt_ms)" in architecture_doc
    assert "_run_server_loop" in architecture_doc
