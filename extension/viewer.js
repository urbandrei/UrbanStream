(function () {
  const EBS_BASE = "https://extrusive-unprelatic-millie.ngrok-free.dev";
  const POLL_INTERVAL = 2000;

  let authToken = "";
  let userId = "";
  let currentPlate = "";
  let pollTimer = null;
  let countdownTimer = null;
  let remainingSeconds = 0;

  const minigame = document.getElementById("minigame");
  const plateText = document.getElementById("plate-text");
  const input = document.getElementById("input");
  const timer = document.getElementById("timer");
  const score = document.getElementById("score");
  const feedback = document.getElementById("feedback");

  function formatTime(s) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m + ":" + (sec < 10 ? "0" : "") + sec;
  }

  function startCountdown(seconds) {
    remainingSeconds = seconds;
    timer.textContent = formatTime(remainingSeconds);
    clearInterval(countdownTimer);
    countdownTimer = setInterval(function () {
      remainingSeconds = Math.max(0, remainingSeconds - 1);
      timer.textContent = formatTime(remainingSeconds);
      if (remainingSeconds <= 0) {
        clearInterval(countdownTimer);
      }
    }, 1000);
  }

  function showFeedback(correct) {
    feedback.textContent = correct ? "Correct! Time reduced!" : "Wrong, try again!";
    feedback.className = correct ? "feedback-correct" : "feedback-wrong";
    setTimeout(function () {
      feedback.textContent = "";
      feedback.className = "";
    }, 1500);
  }

  async function checkStatus() {
    try {
      const resp = await fetch(
        EBS_BASE + "/api/extension/jail-status?user_id=" + encodeURIComponent(userId)
      );
      const data = await resp.json();

      if (data.jailed) {
        minigame.classList.remove("hidden");
        currentPlate = data.plate;
        plateText.textContent = data.plate;
        score.textContent = "Plates: " + data.completed;
        startCountdown(data.remaining);
      } else {
        minigame.classList.add("hidden");
        clearInterval(countdownTimer);
      }
    } catch (e) {
      // EBS unreachable, hide minigame
      minigame.classList.add("hidden");
    }
  }

  async function submitAnswer(answer) {
    try {
      const resp = await fetch(EBS_BASE + "/api/extension/plate-complete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-extension-jwt": authToken,
        },
        body: JSON.stringify({ answer: answer }),
      });
      const data = await resp.json();
      showFeedback(data.correct);

      if (data.correct) {
        currentPlate = data.next_plate;
        plateText.textContent = data.next_plate;
        score.textContent = "Plates: " + data.completed;
        startCountdown(data.remaining);
      }
    } catch (e) {
      // Ignore network errors
    }
  }

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      const val = input.value.trim();
      if (val) {
        submitAnswer(val);
        input.value = "";
      }
    }
  });

  // Auto-submit when input matches plate length
  input.addEventListener("input", function () {
    const val = input.value.trim().toUpperCase();
    if (val.length === currentPlate.length && currentPlate.length > 0) {
      submitAnswer(val);
      input.value = "";
    }
  });

  window.Twitch.ext.onAuthorized(function (auth) {
    authToken = auth.token;
    userId = auth.userId;

    // Start polling for jail status
    checkStatus();
    pollTimer = setInterval(checkStatus, POLL_INTERVAL);
  });
})();
