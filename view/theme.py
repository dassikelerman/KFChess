"""Theme: named colors and HUD sizes for cv2 rendering.

The only place pixel-level UI values live - a color or size gets a name here instead of
a bare tuple/number at the call site, so a reader never has to decode what (255, 255, 0)
means. Server/game-rule constants belong in constants.py, not here - this module is
rendering-only and has no engine or protocol imports.
"""

from model.piece import PieceColor

REST_OVERLAY_COLOR_BGR = (230, 160, 90)
REST_OVERLAY_ALPHA = 0.55

SELECTION_FRAME_COLOR_BGR = (60, 220, 255)
SELECTION_FRAME_THICKNESS = 4
SELECTION_FRAME_ALPHA = 0.85

PANEL_BACKGROUND_BGR = {PieceColor.BLACK: (30, 30, 30), PieceColor.WHITE: (235, 235, 235)}
PANEL_TEXT_BGR = {PieceColor.BLACK: (255, 255, 255), PieceColor.WHITE: (20, 20, 20)}
PANEL_TEXT_MARGIN = 14
PANEL_LINE_HEIGHT = 24
PANEL_SCORE_FONT_SIZE = 0.7
PANEL_ACTION_FONT_SIZE = 0.42

ROOM_LABEL_COLOR_BGR = (255, 255, 0)
DISCONNECT_WARNING_COLOR_BGR = (0, 0, 255)
HUD_TEXT_FONT_SIZE = 0.6
HUD_TEXT_THICKNESS = 2
