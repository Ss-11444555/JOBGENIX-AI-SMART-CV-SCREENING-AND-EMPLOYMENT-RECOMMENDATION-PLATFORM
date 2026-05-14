import os
import time
import wave
import tempfile
import winsound

import pyaudio
import requests
from dotenv import load_dotenv
from openai import OpenAI


# ==========================================================
# 1. CONFIG
# ==========================================================

# Load OPENAI_API_KEY from .env
# .env file must be in the SAME FOLDER as this script.
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY not found.\n"
        "Create a .env file next to interview_ai.py with:\n"
        "OPENAI_API_KEY=sk-...."
    )

client = OpenAI(api_key=OPENAI_API_KEY)

# Your local prediction API (Flask app.py must be running)
PREDICT_API_URL = "http://127.0.0.1:5000/api/predict"

# Audio recording settings
RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024
RECORD_SECONDS = 10         # how long each answer recording lasts
INPUT_WAV = "user_question.wav"
OUTPUT_WAV = "ai_reply.wav"


# ==========================================================
# 2. AUDIO HELPERS
# ==========================================================

def record_microphone_to_wav(filename: str, seconds: int = RECORD_SECONDS):
    """Record audio from default microphone into a WAV file."""
    print(f"\n[ ] Recording for {seconds} seconds... Speak now.")
    pa = pyaudio.PyAudio()

    stream = pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )

    frames = []
    for _ in range(0, int(RATE / CHUNK) * seconds):
        data = stream.read(CHUNK)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    pa.terminate()

    # Save to WAV
    wf = wave.open(filename, "wb")
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b"".join(frames))
    wf.close()
    print("[ ] Recording finished.")


def play_wav(path: str):
    """Play a WAV file from disk using winsound."""
    if not os.path.exists(path):
        print(f"[ ] Audio file not found: {path}")
        return
    winsound.PlaySound(path, winsound.SND_FILENAME)


# ==========================================================
# 3. OPENAI HELPERS (STT, CHAT, TTS)
# ==========================================================

def transcribe_audio(filename: str) -> str:
    """Use OpenAI Audio API to transcribe a WAV file to text."""
    print("[ ] Transcribing your answer...")
    with open(filename, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",  # speech-to-text model
            file=f,
        )
    text = transcript.text.strip()
    print(f"[YOU SAID] {text}")
    return text


def interview_ai_reply(history, user_text: str) -> str:
    """
    Use GPT as an interviewer: evaluates your answer and asks next question.
    `history` is a list of chat messages to preserve context.
    """
    history.append({"role": "user", "content": user_text})

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=history,
        temperature=0.7,
    )

    reply = completion.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    return reply


def text_to_speech_to_wav(text: str, filename: str):
    """
    Convert text reply to spoken audio and save as WAV.

    IMPORTANT: client.audio.speech.create() returns a BinaryResponse,
    so we use .stream_to_file() to write to disk.
    """
    print("[ ] Generating AI voice...")
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text,
        format="wav",
    )

    # Save audio directly to a WAV file
    response.stream_to_file(filename)


def call_prediction_api_from_text(user_text: str):
    """
    OPTIONAL: very simple heuristic to call your /api/predict endpoint.
    Right now we just send the full text as 'skills' and assume
    3 years exp + Bachelor CS. You can improve later.
    """
    try:
        skills = user_text
        education = "Bachelor in Computer Science"
        experience_years = 3

        payload = {
            "skills": skills,
            "education": education,
            "experience_years": experience_years,
        }
        r = requests.post(PREDICT_API_URL, json=payload, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[ ] Prediction API error {r.status_code}: {r.text}")
            return None
    except Exception as e:
        print(f"[ ] Could not call prediction API: {e}")
        return None


# ==========================================================
# 4. MAIN INTERVIEW LOOP
# ==========================================================

def run_interview():
    print("===============================================")
    print("        JobGenix AI – Voice Interview")
    print("===============================================")
    print("Controls:")
    print(" - Each round I will ask you a question.")
    print(" - You answer by speaking. I record ~10 seconds.")
    print(" - Say 'stop interview' to finish.\n")

    # System prompt: how the AI should behave
    history = [
        {
            "role": "system",
            "content": (
                "You are an AI technical interviewer for IT jobs. "
                "Interview the candidate, ask one question at a time, "
                "give short feedback about their answer, "
                "and then ask the next question. "
                "Focus on software engineering, data, cloud, etc. "
                "Keep answers under 4 sentences."
            ),
        }
    ]

    # First question from AI (text only)
    first_question = interview_ai_reply(history, "Start the interview with the first question.")
    print(f"\n[AI] {first_question}")
    text_to_speech_to_wav(first_question, OUTPUT_WAV)
    play_wav(OUTPUT_WAV)

    while True:
        input("\nPress ENTER when you're ready to answer...")
        record_microphone_to_wav(INPUT_WAV, RECORD_SECONDS)

        # Transcribe
        user_text = transcribe_audio(INPUT_WAV)

        if user_text.lower().strip() in ["stop interview", "quit", "exit"]:
            print("\n[AI] Thank you! The interview is finished.")
            break

        # (Optional) call your prediction API using the answer
        prediction = call_prediction_api_from_text(user_text)
        if prediction:
            print(f"[PREDICTION API] {prediction}")

        # Get AI reply (feedback + next question)
        ai_reply = interview_ai_reply(history, user_text)
        print(f"\n[AI] {ai_reply}")

        # Speak it out
        text_to_speech_to_wav(ai_reply, OUTPUT_WAV)
        play_wav(OUTPUT_WAV)

        time.sleep(1)

    print("\nInterview session ended.")


if __name__ == "__main__":
    run_interview()
