from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
import os
from dotenv import load_dotenv
from langdetect import detect
from io import BytesIO
from gtts import gTTS
import speech_recognition as sr
import tempfile

load_dotenv()

app = FastAPI()

# ==== CORS ====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LANGUAGE_NAMES = {
    'en': 'English', 'hi': 'Hindi', 'bn': 'Bengali', 'te': 'Telugu',
    'mr': 'Marathi', 'ta': 'Tamil', 'gu': 'Gujarati', 'kn': 'Kannada',
    'ml': 'Malayalam', 'pa': 'Punjabi', 'ur': 'Urdu', 'or': 'Odia', 'as': 'Assamese'
}

# ---- LANGUAGE DETECTION ----
def detect_script(text):
    ranges = [
        ('hi', '\u0900', '\u097F'),
        ('or', '\u0B00', '\u0B7F'),
        ('bn', '\u0980', '\u09FF'),
        ('ta', '\u0B80', '\u0BFF'),
        ('te', '\u0C00', '\u0C7F'),
        ('gu', '\u0A80', '\u0AFF'),
        ('kn', '\u0C80', '\u0CFF'),
        ('ml', '\u0D00', '\u0D7F'),
        ('pa', '\u0A00', '\u0A7F'),
    ]
    for lang, start, end in ranges:
        if any(start <= c <= end for c in text):
            return lang
    return None

def detect_language_enhanced(text):
    s = detect_script(text)
    if s: return s
    try:
        d = detect(text)
        if d == 'sw' and detect_script(text): return 'hi'
        return d
    except:
        return 'en'

# ---- SMALL TALK ----
def is_small_talk(text):
    smalltalk = {
        'en': ['hello', 'hi', 'hey', 'thanks', 'bye'],
        'hi': ['namaste', 'dhanyavaad'],
        'or': ['namaskar', 'dhanyabad']
    }
    tl = text.lower()
    for phrases in smalltalk.values():
        if any(p == tl or p in tl for p in phrases):
            return True
    return False

def get_small_talk_response(text, lang):
    responses = {
        'hi': {"greet": "नमस्ते! मैं AAROH हूं।", "thanks": "आपका स्वागत है!", "bye": "नमस्ते!"},
        'or': {"greet": "ନମସ୍କାର! ମୁଁ AAROH ।", "thanks": "ସ୍ୱାଗତ!", "bye": "ନମସ୍କାର!"},
        'en': {"greet": "Hello! I'm AAROH.", "thanks": "You're welcome!", "bye": "Goodbye!"}
    }
    lang_res = responses.get(lang, responses["en"])
    tl = text.lower()
    if "thank" in tl: return lang_res["thanks"]
    if "bye" in tl: return lang_res["bye"]
    return lang_res["greet"]

# ---- AUDIO OUT ----
def text_to_speech(text, lang):
    try:
        lang_map = {
            'hi': 'hi', 'or': 'or', 'en': 'en', 'bn': 'bn', 'ta': 'ta',
            'te': 'te', 'mr': 'mr', 'gu': 'gu', 'kn': 'kn', 'ml': 'ml'
        }
        tts = gTTS(text=text, lang=lang_map.get(lang, 'en'))
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except:
        return None

# ---- AUDIO IN ----
def speech_to_text(audio_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_bytes)
        path = f.name

    rec = sr.Recognizer()
    with sr.AudioFile(path) as src:
        audio = rec.record(src)

    try:
        text = rec.recognize_google(audio, language="hi-IN")
        return text
    except:
        return None

# ---- AI PROMPT (UNCHANGED) ----
def build_prompt(user_query, chat_history, lang):
    """Improved PM-AJAY focused prompt (same as Streamlit version)"""

    LANGUAGE_NAMES = {
        'hi': "Hindi (Devanagari)",
        'or': "Odia",
        'bn': "Bengali",
        'ta': "Tamil",
        'te': "Telugu",
        'en': "English"
    }

    language_instructions = {
        'hi': "Respond in Hindi (Devanagari script).",
        'or': "Respond in Odia (Odia script) if possible, otherwise Hindi.",
        'bn': "Respond in Bengali (Bengali script).",
        'ta': "Respond in Tamil (Tamil script).",
        'te': "Respond in Telugu (Telugu script).",
        'en': "Respond in English."
    }

    lang_instruction = language_instructions.get(
        lang,
        f"Respond in {LANGUAGE_NAMES.get(lang, 'the same language')}."
    )

    return f"""
You are AAROH, an AI assistant specifically designed for PM-AJAY (Pradhan Mantri Anusuchit Jaati Abhyuday Yojana) — 
a national programme for Scheduled Caste development.

{lang_instruction}

Conversation History:
{chat_history}

CRITICAL RULES:

• You ONLY answer questions related to PM-AJAY or Scheduled Caste welfare.
• If user asks anything outside PM-AJAY → politely say you can only help with PM-AJAY related topics.
• Be simple, friendly, accurate, and avoid long paragraphs.
• Ask **one question at a time** if eligibility assessment is needed.
• Never generate false information. Give government-style answers.
• If uncertain → suggest contacting local SC Welfare Office.

PM-AJAY Key Components:
1. Education & Scholarships  
2. Skill Development & Livelihood Training  
3. Entrepreneurship & Income Generation  
4. Housing & Infrastructure Support  
5. Health, Nutrition & Social Justice  
6. Digital Empowerment  
7. Grant-in-Aid (GIA) for community development projects  

Target Beneficiaries: Scheduled Caste individuals & communities.

User Question: {user_query}

Now give a clear, correct and helpful answer in {LANGUAGE_NAMES.get(lang, lang)}:
"""


genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")


# ========= MAIN API ============
class ChatRequest(BaseModel):
    message: str
    chat_history: list = []
    wants_audio: bool = False
    is_voice: bool = False


@app.post("/chat")
async def chat(req: ChatRequest):

    user_query = req.message
    lang = detect_language_enhanced(user_query)

    # Small Talk
    if is_small_talk(user_query):
        resp = get_small_talk_response(user_query, lang)
        audio = text_to_speech(resp, lang) if req.wants_audio else None
        return {
            "text": resp,
            "language": lang,
            "tts_audio": audio
        }

    # Build prompt
    history_text = ""
    for m in req.chat_history[-10:]:
        role = "User" if m["role"] == "user" else "Assistant"
        history_text += f"{role}: {m['content']}\n"

    prompt = build_prompt(user_query, history_text, lang)

    ai_resp = model.generate_content(prompt).text

    tts_audio = text_to_speech(ai_resp, lang) if req.wants_audio else None

    return {
        "text": ai_resp,
        "language": lang,
        "tts_audio": tts_audio
    }
