import json
import os
import subprocess
import sys
import tempfile
import wave
from io import BytesIO
from pathlib import Path

import lameenc
from flask import Flask, jsonify, render_template, request, send_file

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
VOICES_DIR = BASE_DIR / "voices"

app = Flask(__name__)

TRANSLATION_ENABLED = os.environ.get("ENABLE_TRANSLATION", "1") != "0"

_en_to_hi_translation = None
_en_to_hi_translation_loaded = False


def get_en_hi_translation():
    global _en_to_hi_translation, _en_to_hi_translation_loaded
    if not _en_to_hi_translation_loaded:
        import argostranslate.translate

        installed_languages = argostranslate.translate.get_installed_languages()
        en = next((lang for lang in installed_languages if lang.code == "en"), None)
        hi = next((lang for lang in installed_languages if lang.code == "hi"), None)
        _en_to_hi_translation = en.get_translation(hi) if en and hi else None
        _en_to_hi_translation_loaded = True
    return _en_to_hi_translation


def list_voices():
    voices = []
    for onnx_path in sorted(VOICES_DIR.glob("*.onnx")):
        config_path = onnx_path.with_suffix(".onnx.json")
        if not config_path.exists():
            continue
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        num_speakers = config.get("num_speakers", 1)
        voices.append(
            {
                "id": onnx_path.stem,
                "label": onnx_path.stem.replace("_", " ").replace("-", " · "),
                "language": config.get("language", {}).get("name_english", ""),
                "num_speakers": num_speakers,
            }
        )
    return voices


def wav_to_mp3(wav_bytes):
    with wave.open(BytesIO(wav_bytes), "rb") as w:
        channels = w.getnchannels()
        sample_rate = w.getframerate()
        sample_width = w.getsampwidth()
        pcm = w.readframes(w.getnframes())

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)

    if sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV is supported for MP3 conversion.")

    mp3_data = encoder.encode(pcm)
    mp3_data += encoder.flush()
    return mp3_data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/voices")
def api_voices():
    return jsonify(list_voices())


@app.route("/api/config")
def api_config():
    return jsonify({"translation_enabled": TRANSLATION_ENABLED})


@app.route("/api/translate", methods=["POST"])
def api_translate():
    if not TRANSLATION_ENABLED:
        return jsonify({"error": "Auto-translation is not available on this deployment. Please type Hindi text directly."}), 503

    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"error": "Text is required."}), 400

    translation = get_en_hi_translation()
    if translation is None:
        return jsonify({"error": "English-to-Hindi translation model is not installed."}), 500

    translated = translation.translate(text)
    return jsonify({"translated": translated})


@app.route("/api/speak", methods=["POST"])
def api_speak():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    voice_id = data.get("voice")
    speed = float(data.get("speed", 1.0))
    speaker = int(data.get("speaker", 0))
    audio_format = (data.get("format") or "wav").lower()

    if audio_format not in ("wav", "mp3"):
        return jsonify({"error": "Format must be 'wav' or 'mp3'."}), 400

    if not text:
        return jsonify({"error": "Text is required."}), 400

    model_path = VOICES_DIR / f"{voice_id}.onnx"
    config_path = VOICES_DIR / f"{voice_id}.onnx.json"
    if not model_path.exists() or not config_path.exists():
        return jsonify({"error": "Unknown voice."}), 400

    length_scale = 1.0 / max(0.25, min(speed, 4.0))

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "output.wav"
        cmd = [
            sys.executable,
            "-m",
            "piper",
            "-m",
            str(model_path),
            "-c",
            str(config_path),
            "-f",
            str(out_path),
            "-s",
            str(speaker),
            "--length-scale",
            str(length_scale),
        ]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            cmd,
            input=text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
        )
        if result.returncode != 0 or not out_path.exists():
            return jsonify({"error": result.stderr or "Speech generation failed."}), 500

        audio_bytes = out_path.read_bytes()

    if audio_format == "mp3":
        try:
            audio_bytes = wav_to_mp3(audio_bytes)
        except ValueError as e:
            return jsonify({"error": str(e)}), 500
        return send_file(
            BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="speech.mp3",
        )

    return send_file(
        BytesIO(audio_bytes),
        mimetype="audio/wav",
        as_attachment=False,
        download_name="speech.wav",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
