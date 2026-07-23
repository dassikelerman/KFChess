"""The Home screen: shell login, then Play/Room until the server seats this client.

Covers everything the presentation calls "Home screen" in one place: login() prompts
for a username and password in the terminal (never a GUI) and retries on a rejected
password - on a brand new connection each attempt, since the server closes the old one
on rejection. run_lobby() then shows the lobby window (client/lobby_view.py), sends
whatever the player picked, and drains the connection's inbound queue for the outcome -
a room id, a rejection/notice popup, or (once seated) the role + first snapshot that
client/run.py needs to build the real GameWindow.

`read_line`/`read_secret`/`notify`/`attempt_login` are injected (defaulting to
input/getpass/print/connect_and_login) so the whole prompt-and-retry flow is
unit-tested without a real terminal or socket.
"""

import getpass
import logging
import queue
import tkinter as tk
from tkinter import messagebox

import cv2

import constants
from client.lobby_view import LobbyView, WINDOW_NAME
from client.server_connection import (
    ConnectionClosed, EventReceived, RoleAssigned, ServerConnection, SnapshotReceived,
)
from protocol.lobby_messages import LoggedIn, MatchNotFound, RoomCreated, RoomRejected

logger = logging.getLogger(__name__)


def prompt_for_username(read_line=input):
    username = ""
    while not username:
        username = read_line("Username: ").strip()
    return username


def connect_and_login(ws_url, username, password, connection_factory=ServerConnection):
    connection = connection_factory(ws_url)
    connection.start()
    connection.send_login(username, password)

    while True:
        item = connection.inbound.get()
        if isinstance(item, EventReceived) and isinstance(item.event, LoggedIn):
            logger.info("login succeeded for username=%r", item.event.username)
            return connection, item.event.username, item.event.rating
        if isinstance(item, ConnectionClosed):
            logger.warning("login rejected for username=%r", username)
            return None


def login(ws_url, read_line=input, read_secret=getpass.getpass, notify=print, attempt_login=connect_and_login):
    username = prompt_for_username(read_line)

    login_result = None
    while login_result is None:
        password = read_secret("Password: ")
        login_result = attempt_login(ws_url, username, password)
        if login_result is None:
            notify("login failed")

    return login_result


def run_lobby(connection):
    view = LobbyView(connection)
    view.open()
    room_id = None
    role = None
    try:
        while True:
            view.render()

            for item in _drain(connection):
                if isinstance(item, EventReceived) and isinstance(item.event, RoomCreated):
                    room_id = item.event.room_id
                    logger.info("room created: room_id=%s", room_id)
                elif isinstance(item, EventReceived) and isinstance(item.event, RoomRejected):
                    logger.info("room join rejected: reason=%s", item.event.reason)
                    _show_room_rejected(item.event.reason)
                elif isinstance(item, EventReceived) and isinstance(item.event, MatchNotFound):
                    logger.info("matchmaking gave up: reason=%s", item.event.reason)
                    view.set_searching(False)
                    _show_match_not_found(item.event.reason)
                elif isinstance(item, RoleAssigned):
                    role = item.role
                elif isinstance(item, SnapshotReceived):
                    logger.info("placed in room: room_id=%s role=%s", room_id, role)
                    return room_id, role, item.game_snapshot, item.clock_ms
                elif isinstance(item, ConnectionClosed):
                    logger.warning("connection closed while in the lobby: reason=%r", item.reason)
                    raise ConnectionError(f"connection closed: {item.reason}")

            key = cv2.waitKey(constants.FRAME_POLL_MS) & 0xFF
            if key == constants.ESCAPE_KEY or cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                raise SystemExit("lobby closed by user")
    finally:
        view.close()


def _drain(connection):
    items = []
    while True:
        try:
            items.append(connection.inbound.get_nowait())
        except queue.Empty:
            return items


def _show_room_rejected(reason):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Room rejected", reason)
    root.destroy()


def _show_match_not_found(reason):
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("No match found", reason)
    root.destroy()
