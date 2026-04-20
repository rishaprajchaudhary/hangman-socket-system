import json
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    import pygame
except ImportError:
    print("Pygame is required for this client. Install it with: pip install pygame")
    sys.exit(1)


API_BASE = "http://127.0.0.1:5555"
WINDOW_W = 1100
WINDOW_H = 760
POLL_EVENT = pygame.USEREVENT + 1
POLL_MS = 1000


class ApiError(Exception):
    pass


def api_get(path):
    req = urllib.request.Request(f"{API_BASE}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8") if err.fp else ""
        try:
            payload = json.loads(body)
            raise ApiError(payload.get("error", f"HTTP {err.code}"))
        except json.JSONDecodeError:
            raise ApiError(f"HTTP {err.code}")
    except urllib.error.URLError:
        raise ApiError("Server not reachable")


def api_post(path, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8") if err.fp else ""
        try:
            payload = json.loads(body)
            raise ApiError(payload.get("error", f"HTTP {err.code}"))
        except json.JSONDecodeError:
            raise ApiError(f"HTTP {err.code}")
    except urllib.error.URLError:
        raise ApiError("Server not reachable")


def draw_hangman(surface, x, y, mistakes):
    color = (74, 47, 32)
    w = 5

    pygame.draw.line(surface, color, (x + 20, y + 220), (x + 160, y + 220), w)
    pygame.draw.line(surface, color, (x + 55, y + 220), (x + 55, y + 20), w)
    pygame.draw.line(surface, color, (x + 55, y + 20), (x + 150, y + 20), w)
    pygame.draw.line(surface, color, (x + 150, y + 20), (x + 150, y + 48), w)

    if mistakes >= 1:
        pygame.draw.circle(surface, color, (x + 150, y + 68), 18, w)
    if mistakes >= 2:
        pygame.draw.line(surface, color, (x + 150, y + 86), (x + 150, y + 140), w)
    if mistakes >= 3:
        pygame.draw.line(surface, color, (x + 150, y + 100), (x + 124, y + 124), w)
    if mistakes >= 4:
        pygame.draw.line(surface, color, (x + 150, y + 100), (x + 176, y + 124), w)
    if mistakes >= 5:
        pygame.draw.line(surface, color, (x + 150, y + 140), (x + 126, y + 176), w)
    if mistakes >= 6:
        pygame.draw.line(surface, color, (x + 150, y + 140), (x + 174, y + 176), w)


def draw_wrapped_text(surface, text, font, color, rect):
    words = text.split(" ")
    line = ""
    y = rect.top
    for word in words:
        test = f"{line} {word}".strip()
        if font.size(test)[0] <= rect.width:
            line = test
            continue

        img = font.render(line, True, color)
        surface.blit(img, (rect.left, y))
        y += img.get_height() + 4
        line = word

    if line:
        img = font.render(line, True, color)
        surface.blit(img, (rect.left, y))


class PygameClient:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Word Duel - Pygame Client")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()

        self.font_title = pygame.font.SysFont("consolas", 46, bold=True)
        self.font_big = pygame.font.SysFont("consolas", 34, bold=True)
        self.font = pygame.font.SysFont("consolas", 24)
        self.font_small = pygame.font.SysFont("consolas", 20)

        self.running = True
        self.sid = ""
        self.state = None
        self.name_input = ""
        self.action_input = ""
        self.error_text = ""
        self.info_text = "Enter your name and press Enter to join"

        pygame.time.set_timer(POLL_EVENT, POLL_MS)

    def refresh_state(self):
        if not self.sid:
            return
        try:
            self.state = api_get(f"/api/state?sid={urllib.parse.quote(self.sid)}")
            self.error_text = ""
        except ApiError as err:
            if "Invalid session" in str(err):
                self.sid = ""
                self.state = None
                self.error_text = "Session invalid. Join again."
            else:
                self.error_text = str(err)

    def join(self):
        name = self.name_input.strip()
        if not name:
            self.error_text = "Name is required"
            return
        try:
            data = api_post("/api/join", {"name": name})
            self.sid = data["session_id"]
            self.state = data["state"]
            self.error_text = ""
            self.info_text = "Joined."
        except ApiError as err:
            self.error_text = str(err)

    def submit_action(self):
        if not self.sid or not self.state:
            return

        text = self.action_input.strip()
        role = self.state.get("role")
        status = self.state.get("status")

        try:
            if role == "setter" and status == "waiting_for_word":
                if not text:
                    self.error_text = "Enter a word first"
                    return
                self.state = api_post("/api/set-word", {"sid": self.sid, "word": text})
                self.action_input = ""
                self.error_text = ""
                return

            if role == "guesser" and status == "in_progress":
                if not text:
                    self.error_text = "Enter a guess first"
                    return
                self.state = api_post("/api/guess", {"sid": self.sid, "guess": text})
                self.action_input = ""
                self.error_text = ""
                return

            self.error_text = "No action available for your role/state"
        except ApiError as err:
            self.error_text = str(err)

    def next_round(self):
        if not self.sid:
            return
        try:
            self.state = api_post("/api/reset", {"sid": self.sid})
            self.error_text = ""
        except ApiError as err:
            self.error_text = str(err)

    def clear_multiplayer(self):
        if not self.sid:
            return
        try:
            api_post("/api/clear", {"sid": self.sid})
            self.sid = ""
            self.state = None
            self.error_text = ""
            self.info_text = "Multiplayer cleared. Join again."
            self.action_input = ""
        except ApiError as err:
            self.error_text = str(err)

    def draw_join_screen(self):
        self.screen.fill((255, 246, 234))
        title = self.font_title.render("Word Duel - Pygame Client", True, (31, 36, 41))
        self.screen.blit(title, (40, 34))

        subtitle = self.font.render("Current server API multiplayer client", True, (95, 104, 114))
        self.screen.blit(subtitle, (42, 90))

        box = pygame.Rect(40, 160, 620, 58)
        pygame.draw.rect(self.screen, (255, 254, 249), box, border_radius=10)
        pygame.draw.rect(self.screen, (233, 220, 199), box, width=2, border_radius=10)

        txt = self.font.render(self.name_input or "Enter name...", True, (31, 36, 41))
        self.screen.blit(txt, (52, 174))

        hint = self.font_small.render("Press Enter to join", True, (95, 104, 114))
        self.screen.blit(hint, (40, 236))

        info = self.font_small.render(self.info_text, True, (24, 80, 42))
        self.screen.blit(info, (40, 280))

        if self.error_text:
            err = self.font_small.render(self.error_text, True, (197, 48, 48))
            self.screen.blit(err, (40, 310))

    def draw_game_screen(self):
        s = self.state or {}
        players = s.get("players", {})
        scores = players.get("scores", [])

        self.screen.fill((255, 246, 234))

        title = self.font_title.render("Word Duel", True, (31, 36, 41))
        self.screen.blit(title, (40, 20))

        role_line = f"Role: {s.get('role', '-') }"
        setter_line = f"Setter: {players.get('current_setter', '-') }"
        names = players.get("names", [])
        names_line = f"Players ({players.get('count', 0)}): {', '.join(names) if names else '-'}"
        self.screen.blit(self.font.render(role_line, True, (31, 36, 41)), (40, 90))
        self.screen.blit(self.font.render(setter_line, True, (31, 36, 41)), (360, 90))
        self.screen.blit(self.font.render(names_line, True, (31, 36, 41)), (40, 126))

        score_text = " | ".join([f"{x.get('name')}: {x.get('score')}" for x in scores]) or "No scores"
        win_score = s.get("win_score", 3)
        self.screen.blit(self.font.render(f"First to {win_score}: {score_text}", True, (31, 36, 41)), (40, 162))

        msg_rect = pygame.Rect(40, 202, WINDOW_W - 80, 72)
        pygame.draw.rect(self.screen, (255, 245, 234), msg_rect, border_radius=8)
        pygame.draw.rect(self.screen, (255, 122, 61), msg_rect, width=2, border_radius=8)
        draw_wrapped_text(self.screen, s.get("message", ""), self.font_small, (31, 36, 41), msg_rect.inflate(-14, -10))

        draw_hangman(self.screen, 80, 290, int(s.get("incorrect_guesses", 0)))

        masked = s.get("masked_word", "_ _ _")
        masked_img = self.font_big.render(masked, True, (31, 36, 41))
        self.screen.blit(masked_img, (430, 330))

        stats = f"Your mistakes: {s.get('incorrect_guesses', 0)} / {s.get('max_errors', 6)}"
        self.screen.blit(self.font.render(stats, True, (31, 36, 41)), (430, 388))

        correct = ", ".join(s.get("guessed_letters", [])) or "None"
        wrong = ", ".join(s.get("wrong_letters", [])) or "None"
        self.screen.blit(self.font_small.render(f"Correct: {correct}", True, (31, 36, 41)), (430, 424))
        self.screen.blit(self.font_small.render(f"Wrong: {wrong}", True, (31, 36, 41)), (430, 452))

        input_rect = pygame.Rect(40, 560, WINDOW_W - 80, 56)
        pygame.draw.rect(self.screen, (255, 254, 249), input_rect, border_radius=10)
        pygame.draw.rect(self.screen, (233, 220, 199), input_rect, width=2, border_radius=10)

        role = s.get("role")
        status = s.get("status")
        if role == "setter" and status == "waiting_for_word":
            prompt = "Type word and press Enter"
        elif role == "guesser" and status == "in_progress":
            prompt = "Type guess and press Enter"
        else:
            prompt = "No text action now"

        shown = self.action_input or prompt
        self.screen.blit(self.font.render(shown, True, (31, 36, 41)), (52, 576))

        hint = "Enter: submit  |  Ctrl+N: next round/new game  |  Ctrl+C: clear multiplayer  |  Ctrl+L: leave"
        self.screen.blit(self.font_small.render(hint, True, (95, 104, 114)), (40, 638))

        if self.error_text:
            err = self.font_small.render(self.error_text, True, (197, 48, 48))
            self.screen.blit(err, (40, 668))

        if status == "finished" and s.get("word_revealed"):
            final_text = f"Secret word: {s.get('word_revealed')}"
            self.screen.blit(self.font_small.render(final_text, True, (24, 80, 42)), (40, 698))

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == POLL_EVENT:
                    self.refresh_state()

                elif event.type == pygame.KEYDOWN:
                    is_ctrl = (event.mod & pygame.KMOD_CTRL) != 0

                    if event.key == pygame.K_ESCAPE:
                        self.running = False

                    elif is_ctrl and event.key == pygame.K_l:
                        self.sid = ""
                        self.state = None
                        self.action_input = ""
                        self.error_text = ""

                    elif is_ctrl and event.key == pygame.K_c:
                        self.clear_multiplayer()

                    elif is_ctrl and event.key == pygame.K_n:
                        self.next_round()

                    elif event.key == pygame.K_RETURN:
                        if not self.sid:
                            self.join()
                        else:
                            self.submit_action()

                    elif event.key == pygame.K_BACKSPACE:
                        if not self.sid:
                            self.name_input = self.name_input[:-1]
                        else:
                            self.action_input = self.action_input[:-1]

                    else:
                        if event.unicode and event.unicode.isprintable():
                            if not self.sid:
                                if len(self.name_input) < 24:
                                    self.name_input += event.unicode
                            else:
                                if len(self.action_input) < 48:
                                    self.action_input += event.unicode

            if not self.sid:
                self.draw_join_screen()
            else:
                self.draw_game_screen()

            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


def main():
    client = PygameClient()
    client.run()


if __name__ == "__main__":
    main()
