import os
from io import BytesIO
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from gtts import gTTS
import tempfile
import speech_recognition as sr
import re

load_dotenv()

app = FastAPI()

# ==== CORS ====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supported Languages
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'hi': 'Hindi',
    'ta': 'Tamil',
    'gu': 'Gujarati',
}

# ---- SCRIPT DETECTION ----
def detect_script_simple(text):
    if any('\u0900' <= c <= '\u097F' for c in text): return 'hi'
    if any('\u0B80' <= c <= '\u0BFF' for c in text): return 'ta'
    if any('\u0A80' <= c <= '\u0AFF' for c in text): return 'gu'
    if any('a' <= c.lower() <= 'z' for c in text): return 'en'
    return 'en'

# ---- SMALL TALK (NO AUTO GREETING ANYMORE) ----
def is_small_talk(text):
    keywords = ['hello', 'hi', 'hey', 'namaste', 'vanakkam', 'kem cho']
    tl = text.lower()
    return any(p == tl.strip() for p in keywords)

def get_small_talk_response(lang):
    responses = {
        'hi': "नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ?",
        'ta': "வணக்கம்! எப்படி உதவலாம்?",
        'gu': "નમસ્તે! હું તમારી કેવી મદદ કરું?",
        'en': "Hello! How can I assist you?"
    }
    return responses.get(lang, responses['en'])

# ---- TTS ----
def text_to_speech(text, lang):
    try:
        lang_map = {'hi': 'hi', 'ta': 'ta', 'gu': 'gu', 'en': 'en'}
        tts_lang = lang_map.get(lang, 'en')
        clean_text = re.sub(r'[\*\#]', '', text)
        tts = gTTS(text=clean_text, lang=tts_lang)
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None

# ---- STT ----
def speech_to_text(audio_bytes, target_lang):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_bytes)
        path = f.name

    rec = sr.Recognizer()
    try:
        with sr.AudioFile(path) as src:
            audio = rec.record(src)

        lang_map = {
            'hi': 'hi-IN',
            'ta': 'ta-IN',
            'gu': 'gu-IN',
            'en': 'en-US'
        }
        text = rec.recognize_google(audio, language=lang_map.get(target_lang, 'en-US'))
        os.unlink(path)
        return text
    except:
        os.unlink(path)
        return None

# ---- AI PROMPT ----
def build_prompt(user_query, chat_history, target_lang):
    language_name = SUPPORTED_LANGUAGES.get(target_lang, 'English')

    return f"""
You are **AAROH**, a responsible, careful, and intelligent AI assistant for the **SUJHAA** platform.

━━━━━━━━━━━━━━━━━━━━
🧠 CRITICAL THINKING & SAFETY RULE
━━━━━━━━━━━━━━━━━━━━
You must think and respond like a **government information assistant**.

✅ Answer ONLY when the question is clearly within your domain.
❌ NEVER guess, assume, fabricate, or hallucinate information.

If the question is:
- Outside SUJHAA
- Outside PM-AJAY
- Outside PM-AJAY components
- Outside SUJHAA components
- About officers, backend, administration, coding, APIs, or internal systems
- Unclear or beyond available information

👉 Respond politely with:
“I’m sorry, I can help only with information related to PM-AJAY or the SUJHAA platform.”

If the question IS in domain but the information is not available:
👉 Clearly say:
“This information is currently not available on SUJHAA.”

━━━━━━━━━━━━━━━━━━━━
🎯 STRICT DOMAIN (DO NOT CROSS)
━━━━━━━━━━━━━━━━━━━━
You are allowed to answer ONLY about:
- **PM-AJAY scheme**
- **PM-AJAY components (Grant-in-Aid, Skill Development, Income Generation, Infrastructure)**
- **SUJHAA platform**
- **SUJHAA beneficiary processes and components**

━━━━━━━━━━━━━━━━━━━━
📌 ABOUT SUJHAA (BENEFICIARY VIEW)
━━━━━━━━━━━━━━━━━━━━
SUJHAA is a digital platform that helps **Scheduled Caste (SC) beneficiaries**
apply for and track schemes under **PM-AJAY** easily and transparently.

━━━━━━━━━━━━━━━━━━━━
✅ ELIGIBILITY TO APPLY
━━━━━━━━━━━━━━━━━━━━
A beneficiary can apply if:
- They belong to **Scheduled Caste (SC)**
- They have a **valid Aadhaar**
- They have a **valid email ID**
- They possess valid documents:
  - Caste Certificate
  - Income Certificate
  - Domicile / Residential Certificate

━━━━━━━━━━━━━━━━━━━━
📝 SUJHAA APPLICATION PROCESS
━━━━━━━━━━━━━━━━━━━━
Always explain in this exact sequence:

1️⃣ Registration  
- Fill application form  
- Upload Aadhaar image & photo  

2️⃣ Email OTP & Digital ID  
- OTP sent to registered email  
- After verification:
  - Registration confirmed
  - Digital Beneficiary ID sent by email

3️⃣ Login  
- Aadhaar Number or Digital Beneficiary ID  
- Password  

4️⃣ Scheme Selection  
- System shows eligible PM-AJAY schemes  
- Beneficiary selects scheme(s)

5️⃣ Upload Documents  
- Caste Certificate  
- Income Certificate  
- Domicile Certificate  

6️⃣ Final Submission  
- Application ID generated  
- Status: **Submitted – Under Verification**

━━━━━━━━━━━━━━━━━━━━
📊 AFTER SUBMISSION
━━━━━━━━━━━━━━━━━━━━
- Application goes to field officer for further verification
- Field verification may occur if required
- Beneficiary can track status anytime

━━━━━━━━━━━━━━━━━━━━
🆘 PERMITTED HELP TOPICS
━━━━━━━━━━━━━━━━━━━━
You may help with:
- How to apply on SUJHAA
- Documents required
- Login and Digital ID help
- Application status meanings
- PM-AJAY scheme overview (high-level)

━━━━━━━━━━━━━━━━━━━━
🚫 FORBIDDEN ACTIONS
━━━━━━━━━━━━━━━━━━━━
- Do NOT answer outside domain
- Do NOT hallucinate or guess
- Do NOT explain internal systems
- Do NOT give legal or policy interpretation

━━━━━━━━━━━━━━━━━━━━
🗣 RESPONSE STYLE
━━━━━━━━━━━━━━━━━━━━
1. Reply ONLY in **{language_name}**
2. Be **short, structured, and clear**
3. Use **bullet points & bold keywords**
4. No greeting unless user greets first
5. Maintain calm, official, helpful tone

Conversation History:
{chat_history}

User Question:
{user_query}

Now respond carefully and truthfully in **{language_name}**, following ALL rules above.
"""



genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# ========= MAIN API ============
class ChatRequest(BaseModel):
    message: str
    target_language: str
    chat_history: list = []
    wants_audio: bool = False
    is_voice: bool = False

@app.post("/chat")
async def chat(req: ChatRequest):

    user_query = req.message
    target_lang = req.target_language.lower()

    # Voice Input
    if req.is_voice:
        user_query = speech_to_text(user_query, target_lang)
        if not user_query:
            msgs = {
                "hi": "क्षमा करें, आपकी आवाज़ समझ नहीं आई।",
                "ta": "மன்னிக்கவும், குரலை புரிந்துகொள்ள முடியவில்லை.",
                "gu": "માફ કરશો, અવાજ સમજાયો નથી.",
                "en": "Sorry, I couldn’t understand your voice."
            }
            return {"text": msgs.get(target_lang, msgs["en"]), "language": target_lang}

    # Small Talk (ONLY IF EXACT GREETING)
    if is_small_talk(user_query):
        resp = get_small_talk_response(target_lang)
        audio = text_to_speech(resp, target_lang) if req.wants_audio else None
        return {"text": resp, "language": target_lang, "tts_audio": audio}

    # Build history text
    history_text = ""
    for m in req.chat_history[-10:]:
        role = "User" if m["role"] == "user" else "Assistant"
        history_text += f"{role}: {m['content']}\n"

    prompt = build_prompt(user_query, history_text, target_lang)

    try:
        ai_resp = model.generate_content(prompt).text
    except:
        fallback = {
            'hi': "अभी जानकारी उपलब्ध नहीं है। कृपया बाद में प्रयास करें।",
            'ta': "தகவல் கிடைக்கவில்லை. பின்னர் முயற்சிக்கவும்.",
            'gu': "માહિતી ઉપલબ્ધ નથી. થોડા સમય પછી પ્રયત્ન કરો.",
            'en': "I cannot respond right now. Please try again later."
        }
        ai_resp = fallback.get(target_lang, fallback["en"])

    tts_audio = text_to_speech(ai_resp, target_lang) if req.wants_audio else None

    return {
        "text": ai_resp,
        "language": target_lang,
        "tts_audio": tts_audio
    }
