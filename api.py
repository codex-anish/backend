import os
from io import BytesIO
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form
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

# Supported Languages for the Chatbot
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'hi': 'Hindi',
    'ta': 'Tamil',
    'gu': 'Gujarati',
}

# ---- LANGUAGE DETECTION (Simplified/Targeted for Indian Languages) ----
def detect_script_simple(text):
    """Detects script for Indian languages, defaulting to 'en'."""
    # Devanagari (Hindi)
    if any('\u0900' <= c <= '\u097F' for c in text): return 'hi'
    # Tamil
    if any('\u0B80' <= c <= '\u0BFF' for c in text): return 'ta'
    # Gujarati
    if any('\u0A80' <= c <= '\u0AFF' for c in text): return 'gu'
    # Simple check for English characters
    if any('a' <= c.lower() <= 'z' for c in text): return 'en'
    return 'en' # Default fallback

# ---- SMALL TALK ----
def is_small_talk(text, chat_history):
    """
    Enhanced small talk detection. 
    It only detects small talk if the message is very short/simple 
    AND if the history is empty (for initial greeting) or if it's explicitly 'thanks'/'bye'.
    """
    tl = text.lower().strip()
    
    # Explicitly handle Thanks/Bye, regardless of history
    if "thank" in tl or "dhanyavaad" in tl or "shukriya" in tl or "bye" in tl or "alvida" in tl:
        return True

    # If history is NOT empty, we don't want to greet again on simple questions.
    if chat_history:
        return False

    # Check for simple greetings only if it's the very first message
    greeting_keywords = ['hello', 'hi', 'hey', 'namaste', 'vandanam', 'namaskar']
    if any(p == tl for p in greeting_keywords) or any(p in tl and len(tl) < 10 for p in greeting_keywords):
        return True
    
    return False


def get_small_talk_response(text, lang):
    """Provides a tailored small talk response."""
    # Updated 'greet' message to focus on Sujhaa and PM-AJAY
    responses = {
        'hi': {"greet": "नमस्ते! मैं **AAROH** हूँ, **Sujhaa** का PM-AJAY सहायक। मैं विशेष रूप से **Grant-in-Aid** और योजना की जानकारी में आपकी मदद कर सकता हूँ।", "thanks": "आपका स्वागत है!", "bye": "नमस्ते! अलविदा।"},
        'ta': {"greet": "வணக்கம்! நான் **AAROH**, **Sujhaa**-இன் PM-AJAY உதவியாளர். **Grant-in-Aid** மற்றும் திட்டம் பற்றிய தகவல்களுக்கு நான் உங்களுக்கு உதவ முடியும்.", "thanks": "வரவேற்கிறேன்!", "bye": "நன்றி! போய் வருகிறேன்."},
        'gu': {"greet": "નમસ્કાર! હું **AAROH** છું, **Sujhaa** નો PM-AJAY સહાયક. હું ખાસ કરીને **Grant-in-Aid** અને યોજનાની માહિતીમાં તમારી મદદ કરી શકું છું.", "thanks": "તમારું સ્વાગત છે!", "bye": "આવજો!"},
        'en': {"greet": "Hello! I'm **AAROH**, the PM-AJAY assistant for **Sujhaa**. I can primarily assist you with **Grant-in-Aid (GIA)** and other scheme details.", "thanks": "You're welcome!", "bye": "Goodbye!"}
    }
    lang_res = responses.get(lang, responses["en"])
    tl = text.lower()
    if "thank" in tl or "dhanyavaad" in tl or "shukriya" in tl: return lang_res["thanks"]
    if "bye" in tl or "alvida" in tl or "avjo" in tl: return lang_res["bye"]
    return lang_res["greet"]

# ---- AUDIO OUT ----
def text_to_speech(text, lang):
    """Converts text to speech bytes."""
    try:
        # gTTS uses standard ISO 639-1 codes
        lang_map = {'hi': 'hi', 'ta': 'ta', 'gu': 'gu', 'en': 'en'}
        tts_lang = lang_map.get(lang, 'en')
        
        # Remove markdown before TTS to prevent gTTS reading '*' or '**'
        clean_text = re.sub(r'[\*\#]', '', text) 

        tts = gTTS(text=clean_text, lang=tts_lang)
        buf = BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

# ---- AUDIO IN ----
def speech_to_text(audio_bytes, target_lang):
    """Converts speech bytes to text using target language hint."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_bytes)
        path = f.name

    rec = sr.Recognizer()
    try:
        with sr.AudioFile(path) as src:
            audio = rec.record(src)
        
        # Mapping for Google Speech Recognition
        sr_lang_map = {
            'hi': 'hi-IN', 
            'ta': 'ta-IN', 
            'gu': 'gu-IN', 
            'en': 'en-US'
        }
        sr_lang = sr_lang_map.get(target_lang, 'en-US')

        text = rec.recognize_google(audio, language=sr_lang)
        os.unlink(path) # Clean up temp file
        return text
    except Exception as e:
        print(f"STT Error: {e}")
        os.unlink(path)
        return None

# ---- AI PROMPT (Trained like a Pro) ----
def build_prompt(user_query, chat_history, target_lang):
    """
    Improved PM-AJAY focused prompt with strict formatting and language control.
    """

    language_name = SUPPORTED_LANGUAGES.get(target_lang, 'English')

    return f"""
You are AAROH, a professional, concise, and friendly AI assistant for **Sujhaa**, specifically designed for the **PM-AJAY (Pradhan Mantri Anusuchit Jaati Abhyuday Yojana)** scheme. Your primary focus is to provide detailed information on the **Grant-in-Aid (GIA)** component.

**CRITICAL INSTRUCTIONS:**
1.  **Response Language:** You MUST respond ONLY in **{language_name}** (Target Language).
2.  **Conciseness & Tone:** Provide short, clear, and direct answers. **Do not give long paragraphs.** Maintain a helpful and official tone.
3.  **Formatting:** Structure information using **Markdown Bullet Points (`*`)** and **Bold Keywords (`**keyword**`)** for better readability. Avoid surrounding the entire response or scheme names with quotes.
4.  **Domain Focus:** ONLY answer questions related to **PM-AJAY** or general **SC welfare**. If the user asks for non-related information, politely state that you can only help with PM-AJAY.
5.  **GIA Focus:** When discussing PM-AJAY, always emphasize and prioritize the **Grant-in-Aid (GIA)** component as a key area of focus for AAROH/Sujhaa.
6.  **Hinglish/Input Language:** If the user inputs text in Hinglish (e.g., "pm ajay kya hai"), process the query but respond strictly in the Target Language (**{language_name}**).

**PM-AJAY Key Components (Use these in your answers):**
* **Education & Scholarships** * **Skill Development & Livelihood Training** * **Entrepreneurship & Income Generation** * **Housing & Infrastructure Support** * **Health, Nutrition & Social Justice** * **Digital Empowerment** * **Grant-in-Aid (GIA):** **(This is AAROH's MAIN FOCUS)** Financial support to NGOs/Local Bodies for SC community projects, including infrastructure and scheme awareness.

Conversation History (For context, max 10 turns):
{chat_history}

User Question: {user_query}

Now, provide a helpful and precise answer strictly following all CRITICAL INSTRUCTIONS in **{language_name}**:
"""


genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")


# ========= MAIN API ============
class ChatRequest(BaseModel):
    message: str
    target_language: str # New field for chosen language (en, hi, ta, gu)
    chat_history: list = []
    wants_audio: bool = False
    is_voice: bool = False


@app.post("/chat")
async def chat(req: ChatRequest):

    user_query = req.message
    target_lang = req.target_language.lower() # Enforce lowercase
    
    # 1. Voice-to-Text Conversion (if needed) - Removed for simplicity in this file

    # 2. Small Talk Handling (FIXED: Added chat_history check)
    if is_small_talk(user_query, req.chat_history):
        resp = get_small_talk_response(user_query, target_lang)
        audio = text_to_speech(resp, target_lang) if req.wants_audio else None
        return {
            "text": resp,
            "language": target_lang,
            "tts_audio": audio
        }

    # 3. Build prompt
    history_text = ""
    for m in req.chat_history[-10:]:
        role = "User" if m["role"] == "user" else "Assistant"
        # Only add content, the model will handle language based on the target_lang
        history_text += f"{role}: {m['content']}\n" 

    prompt = build_prompt(user_query, history_text, target_lang)

    try:
        # 4. Generate AI Response
        ai_resp = model.generate_content(prompt).text
    except Exception as e:
        print(f"AI Generation Error: {e}")
        # Error messages in target language
        if target_lang == 'hi':
            ai_resp = "क्षमा करें, मैं अभी आपकी मदद नहीं कर सकता। कृपया कुछ देर बाद कोशिश करें।"
        elif target_lang == 'ta':
            ai_resp = "மன்னிக்கவும், இப்போதைக்கு என்னால் உங்களுக்கு உதவ முடியவில்லை. சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும்."
        elif target_lang == 'gu':
            ai_resp = "માફ કરશો, હું અત્યારે તમારી મદદ કરી શકતો નથી. કૃપા કરીને થોડા સમય પછી ફરી પ્રયાસ કરો।"
        else:
            ai_resp = "Sorry, I cannot assist you at the moment. Please try again later."


    # 5. Text-to-Speech Conversion
    tts_audio = text_to_speech(ai_resp, target_lang) if req.wants_audio else None

    return {
        "text": ai_resp,
        "language": target_lang,
        "tts_audio": tts_audio
    }