import getpass

from client.ws_client import WsClient


def prompt_for_username():
    username = ""
    while not username:
        username = input("Username: ").strip()
    return username


def connect_and_login(ws_url, username, password):
    ws_client = WsClient(ws_url)
    ws_client.start()
    ws_client.send_login(username, password)

    role = None
    game_snapshot = None
    clock_ms = None
    while game_snapshot is None:
        item = ws_client.inbound.get()
        if item[0] == "snapshot":
            _, game_snapshot, clock_ms = item
        elif item[0] == "role":
            _, role = item
        elif item[0] == "closed":
            return None
    return ws_client, role, game_snapshot, clock_ms


def login(ws_url):
    username = prompt_for_username()

    login_result = None
    while login_result is None:
        password = getpass.getpass("Password: ")
        login_result = connect_and_login(ws_url, username, password)
        if login_result is None:
            print("login failed")

    ws_client, role, game_snapshot, clock_ms = login_result
    return username, role, ws_client, game_snapshot, clock_ms
