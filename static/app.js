const textEl = document.getElementById("text");
const translationField = document.getElementById("translation-field");
const translationEl = document.getElementById("translation");
const voiceEl = document.getElementById("voice");
const speakerField = document.getElementById("speaker-field");
const speakerEl = document.getElementById("speaker");
const speedEl = document.getElementById("speed");
const speedValueEl = document.getElementById("speed-value");
const speakBtn = document.getElementById("speak-btn");
const downloadWavBtn = document.getElementById("download-wav-btn");
const downloadMp3Btn = document.getElementById("download-mp3-btn");
const statusEl = document.getElementById("status");
const playerEl = document.getElementById("player");

const DEVANAGARI_RE = /[ऀ-ॿ]/;

let voices = [];
let currentAudioUrl = null;
let lastParams = null;
let lastTranslatedSource = null;

function needsHindiTranslation(text) {
  const voice = voices.find((v) => v.id === voiceEl.value);
  return Boolean(voice && voice.language === "Hindi" && !DEVANAGARI_RE.test(text));
}

async function resolveSpokenText(text) {
  if (!needsHindiTranslation(text)) {
    translationField.style.display = "none";
    lastTranslatedSource = null;
    return text;
  }

  translationField.style.display = "flex";

  if (lastTranslatedSource !== text) {
    statusEl.textContent = "Translating to Hindi...";
    const res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to translate text.");
    }

    const { translated } = await res.json();
    translationEl.value = translated;
    lastTranslatedSource = text;
  }

  return translationEl.value.trim();
}

async function loadVoices() {
  const res = await fetch("/api/voices");
  voices = await res.json();

  if (voices.length === 0) {
    statusEl.textContent = "No voices found in the voices/ folder.";
    speakBtn.disabled = true;
    return;
  }

  voiceEl.innerHTML = voices
    .map((v) => `<option value="${v.id}">${v.label}${v.language ? " (" + v.language + ")" : ""}</option>`)
    .join("");

  updateSpeakerOptions();
}

function updateSpeakerOptions() {
  const voice = voices.find((v) => v.id === voiceEl.value);
  if (voice && voice.num_speakers > 1) {
    speakerField.style.display = "flex";
    speakerEl.innerHTML = Array.from({ length: voice.num_speakers }, (_, i) => `<option value="${i}">Speaker ${i}</option>`).join("");
  } else {
    speakerField.style.display = "none";
    speakerEl.innerHTML = "";
  }
}

voiceEl.addEventListener("change", () => {
  updateSpeakerOptions();
  if (!needsHindiTranslation(textEl.value.trim())) {
    translationField.style.display = "none";
    lastTranslatedSource = null;
  }
});

speedEl.addEventListener("input", () => {
  speedValueEl.textContent = `${parseFloat(speedEl.value).toFixed(1)}x`;
});

speakBtn.addEventListener("click", async () => {
  const text = textEl.value.trim();
  if (!text) {
    statusEl.textContent = "Please enter some text first.";
    return;
  }

  speakBtn.disabled = true;
  downloadWavBtn.style.display = "none";
  downloadMp3Btn.style.display = "none";

  try {
    const spokenText = await resolveSpokenText(text);
    if (!spokenText) {
      throw new Error("Translation returned empty text.");
    }

    lastParams = {
      text: spokenText,
      voice: voiceEl.value,
      speaker: speakerEl.value || 0,
      speed: speedEl.value,
    };

    statusEl.textContent = "Generating speech...";

    const res = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...lastParams, format: "wav" }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to generate speech.");
    }

    const blob = await res.blob();
    if (currentAudioUrl) {
      URL.revokeObjectURL(currentAudioUrl);
    }
    currentAudioUrl = URL.createObjectURL(blob);

    playerEl.src = currentAudioUrl;
    playerEl.style.display = "block";
    playerEl.play();

    downloadWavBtn.href = currentAudioUrl;
    downloadWavBtn.style.display = "inline-block";
    downloadMp3Btn.style.display = "inline-block";

    statusEl.textContent = "Done.";
  } catch (e) {
    statusEl.textContent = `Error: ${e.message}`;
  } finally {
    speakBtn.disabled = false;
  }
});

downloadMp3Btn.addEventListener("click", async () => {
  if (!lastParams) return;

  downloadMp3Btn.disabled = true;
  statusEl.textContent = "Encoding MP3...";

  try {
    const res = await fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...lastParams, format: "mp3" }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Failed to encode MP3.");
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "speech.mp3";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    statusEl.textContent = "MP3 downloaded.";
  } catch (e) {
    statusEl.textContent = `Error: ${e.message}`;
  } finally {
    downloadMp3Btn.disabled = false;
  }
});

loadVoices();
