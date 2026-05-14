import os
import time
import wave
import tempfile
import winsound
import json

import pyaudio
import requests
from dotenv import load_dotenv
from openai import OpenAI

# ==========================================================
# 1. CONFIG
# ==========================================================

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY not found.\n"
        "Create a .env file next to this script with:\n"
        "OPENAI_API_KEY=your_openai_api_key_here"
    )

client = OpenAI(api_key=OPENAI_API_KEY)

# Your local prediction API (Flask app.py must be running)
PREDICT_API_URL = "http://127.0.0.1:5000/api/predict"

# Audio recording settings
RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024
RECORD_SECONDS = 10
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

    wf = wave.open(filename, "wb")
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b"".join(frames))
    wf.close()
    print("[ ] Recording finished.")


def play_wav(path: str):
    """Play a WAV file using winsound (Windows only)."""
    if not os.path.exists(path):
        print(f"[ ] WAV file not found: {path}")
        return
    winsound.PlaySound(path, winsound.SND_FILENAME)


def play_audio_bytes(audio_bytes: bytes):
    """Play WAV audio bytes by saving to a temp file then using winsound."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        temp_path = tmp.name

    try:
        winsound.PlaySound(temp_path, winsound.SND_FILENAME)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ==========================================================
# 3. OPENAI HELPERS (STT, CHAT, TTS)
# ==========================================================

def transcribe_audio(filename: str) -> str:
    """Use OpenAI Audio API to transcribe a WAV file to text."""
    print("[ ] Transcribing your answer...")
    with open(filename, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
        )
    text = transcript.text.strip()
    print(f"[YOU SAID] {text}")
    return text


def text_to_speech_to_wav(text: str, filename: str):
    """Convert text reply to spoken audio and save as a WAV file."""
    print("[ ] Generating AI voice...")
    
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text,
            response_format="wav",
        )
        
        with open(filename, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)
                
        print(f"[ ] Audio saved to {filename}")
        
    except Exception as e:
        print(f"[ ] Error generating speech: {e}")
        raise


def generate_interview_question(history, job_role: str, question_number: int):
    """
    Generate intelligent interview questions based on job role and conversation history.
    """
    system_prompt = f"""
    You are an expert technical interviewer for IT positions. Your role is to conduct a structured technical interview for a {job_role} position.

    INTERVIEW STRUCTURE:
    - Ask exactly 5 technical questions total
    - Each question should be relevant to {job_role} role
    - Questions should progress from fundamental to advanced concepts
    - Focus on practical skills, problem-solving, and real-world scenarios
    - After each answer, provide brief constructive feedback and ask the next question
    - Keep questions clear and concise

    CURRENT PROGRESS: Question {question_number}/5

    IMPORTANT: 
    - Always include the question number in your response
    - Provide brief feedback on the previous answer before asking the next question
    - Make sure questions are job-specific and technical
    - End your response with the next question
    """

    # If it's the first question, use a starter prompt
    if question_number == 1:
        user_prompt = f"Start the technical interview for {job_role} position. Ask the first technical question."
    else:
        user_prompt = "Based on the conversation history, provide brief feedback and ask the next appropriate technical question."

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_prompt}
    ]

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.7,
        max_tokens=500
    )

    reply = completion.choices[0].message.content.strip()
    return reply


def generate_interview_review(job_role: str, interview_data: list):
    """
    Generate a comprehensive review and pass/fail assessment of the interview.
    """
    system_prompt = f"""
    You are an experienced HR manager and technical hiring expert. Your task is to provide a comprehensive assessment of a candidate's performance in a technical interview for a {job_role} position.

    ASSESSMENT CRITERIA:
    1. Technical Knowledge (40%) - Understanding of core concepts
    2. Problem-Solving Skills (30%) - Ability to think critically and solve problems
    3. Communication Skills (20%) - Clarity and structure in responses
    4. Confidence & Honesty (10%) - Willingness to admit when unsure

    INTERVIEW DATA:
    {json.dumps(interview_data, indent=2)}

    Provide a detailed assessment with:
    - Overall score (0-100)
    - Pass/Fail recommendation
    - Strengths identified
    - Areas for improvement
    - Detailed breakdown per question
    - Final hiring recommendation

    Be honest but constructive in your feedback.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Please evaluate this interview for {job_role} position and provide a comprehensive assessment with pass/fail recommendation."}
    ]

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.3,
        max_tokens=1500
    )

    review = completion.choices[0].message.content.strip()
    return review


def call_prediction_api_from_text(user_text: str, job_role: str):
    """
    Call your prediction API with job role context.
    """
    try:
        payload = {
            "skills": user_text,
            "job_role": job_role,
            "education": "Not specified",
            "experience_years": "Not specified"
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

def get_job_role():
    """Get the job role from user input."""
    print("Available IT Job Roles:")
    common_roles = [
        "Data Scientist", "Machine Learning Engineer", "Data Analyst",
        "Software Engineer", "Backend Developer", "Frontend Developer", "Full Stack Developer",
        "DevOps Engineer", "Cloud Engineer", "System Administrator",
        "Cybersecurity Analyst", "Network Engineer", "Database Administrator",
        "IT Project Manager", "Business Analyst", "QA Engineer"
    ]
    
    for i, role in enumerate(common_roles, 1):
        print(f"{i}. {role}")
    
    while True:
        try:
            choice = input("\nEnter the job role (type the name or number): ").strip()
            
            if choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(common_roles):
                    return common_roles[choice_num - 1]
                else:
                    print("Please select a valid number")
            else:
                if choice.title() in common_roles:
                    return choice.title()
                else:
                    print("Role not in list. Please select from available roles or enter a custom role:")
                    return input("Custom job role: ").strip()
                    
        except Exception as e:
            print(f"Error: {e}. Please try again.")


def run_intelligent_interview():
    print("===============================================")
    print("    JobGenix AI – Intelligent Voice Interview")
    print("===============================================")
    print("This AI interviewer will generate job-specific questions dynamically.")
    print("Controls:")
    print(" - You will be asked 5 intelligent questions for your specific job role")
    print(" - Questions are generated based on the job role and your previous answers")
    print(" - You answer by speaking. I record ~10 seconds per answer.")
    print(" - After 5 questions, you'll receive a comprehensive review and pass/fail assessment\n")

    # Get job role
    job_role = get_job_role()
    print(f"\nStarting interview for: {job_role}")
    print("The AI will ask 5 intelligent questions specific to this role.\n")

    # Initialize conversation history
    history = []
    total_questions = 5
    
    # Store all answers for analysis
    interview_data = []

    # Conduct the interview
    for question_num in range(1, total_questions + 1):
        print(f"\n{'='*50}")
        print(f"QUESTION {question_num}/{total_questions}")
        print(f"{'='*50}")
        
        # Generate intelligent question
        ai_response = generate_interview_question(history, job_role, question_num)
        print(f"[AI] {ai_response}")
        
        # Update history
        history.append({"role": "assistant", "content": ai_response})
        
        # Speak the question
        text_to_speech_to_wav(ai_response, OUTPUT_WAV)
        play_wav(OUTPUT_WAV)

        # Wait for user to be ready
        input("\nPress ENTER when you're ready to answer...")
        
        # Record user's answer
        record_microphone_to_wav(INPUT_WAV, RECORD_SECONDS)
        
        # Transcribe answer
        user_text = transcribe_audio(INPUT_WAV)
        
        # Store interview data for review
        interview_data.append({
            "question_number": question_num,
            "question": ai_response,
            "answer": user_text,
            "job_role": job_role
        })

        # Update history with user's answer
        history.append({"role": "user", "content": user_text})

        # Check if user wants to stop early
        if user_text.lower().strip() in ["stop interview", "quit", "exit", "stop", "end interview"]:
            print("\n[AI] Interview stopped by user.")
            break

        # Call prediction API with job context
        prediction = call_prediction_api_from_text(user_text, job_role)
        if prediction:
            print(f"[PREDICTION API] {prediction}")

        # Brief pause between questions
        if question_num < total_questions:
            print("\nPreparing next question...")
            time.sleep(2)

    # Generate comprehensive review
    print("\n" + "="*60)
    print("GENERATING COMPREHENSIVE INTERVIEW REVIEW...")
    print("="*60)
    
    review = generate_interview_review(job_role, interview_data)
    
    print("\n" + " " * 60)
    print("  INTERVIEW ASSESSMENT REPORT")
    print(" " * 60)
    print(review)
    print(" " * 60)
    
    # Speak the final result
    if "PASS" in review.upper() or "RECOMMEND" in review.upper() and "NOT" not in review.upper():
        result_audio = "Congratulations! Based on your interview performance, you have passed the technical assessment. Please check the detailed review on screen."
    else:
        result_audio = "Thank you for completing the interview. Based on your performance, we recommend further preparation. Please check the detailed assessment on screen for areas of improvement."
    
    print(f"\n[AI] {result_audio}")
    text_to_speech_to_wav(result_audio, OUTPUT_WAV)
    play_wav(OUTPUT_WAV)

    # Save interview report to file
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_filename = f"interview_report_{job_role.replace(' ', '_')}_{timestamp}.txt"
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("JOBGENIX AI INTERVIEW REPORT\n")
        f.write("=" * 50 + "\n")
        f.write(f"Job Role: {job_role}\n")
        f.write(f"Interview Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 50 + "\n\n")
        f.write("INTERVIEW QUESTIONS & ANSWERS:\n")
        f.write("-" * 40 + "\n")
        for i, qa in enumerate(interview_data, 1):
            f.write(f"\nQ{i}: {qa['question']}\n")
            f.write(f"A{i}: {qa['answer']}\n")
            f.write("-" * 40 + "\n")
        f.write("\nASSESSMENT REPORT:\n")
        f.write("=" * 50 + "\n")
        f.write(review)
    
    print(f"\n Interview report saved as: {report_filename}")

    # Print final summary
    print("\n" + " " * 60)
    print("INTERVIEW COMPLETED SUCCESSFULLY!")
    print(" " * 60)
    print(f"Job Role: {job_role}")
    print(f"Questions Completed: {len(interview_data)}")
    print(f"Report Saved: {report_filename}")
    print("Thank you for using JobGenix AI Interview System!")
    print(" " * 60)


if __name__ == "__main__":
    run_intelligent_interview()