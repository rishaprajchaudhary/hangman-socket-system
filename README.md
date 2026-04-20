# Word Duel - Web UI with Python Sockets

This project is now a web-based multiplayer word game implemented with pure Python socket programming.

No FastAPI, Flask, or third-party framework is used.

## Game Rules

1. Players join the same match from multiple browser tabs/devices.
2. One player is the setter for the round; others are guessers.
3. Setter enters a secret word and guessers try letters or full-word guesses.
4. Guessers play in sequence; after a wrong guess, turn moves to next guesser.
5. The player who solves the word earns 1 point.
6. First player to 3 points wins the match.
7. After each round, setter rotates to the next player.
8. After GAME OVER, use "Next Setter Round" to start a new game with same players.

## What was added

- Socket-based HTTP server in Python (`server.py`)
- Browser UI/UX (`web/index.html`, `web/styles.css`, `web/app.js`)
- Turn-based multiplayer mode with rotating setter and scoring
- JSON API endpoints for join, state, set-word, guess, and reset

## Run Locally

1. Start the server:

```bash
python server.py
```

2. Open browser tabs/windows:

- `http://127.0.0.1:5555`
- Open this URL in two windows (or two devices on same network)

3. Play:

- Open the URL in multiple windows/devices
- Current setter sets a word and starts the round
- Other players guess letters/words
- Click "Next Setter Round" after round finish

## Notes

- Default max mistakes is 6.
