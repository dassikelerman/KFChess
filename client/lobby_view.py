"""LobbyView: the Home screen's Play/Room window and its room-id popup.

Two small GUI pieces of the same on-screen lobby, kept in one file even though they use
different toolkits: LobbyView is a cv2 window with Play/Room buttons; open_room_dialog
(tkinter) is the Create/Join/Cancel popup it opens when Room is clicked. Neither is used
anywhere else. The polling/flow-control loop that drives this window lives one level up,
in client/home_screen.py.
"""

import tkinter as tk

import cv2
import numpy as np

from protocol.message_types import RoomAction

WINDOW_NAME = "KungFu Chess - Lobby"
WINDOW_SIZE = (240, 400)
ROOM_BUTTON = (40, 40, 240, 100)
PLAY_BUTTON = (40, 120, 240, 180)


def open_room_dialog():
    result = ["cancel", None]

    root = tk.Tk()
    root.title("Room")

    room_id_var = tk.StringVar()

    def _create():
        result[0] = "create"
        result[1] = None
        root.destroy()

    def _join():
        result[0] = "join"
        result[1] = room_id_var.get().strip()
        root.destroy()

    def _cancel():
        result[0] = "cancel"
        result[1] = None
        root.destroy()

    tk.Label(root, text="Room ID (leave empty to create):").pack(padx=10, pady=(10, 0))
    entry = tk.Entry(root, textvariable=room_id_var)
    entry.pack(padx=10, pady=5)
    entry.focus_set()

    button_frame = tk.Frame(root)
    button_frame.pack(padx=10, pady=10)
    tk.Button(button_frame, text="Create", command=_create).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Join", command=_join).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Cancel", command=_cancel).pack(side=tk.LEFT, padx=5)

    root.protocol("WM_DELETE_WINDOW", _cancel)
    root.mainloop()

    return result[0], result[1]


class LobbyView:
    def __init__(self, connection):
        self._connection = connection
        self._searching = False

    def open(self):
        cv2.namedWindow(WINDOW_NAME)
        cv2.setMouseCallback(WINDOW_NAME, self._on_mouse)

    def close(self):
        cv2.destroyWindow(WINDOW_NAME)

    def set_searching(self, searching):
        self._searching = searching

    def render(self):
        height, width = WINDOW_SIZE
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        x1, y1, x2, y2 = ROOM_BUTTON
        cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 80, 80), thickness=-1)
        cv2.putText(
            frame, "Room", (x1 + 45, y1 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA,
        )

        px1, py1, px2, py2 = PLAY_BUTTON
        play_color = (60, 60, 60) if self._searching else (80, 80, 80)
        cv2.rectangle(frame, (px1, py1), (px2, py2), play_color, thickness=-1)
        play_text = "Searching..." if self._searching else "Play"
        cv2.putText(
            frame, play_text, (px1 + 15, py1 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA,
        )

        cv2.imshow(WINDOW_NAME, frame)

    def _on_mouse(self, event, x, y, flags, userdata):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if self._inside(ROOM_BUTTON, x, y):
            self._handle_room_click()
        elif self._inside(PLAY_BUTTON, x, y):
            self._handle_play_click()

    def _handle_room_click(self):
        action, room_id = open_room_dialog()
        if action == "create":
            self._connection.send_room_intent(RoomAction.CREATE)
        elif action == "join":
            self._connection.send_room_intent(RoomAction.JOIN, room_id)

    def _handle_play_click(self):
        if self._searching:
            return
        self._searching = True
        self._connection.send_play_intent()

    def _inside(self, button, x, y):
        x1, y1, x2, y2 = button
        return x1 <= x <= x2 and y1 <= y <= y2
