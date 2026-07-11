def _dispatch(command, engine, renderer):
    parts = command.split()
    if not parts:
        return

    action = parts[0]
    if action == "click":
        engine.handle_click(int(parts[1]), int(parts[2]))
    elif action == "jump":
        engine.handle_jump(int(parts[1]), int(parts[2]))
    elif action == "wait":
        engine.wait(int(parts[1]))
    elif action == "print":
        print(engine.render(renderer))
