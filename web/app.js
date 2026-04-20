const storage = window.sessionStorage;

const state = {
  sid: storage.getItem("word-duel-sid") || "",
  role: "",
  pollingId: null,
};

// Remove legacy shared-tab session storage to avoid multiplayer collisions.
localStorage.removeItem("word-duel-sid");

const els = {
  joinCard: document.getElementById("joinCard"),
  gameCard: document.getElementById("gameCard"),
  nameInput: document.getElementById("nameInput"),
  joinBtn: document.getElementById("joinBtn"),
  joinError: document.getElementById("joinError"),
  roleText: document.getElementById("roleText"),
  setterText: document.getElementById("setterText"),
  guesserText: document.getElementById("guesserText"),
  turnText: document.getElementById("turnText"),
  scoreText: document.getElementById("scoreText"),
  clearBtn: document.getElementById("clearBtn"),
  leaveBtn: document.getElementById("leaveBtn"),
  messageText: document.getElementById("messageText"),
  maskedWord: document.getElementById("maskedWord"),
  mistakesText: document.getElementById("mistakesText"),
  correctText: document.getElementById("correctText"),
  wrongText: document.getElementById("wrongText"),
  hangmanParts: [
    document.getElementById("hm-head"),
    document.getElementById("hm-body"),
    document.getElementById("hm-left-arm"),
    document.getElementById("hm-right-arm"),
    document.getElementById("hm-left-leg"),
    document.getElementById("hm-right-leg"),
  ],
  setterPanel: document.getElementById("setterPanel"),
  guesserPanel: document.getElementById("guesserPanel"),
  wordInput: document.getElementById("wordInput"),
  setWordBtn: document.getElementById("setWordBtn"),
  resetBtn: document.getElementById("resetBtn"),
  guessInput: document.getElementById("guessInput"),
  guessBtn: document.getElementById("guessBtn"),
  actionError: document.getElementById("actionError"),
};

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function getJson(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function formatRole(role) {
  if (role === "setter") return "Setter";
  if (role === "guesser") return "Guesser";
  return "Spectator";
}

function renderGame(s) {
  const playerNames = Array.isArray(s.players.names)
    ? s.players.names
    : [];
  const playerCount = Number.isFinite(s.players.count)
    ? s.players.count
    : playerNames.length;

  const scores = Array.isArray(s.players.scores) ? s.players.scores : [];
  const winScore = Number.isFinite(s.win_score) ? s.win_score : 3;
  const hasMatchWinner = Boolean(s.match_winner);
  const yourTurn = Boolean(s.your_turn);

  state.role = s.role;
  els.roleText.textContent = formatRole(s.role);
  els.setterText.textContent = s.players.current_setter || "-";
  els.guesserText.textContent = `${playerCount || 0} (${playerNames.join(", ") || "-"})`;
  els.turnText.textContent = s.current_turn || "-";
  els.scoreText.textContent = scores.length
    ? `First to ${winScore} points. `
      + scores.map((entry) => `${entry.name}: ${entry.score} pts, ${entry.mistakes || 0} mistakes`).join(" | ")
    : "No scores yet";
  els.messageText.textContent = s.message || "";
  els.maskedWord.textContent = s.masked_word || "_ _ _";
  els.mistakesText.textContent = `${s.incorrect_guesses} / ${s.max_errors}`;
  els.correctText.textContent = s.guessed_letters.length ? s.guessed_letters.join(", ") : "None";
  els.wrongText.textContent = s.wrong_letters.length ? s.wrong_letters.join(", ") : "None";

  const mistakes = Math.max(0, Number(s.incorrect_guesses) || 0);
  els.hangmanParts.forEach((part, index) => {
    if (!part) return;
    part.classList.toggle("show", index < mistakes);
  });

  const isSetter = s.role === "setter";
  const isGuesser = s.role === "guesser";
  const isInProgress = s.status === "in_progress";
  const isEliminated = Boolean(s.eliminated);
  const canSetWord = isSetter && s.status === "waiting_for_word";
  const canGuess = isGuesser && isInProgress && !isEliminated && yourTurn;

  els.setterPanel.classList.toggle("hidden", !canSetWord);
  els.guesserPanel.classList.toggle("hidden", !isGuesser);
  els.guessInput.disabled = !canGuess;
  els.guessBtn.disabled = !canGuess;
  els.resetBtn.classList.toggle("hidden", s.status !== "finished");
  els.resetBtn.textContent = hasMatchWinner ? "Start New Game" : "Next Setter Round";

  if (isEliminated && isInProgress) {
    els.actionError.textContent = "You are out for this round after reaching max mistakes.";
  } else if (isGuesser && isInProgress && !yourTurn) {
    els.actionError.textContent = "Wait for your turn.";
  } else if (els.actionError.textContent === "You are out for this round after reaching max mistakes.") {
    els.actionError.textContent = "";
  } else if (els.actionError.textContent === "Wait for your turn.") {
    els.actionError.textContent = "";
  }

  if (s.status === "finished" && s.word_revealed) {
    els.messageText.textContent = `${s.message} Secret word: ${s.word_revealed}`;
  }

  els.joinCard.classList.add("hidden");
  els.gameCard.classList.remove("hidden");
}

async function refreshState() {
  if (!state.sid) return;
  try {
    const data = await getJson(`/api/state?sid=${encodeURIComponent(state.sid)}`);
    renderGame(data);
    els.joinError.textContent = "";
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("invalid session")) {
      leaveSession();
      els.joinError.textContent = "Session was cleared. Please join again.";
      return;
    }

    els.joinError.textContent = err.message;
    clearInterval(state.pollingId);
    state.pollingId = null;
  }
}

function beginPolling() {
  if (state.pollingId) return;
  refreshState();
  state.pollingId = setInterval(refreshState, 1000);
}

function leaveSession() {
  state.sid = "";
  state.role = "";
  if (state.pollingId) {
    clearInterval(state.pollingId);
    state.pollingId = null;
  }

  storage.removeItem("word-duel-sid");
  localStorage.removeItem("word-duel-sid");

  els.actionError.textContent = "";
  els.joinError.textContent = "";
  els.gameCard.classList.add("hidden");
  els.joinCard.classList.remove("hidden");
}

els.joinBtn.addEventListener("click", async () => {
  const name = els.nameInput.value.trim();
  els.joinError.textContent = "";
  if (!name) {
    els.joinError.textContent = "Please enter your name.";
    return;
  }

  try {
    const data = await postJson("/api/join", { name });
    state.sid = data.session_id;
    storage.setItem("word-duel-sid", state.sid);
    renderGame(data.state);
    beginPolling();
  } catch (err) {
    els.joinError.textContent = err.message;
  }
});

els.setWordBtn.addEventListener("click", async () => {
  els.actionError.textContent = "";
  const word = els.wordInput.value.trim();
  if (!word) {
    els.actionError.textContent = "Enter a word first.";
    return;
  }

  try {
    const data = await postJson("/api/set-word", { sid: state.sid, word });
    renderGame(data);
    els.wordInput.value = "";
  } catch (err) {
    els.actionError.textContent = err.message;
  }
});

els.resetBtn.addEventListener("click", async () => {
  els.actionError.textContent = "";
  try {
    const data = await postJson("/api/reset", { sid: state.sid });
    renderGame(data);
  } catch (err) {
    els.actionError.textContent = err.message;
  }
});

els.guessBtn.addEventListener("click", async () => {
  els.actionError.textContent = "";
  const guess = els.guessInput.value.trim();
  if (!guess) {
    els.actionError.textContent = "Enter a guess first.";
    return;
  }

  try {
    const data = await postJson("/api/guess", { sid: state.sid, guess });
    renderGame(data);
    els.guessInput.value = "";
  } catch (err) {
    els.actionError.textContent = err.message;
  }
});

els.leaveBtn.addEventListener("click", leaveSession);

els.clearBtn.addEventListener("click", async () => {
  els.actionError.textContent = "";
  try {
    await postJson("/api/clear", { sid: state.sid });
    leaveSession();
    els.joinError.textContent = "Multiplayer cleared. All players must join again.";
  } catch (err) {
    els.actionError.textContent = err.message;
  }
});

if (state.sid) {
  beginPolling();
}
