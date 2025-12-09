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

# ---- SMALL TALK ----
def is_small_talk(text):
	keywords = ['hello', 'hi', 'hey', 'namaste', 'vanakkam', 'kem cho']
	return text.lower().strip() in keywords

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
		clean_text = re.sub(r'[\*\#]', '', text)
		tts = gTTS(text=clean_text, lang=lang)
		buf = BytesIO()
		tts.write_to_fp(buf)
		buf.seek(0)
		return buf.read()
	except:
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
		text = rec.recognize_google(audio)
		os.unlink(path)
		return text
	except:
		os.unlink(path)
		return None

# ---- AI PROMPT ----
def build_prompt(user_query, chat_history, target_lang):

	LOGIN_URL = "https://sujhaa-frontend.vercel.app/login"
	REGISTER_URL = "https://sujhaa-frontend.vercel.app/register"
	VIDEO_URL = "https://youtu.be/TH0EGRd4FHc?si=UlNreiThmSa1LQhY"
	HELPLINE = "1800110000"

	language_name = SUPPORTED_LANGUAGES.get(target_lang, 'English')

	# ✅ ADDITION 1: HELP MASTER RESPONSE
	help_keywords = [
		"help", "need help", "problem", "issue",
		"support", "portal problem"
	]

	if any(k in user_query.lower() for k in help_keywords):
		return f"""
**SUJHAA Help & Support**

**1. Application Rejected**
- **Check Reason:** Log in to see the exact reason → {LOGIN_URL}
- **Action:** Rectify the issue (upload clearer documents) and resubmit
- **Helpline:** Call **{HELPLINE}**

**2. Forgot Login / Beneficiary ID**
- **Password:** Use the *Forgot Password* option on Login page
- **Beneficiary ID:** Check registered email (Inbox / Spam)
- **Contact:** Call **{HELPLINE}**

**3. Status Stuck / Not Updating**
- **Wait:** Field verification may take several weeks
- **Check Account:** Ensure no clarification is pending
- **Manual Check:** Call **{HELPLINE}**

**4. General Assistance**
- **SUJHAA Help Desk:** **{HELPLINE}**
"""

	# ✅ ADDITION 2: HOW TO APPLY WITH VIDEO FIRST
	if any(k in user_query.lower() for k in [
		"how to apply", "application process",
		"register", "registration"
	]):
		return f"""
📺 **Watch Step-by-Step Video Guide First**
{VIDEO_URL}

**How to Apply on SUJHAA**

1️⃣ **Registration**
- {REGISTER_URL}

2️⃣ **Email OTP & Digital ID**
- Verification through registered email

3️⃣ **Login**
- {LOGIN_URL}

4️⃣ **Scheme Selection**
- Eligible PM-AJAY schemes shown

5️⃣ **Upload Documents**
- Caste Certificate
- Income Certificate
- Domicile Certificate

6️⃣ **Final Submission**
- Application ID generated
- Status: *Under Verification*
"""

	# ---- ORIGINAL PROMPT CONTINUES (UNCHANGED) ----
	return f"""
You are **AAROH**, a responsible AI assistant for **SUJHAA**.

Respond ONLY within PM-AJAY and SUJHAA domain.
If outside scope, say politely you cannot help.

Reply in **{language_name}**.
Be clear, short, and structured.

Conversation History:
{chat_history}

User Question:
{user_query}
"""

# ===== GEMINI CONFIG =====
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# ===== API MODEL =====
class ChatRequest(BaseModel):
	message: str
	target_language: str
	chat_history: list = []
	wants_audio: bool = False
	is_voice: bool = False

# ===== MAIN CHAT API =====
@app.post("/chat")
async def chat(req: ChatRequest):

	user_query = req.message
	target_lang = req.target_language.lower()

	if req.is_voice:
		user_query = speech_to_text(user_query, target_lang)
		if not user_query:
			return {"text": "Voice not understood.", "language": target_lang}

	if is_small_talk(user_query):
		resp = get_small_talk_response(target_lang)
		return {"text": resp, "language": target_lang}

	history_text = ""
	for m in req.chat_history[-10:]:
		role = "User" if m["role"] == "user" else "Assistant"
		history_text += f"{role}: {m['content']}\n"

	prompt = build_prompt(user_query, history_text, target_lang)

	try:
		ai_resp = model.generate_content(prompt).text
	except:
		ai_resp = "Information is currently unavailable."

	tts_audio = text_to_speech(ai_resp, target_lang) if req.wants_audio else None

	return {
		"text": ai_resp,
		"language": target_lang,
		"tts_audio": tts_audio
	}
