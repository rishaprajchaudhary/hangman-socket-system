import json
import secrets
import socket
import threading
import urllib.parse
from pathlib import Path

HOST = "0.0.0.0"
PORT = 5555
MAX_ERRORS = 6
WIN_SCORE = 3
STATIC_DIR = Path(__file__).parent / "web"
state_lock = threading.Lock()

sessions = {}
game_state = {
    "player_ids": [],
    "player_names": [],
    "setter_index": 0,
    "current_turn_id": None,
    "scores": {},
    "player_errors": {},
    "match_winner": None,
    "secret_word": "",
    "masked_word": "",
    "guessed_letters": [],
    "wrong_letters": [],
    "max_errors": MAX_ERRORS,
    "status": "waiting_for_players",
    "message": "Waiting for players to join",
    "winner": None,
}


def reset_multiplayer_state():
    sessions.clear()
    game_state["player_ids"] = []
    game_state["player_names"] = []
    game_state["setter_index"] = 0
    game_state["current_turn_id"] = None
    game_state["scores"] = {}
    game_state["player_errors"] = {}
    game_state["match_winner"] = None
    clear_round_state()
    game_state["status"] = "waiting_for_players"
    game_state["message"] = "Multiplayer cleared. Waiting for players to join."


def make_response(status_code, body, content_type="application/json; charset=utf-8"):
    reason = {
        200: "OK",
        201: "Created",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        500: "Internal Server Error",
    }.get(status_code, "OK")

    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = json.dumps(body).encode("utf-8")

    headers = [
        f"HTTP/1.1 {status_code} {reason}",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body_bytes)}",
        "Connection: close",
        "Cache-Control: no-store",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("utf-8") + body_bytes


def read_http_request(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return None
        data += chunk
        if len(data) > 2 * 1024 * 1024:
            return None

    header_blob, body = data.split(b"\r\n\r\n", 1)
    lines = header_blob.decode("utf-8", errors="replace").split("\r\n")
    if not lines:
        return None

    request_line = lines[0].split(" ")
    if len(request_line) < 3:
        return None

    method, raw_path, _ = request_line
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    content_length = int(headers.get("content-length", "0") or 0)
    while len(body) < content_length:
        chunk = conn.recv(4096)
        if not chunk:
            break
        body += chunk

    return method, raw_path, headers, body[:content_length]


def load_static(path):
    if path in ("/", "/index.html"):
        target = STATIC_DIR / "index.html"
        content_type = "text/html; charset=utf-8"
    elif path == "/styles.css":
        target = STATIC_DIR / "styles.css"
        content_type = "text/css; charset=utf-8"
    elif path == "/app.js":
        target = STATIC_DIR / "app.js"
        content_type = "application/javascript; charset=utf-8"
    else:
        return None, None

    if not target.exists():
        return None, None
    return target.read_bytes(), content_type


def normalize_word(raw_word):
    letters = [ch.upper() for ch in raw_word if ch.isalpha()]
    return "".join(letters)


def clear_round_state():
    game_state["secret_word"] = ""
    game_state["guessed_letters"] = []
    game_state["wrong_letters"] = []
    game_state["winner"] = None
    game_state["masked_word"] = ""
    game_state["current_turn_id"] = None


def get_current_setter_index():
    if not game_state["player_ids"]:
        return None
    game_state["setter_index"] %= len(game_state["player_ids"])
    return game_state["setter_index"]


def get_current_setter_id():
    idx = get_current_setter_index()
    if idx is None:
        return None
    return game_state["player_ids"][idx]


def get_current_setter_name():
    idx = get_current_setter_index()
    if idx is None:
        return None
    return game_state["player_names"][idx]


def get_player_index(player_id):
    try:
        return game_state["player_ids"].index(player_id)
    except ValueError:
        return None


def is_active_guesser(player_id):
    if player_id is None:
        return False
    if player_id == get_current_setter_id():
        return False
    return game_state["player_errors"].get(player_id, 0) < game_state["max_errors"]


def get_next_active_guesser(start_after_id=None):
    ids = game_state["player_ids"]
    if len(ids) < 2:
        return None

    if start_after_id is None:
        start_idx = get_current_setter_index()
    else:
        found_idx = get_player_index(start_after_id)
        start_idx = found_idx if found_idx is not None else get_current_setter_index()

    if start_idx is None:
        return None

    for offset in range(1, len(ids) + 1):
        candidate = ids[(start_idx + offset) % len(ids)]
        if is_active_guesser(candidate):
            return candidate

    return None


def get_current_turn_name():
    turn_id = game_state["current_turn_id"]
    turn_idx = get_player_index(turn_id)
    if turn_idx is None:
        return None
    return game_state["player_names"][turn_idx]


def ensure_waiting_for_word_state():
    if len(game_state["player_ids"]) < 2:
        clear_round_state()
        game_state["status"] = "waiting_for_players"
        game_state["message"] = "Need at least 2 players to start."
        return

    clear_round_state()
    setter_name = get_current_setter_name() or "Setter"
    game_state["status"] = "waiting_for_word"
    game_state["message"] = f"{setter_name}'s turn to set a word."


def rotate_setter():
    if not game_state["player_ids"]:
        return
    game_state["setter_index"] = (game_state["setter_index"] + 1) % len(game_state["player_ids"])


def new_session(name):
    session_id = secrets.token_hex(16)
    sessions[session_id] = {"name": name}
    return session_id


def assign_role(session_id, name):
    if session_id not in game_state["player_ids"]:
        game_state["player_ids"].append(session_id)
        game_state["player_names"].append(name)
        game_state["scores"][session_id] = 0
        game_state["player_errors"][session_id] = 0

    if game_state["status"] == "waiting_for_players" and len(game_state["player_ids"]) >= 2:
        ensure_waiting_for_word_state()

    return "setter" if session_id == get_current_setter_id() else "guesser"


def ensure_session(session_id):
    return session_id in sessions


def make_masked(word, guessed):
    return " ".join(ch if ch in guessed else "_" for ch in word)


def public_state_for(session_id):
    role = "spectator"
    if session_id == get_current_setter_id():
        role = "setter"
    elif session_id in game_state["player_ids"]:
        role = "guesser"

    player_list = list(game_state["player_names"])
    scores = []
    for idx, pid in enumerate(game_state["player_ids"]):
        scores.append({
            "name": game_state["player_names"][idx],
            "score": game_state["scores"].get(pid, 0),
            "mistakes": game_state["player_errors"].get(pid, 0),
        })

    personal_errors = game_state["player_errors"].get(session_id, 0)

    return {
        "role": role,
        "players": {
            "count": len(player_list),
            "names": player_list,
            "current_setter": get_current_setter_name(),
            "scores": scores,
        },
        "status": game_state["status"],
        "message": game_state["message"],
        "masked_word": game_state["masked_word"],
        "guessed_letters": game_state["guessed_letters"],
        "wrong_letters": game_state["wrong_letters"],
        "incorrect_guesses": personal_errors,
        "max_errors": game_state["max_errors"],
        "winner": game_state["winner"],
        "match_winner": game_state["match_winner"],
        "current_turn": get_current_turn_name(),
        "your_turn": session_id == game_state["current_turn_id"],
        "win_score": WIN_SCORE,
        "eliminated": personal_errors >= game_state["max_errors"],
        "word_revealed": game_state["secret_word"] if game_state["status"] == "finished" else None,
    }


def api_join(payload):
    name = (payload.get("name") or "").strip()
    if not name:
        return 400, {"error": "Name is required"}

    with state_lock:
        session_id = new_session(name)
        role = assign_role(session_id, name)
        return 201, {"session_id": session_id, "role": role, "state": public_state_for(session_id)}


def api_state(query):
    session_id = query.get("sid", [""])[0]
    with state_lock:
        if not ensure_session(session_id):
            return 401, {"error": "Invalid session"}
        return 200, public_state_for(session_id)


def api_set_word(payload):
    session_id = payload.get("sid", "")
    raw_word = payload.get("word", "")
    word = normalize_word(raw_word)

    with state_lock:
        if not ensure_session(session_id):
            return 401, {"error": "Invalid session"}
        if session_id != get_current_setter_id():
            return 403, {"error": "Only current setter can set the word"}
        if game_state["status"] != "waiting_for_word":
            return 409, {"error": "Round is not ready for a new word"}
        if not word:
            return 400, {"error": "Word must include letters"}
        if len(word) < 3:
            return 400, {"error": "Word must be at least 3 letters"}

        game_state["secret_word"] = word
        for pid in game_state["player_ids"]:
            game_state["player_errors"][pid] = 0
        game_state["masked_word"] = make_masked(word, set())
        game_state["status"] = "in_progress"
        game_state["current_turn_id"] = get_next_active_guesser()
        turn_name = get_current_turn_name() or "Guesser"
        game_state["message"] = f"Round started. {turn_name}'s turn to guess."

        return 200, public_state_for(session_id)


def api_guess(payload):
    session_id = payload.get("sid", "")
    raw_guess = payload.get("guess", "")
    guess = normalize_word(raw_guess)

    with state_lock:
        if not ensure_session(session_id):
            return 401, {"error": "Invalid session"}
        if session_id not in game_state["player_ids"]:
            return 403, {"error": "Only joined players can submit guesses"}
        if session_id == get_current_setter_id():
            return 403, {"error": "Setter cannot guess this round"}
        if session_id != game_state["current_turn_id"]:
            return 403, {"error": "Not your turn"}
        if game_state["player_errors"].get(session_id, 0) >= game_state["max_errors"]:
            return 403, {"error": "You are out for this round"}
        if game_state["status"] != "in_progress":
            return 409, {"error": "Game is not in progress"}
        if not guess:
            return 400, {"error": "Guess cannot be empty"}

        word = game_state["secret_word"]
        guessed_set = set(game_state["guessed_letters"])
        wrong_set = set(game_state["wrong_letters"])

        if len(guess) == 1:
            letter = guess
            if letter in guessed_set or letter in wrong_set:
                return 409, {"error": "Letter already guessed"}
            if letter in word:
                guessed_set.add(letter)
                game_state["message"] = f"Correct letter: {letter}"
            else:
                wrong_set.add(letter)
                game_state["player_errors"][session_id] = game_state["player_errors"].get(session_id, 0) + 1
                next_turn = get_next_active_guesser(start_after_id=session_id)
                game_state["current_turn_id"] = next_turn
                if next_turn is not None:
                    game_state["message"] = f"Wrong letter: {letter}. Turn goes to {get_current_turn_name()}."
                else:
                    game_state["message"] = f"Wrong letter: {letter}."
        else:
            if guess == word:
                guessed_set.update(set(word))
                game_state["message"] = "Correct full-word guess!"
            else:
                guess_letters = set(guess)
                matched_letters = sorted(ch for ch in guess_letters if ch in word and ch not in guessed_set)

                if matched_letters:
                    guessed_set.update(matched_letters)
                    game_state["message"] = f"Your guess contains correct letters: {', '.join(matched_letters)}"
                else:
                    game_state["player_errors"][session_id] = game_state["player_errors"].get(session_id, 0) + 1
                    next_turn = get_next_active_guesser(start_after_id=session_id)
                    game_state["current_turn_id"] = next_turn
                    if next_turn is not None:
                        game_state["message"] = f"No matching letters found. Turn goes to {get_current_turn_name()}."
                    else:
                        game_state["message"] = "No matching letters found in that word guess."

        game_state["guessed_letters"] = sorted(guessed_set)
        game_state["wrong_letters"] = sorted(wrong_set)
        game_state["masked_word"] = make_masked(word, guessed_set)

        if "_" not in game_state["masked_word"]:
            game_state["status"] = "finished"
            game_state["winner"] = session_id
            winner_name = sessions.get(session_id, {}).get("name", "Player")
            game_state["scores"][session_id] = game_state["scores"].get(session_id, 0) + 1
            current_score = game_state["scores"][session_id]

            if current_score >= WIN_SCORE:
                game_state["match_winner"] = session_id
                game_state["message"] = (
                    f"{winner_name} solved the word and reached {current_score} points. "
                    "GAME OVER. Press Next Setter Round to start a new game."
                )
            else:
                next_setter_name = game_state["player_names"][(game_state["setter_index"] + 1) % len(game_state["player_ids"])]
                game_state["message"] = (
                    f"{winner_name} solved the word and earned 1 point "
                    f"({current_score}/{WIN_SCORE}). Next setter: {next_setter_name}."
                )
        else:
            active_guessers = [
                pid for pid in game_state["player_ids"]
                if pid != get_current_setter_id()
            ]
            all_out = active_guessers and all(
                game_state["player_errors"].get(pid, 0) >= game_state["max_errors"]
                for pid in active_guessers
            )

            if all_out:
                game_state["status"] = "finished"
                game_state["winner"] = "setter"
                next_setter_name = game_state["player_names"][(game_state["setter_index"] + 1) % len(game_state["player_ids"])]
                game_state["message"] = f"Round over. All guessers are out. Next setter: {next_setter_name}."

        return 200, public_state_for(session_id)


def api_reset(payload):
    session_id = payload.get("sid", "")
    with state_lock:
        if not ensure_session(session_id):
            return 401, {"error": "Invalid session"}
        if session_id not in game_state["player_ids"]:
            return 403, {"error": "Only joined players can start a new round"}
        if len(game_state["player_ids"]) < 2:
            return 409, {"error": "Need at least 2 players"}
        if game_state["status"] not in ("finished", "waiting_for_word"):
            return 409, {"error": "You can start next round after this round finishes"}

        # If match ended, keep the same multiplayer lobby and start a fresh game.
        if game_state["match_winner"] is not None:
            game_state["match_winner"] = None
            for pid in game_state["player_ids"]:
                game_state["scores"][pid] = 0
                game_state["player_errors"][pid] = 0

        rotate_setter()
        ensure_waiting_for_word_state()

        return 200, public_state_for(session_id)


def api_clear(payload):
    session_id = payload.get("sid", "")
    with state_lock:
        if not ensure_session(session_id):
            return 401, {"error": "Invalid session"}

        reset_multiplayer_state()
        return 200, {"ok": True, "message": "Multiplayer state cleared"}


def handle_api(method, path, body):
    parsed = urllib.parse.urlparse(path)
    query = urllib.parse.parse_qs(parsed.query)

    if method == "GET" and parsed.path == "/api/state":
        return api_state(query)

    if method != "POST":
        return 405, {"error": "Method not allowed"}

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return 400, {"error": "Invalid JSON body"}

    if parsed.path == "/api/join":
        return api_join(payload)
    if parsed.path == "/api/set-word":
        return api_set_word(payload)
    if parsed.path == "/api/guess":
        return api_guess(payload)
    if parsed.path == "/api/reset":
        return api_reset(payload)
    if parsed.path == "/api/clear":
        return api_clear(payload)

    return 404, {"error": "Unknown API route"}


def handle_connection(conn, addr):
    try:
        request = read_http_request(conn)
        if request is None:
            conn.sendall(make_response(400, {"error": "Bad request"}))
            return

        method, raw_path, _, body = request
        parsed = urllib.parse.urlparse(raw_path)

        if parsed.path.startswith("/api/"):
            status, payload = handle_api(method, raw_path, body)
            conn.sendall(make_response(status, payload))
            return

        if method != "GET":
            conn.sendall(make_response(405, {"error": "Method not allowed"}))
            return

        content, content_type = load_static(parsed.path)
        if content is None:
            conn.sendall(make_response(404, {"error": "Not found"}))
            return

        headers = [
            "HTTP/1.1 200 OK",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(content)}",
            "Connection: close",
            "Cache-Control: no-store",
            "",
            "",
        ]
        conn.sendall("\r\n".join(headers).encode("utf-8") + content)
    except Exception as exc:
        print(f"[SERVER] Error handling {addr}: {exc}")
        try:
            conn.sendall(make_response(500, {"error": "Internal server error"}))
        except OSError:
            pass
    finally:
        conn.close()


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(50)
    print(f"[SERVER] Web game listening on http://127.0.0.1:{PORT}")

    try:
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_connection, args=(conn, addr), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...")
    finally:
        server.close()


if __name__ == "__main__":
    start_server()
