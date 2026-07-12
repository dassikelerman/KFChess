from dataclasses import dataclass


@dataclass(frozen=True)
class ClickCommand:
    x: int
    y: int


@dataclass(frozen=True)
class JumpCommand:
    x: int
    y: int


@dataclass(frozen=True)
class WaitCommand:
    ms: int


@dataclass(frozen=True)
class PrintBoardCommand:
    pass


def parse(script):
    """Turn raw script lines ("click X Y", "wait N", ...) into typed
    Command objects. A thin wrapper around the parts = line.split()
    shape script_runner.py's predecessor (app._dispatch) used - it
    doesn't change which commands are supported, just how they're
    represented.
    """
    commands = []
    for line in script:
        parts = line.split()
        if not parts:
            continue

        action = parts[0]
        if action == "click":
            commands.append(ClickCommand(int(parts[1]), int(parts[2])))
        elif action == "jump":
            commands.append(JumpCommand(int(parts[1]), int(parts[2])))
        elif action == "wait":
            commands.append(WaitCommand(int(parts[1])))
        elif action == "print":
            commands.append(PrintBoardCommand())
    return commands
