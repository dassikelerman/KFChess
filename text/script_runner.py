from text.script_parser import ClickCommand, JumpCommand, PrintBoardCommand, WaitCommand


class ScriptRunner:
    def __init__(self, controller, game_engine, board_printer):
        self._controller = controller
        self._game_engine = game_engine
        self._board_printer = board_printer

    def run(self, commands):
        for command in commands:
            self._execute(command)

    def _execute(self, command):
        if isinstance(command, ClickCommand):
            self._controller.click(command.x, command.y)
        elif isinstance(command, JumpCommand):
            self._controller.jump(command.x, command.y)
        elif isinstance(command, WaitCommand):
            self._game_engine.wait(command.ms)
        elif isinstance(command, PrintBoardCommand):
            self._game_engine.wait(0)  # resolve anything due before rendering
            print(self._board_printer.render(self._game_engine.snapshot()))
