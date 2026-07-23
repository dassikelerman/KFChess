"""Central logging setup: point the whole process's logging at one file.

Every module logs through logging.getLogger(__name__) and stays silent until this
runs - an entry point (server or client) calls configure_logging() once, before doing
anything else, so every module's INFO+ records land in one log file without any module
needing to know where it logs.
"""

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(log_path):
    """Send every logger's INFO-and-above records to log_path.

    Replaces any handlers already on the root logger, so calling this twice (e.g.
    across tests that both import an entry point module) does not duplicate every line
    or leave a handler pointed at a previous test's file.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for existing in list(root.handlers):
        root.removeHandler(existing)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
