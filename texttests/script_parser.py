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
