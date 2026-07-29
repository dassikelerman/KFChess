import queue
from unittest.mock import patch

from client.game_window import GameWindow
from client.server_connection import ConnectionClosed, EventReceived, SnapshotReceived
from events.dispatcher import EventDispatcher


class _FakeConnection:
    def __init__(self, *items):
        self.inbound = queue.Queue()
        for item in items:
            self.inbound.put(item)


def _make_window(connection, notify_connection_lost=None):
    return GameWindow(
        connection, snapshot_view=object(), dispatcher=EventDispatcher(), score_tracker=None,
        action_history=None, sound_system=None, sound_paths={}, view=None, controller=None,
        notify_connection_lost=notify_connection_lost or (lambda reason: None),
    )


def test_drain_inbound_records_the_reason_and_stops_draining_once_the_connection_closes():
    # A snapshot queued before the close must still land; anything queued after it must
    # not, since the connection is already gone by then.
    connection = _FakeConnection(
        SnapshotReceived(game_snapshot="snapshot-1", clock_ms=1),
        ConnectionClosed(reason="server closed the connection"),
        SnapshotReceived(game_snapshot="snapshot-2", clock_ms=2),
    )
    window = _make_window(connection)
    window._snapshot_view = _RecordingSnapshotView()

    window._drain_inbound()

    assert window._connection_lost_reason == "server closed the connection"
    assert window._snapshot_view.updates == [("snapshot-1", 1)]
    assert not connection.inbound.empty()  # snapshot-2 was left undrained


class _RecordingSnapshotView:
    def __init__(self):
        self.updates = []

    def update(self, game_snapshot, clock_ms):
        self.updates.append((game_snapshot, clock_ms))


def test_drain_inbound_falls_back_to_a_default_message_when_the_reason_is_empty():
    connection = _FakeConnection(ConnectionClosed(reason=""))
    window = _make_window(connection)

    window._drain_inbound()

    assert window._connection_lost_reason == "The connection to the server was lost."


class _FakeEvent:
    pass


def test_drain_inbound_still_dispatches_events_queued_before_the_close():
    received = []
    event = _FakeEvent()
    connection = _FakeConnection(EventReceived(event=event))
    window = _make_window(connection)
    window._dispatcher.subscribe(_FakeEvent, received.append)

    window._drain_inbound()

    assert received == [event]


def test_run_exits_the_loop_and_notifies_exactly_once_when_the_connection_closes():
    notified = []
    connection = _FakeConnection(ConnectionClosed(reason="boom"))
    window = _make_window(connection, notify_connection_lost=notified.append)

    with patch("cv2.namedWindow"), patch("cv2.setMouseCallback"), patch("cv2.destroyAllWindows") as mock_destroy:
        window.run()

    assert notified == ["boom"]
    mock_destroy.assert_called_once()
