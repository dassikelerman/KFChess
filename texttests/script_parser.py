def parse_input(lines):
    """Split raw input lines into the 'Board:' and 'Commands:' sections."""
    board_lines, commands = [], []
    section = None
    for line in lines:
        if line == "Board:":
            section = "board"
            continue
        if line == "Commands:":
            section = "commands"
            continue
        if section == "board":
            board_lines.append(line)
        elif section == "commands":
            commands.append(line)
    return board_lines, commands
