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
	
	# =========================================================================
	# ✅ HARDCODED SUPPORT DATA AND LOGIC
	# =========================================================================
	LOGIN_URL = "https://sujhaa-frontend.vercel.app/login"
	HELPLINE = "1800110000"
	
	# --- Master Query Translations (from Frontend) ---
	MASTER_PROBLEM_QUERIES = {
		'en': "I have a problem on the portal.",
		'hi': "पोर्टल पर मुझे एक समस्या है",
		'ta': "போர்ட்டலில் எனக்கு ஒரு சிக்கல் உள்ளது",
		'gu': "પોર્ટલ પર મને એક સમસ્યા છે"
	}
	
	# --- English Responses ---
	if target_lang == 'en':
		HELP_RESPONSES = {
			"Help: Application rejected, what next?": 
				"* **Check Reason:** **Log in** to see the rejection reason: " + LOGIN_URL + "\n"
				"* **Action:** **Rectify** the issue (e.g., re-upload documents) and **resubmit**.\n"
				"* **Helpline:** Call **" + HELPLINE + "** or use the Dashboard support.",
				
			"Help: Forgot password or beneficiary ID": 
				"* **Forgot Password:** Use the 'Forgot Password' link on the [**Login Page**](" + LOGIN_URL + ").\n"
				"* **Beneficiary ID:** Check your registered **email inbox** (including spam).\n"
				"* **Contact:** Call **" + HELPLINE + "** for further assistance.",
				
			"Help: Application status is stuck or not updating": 
				"* **Wait:** Verification processes can take several weeks. Allow ample time.\n"
				"* **Check Account:** **Log in** to your account (" + LOGIN_URL + ") to ensure no **missing document** request is pending.\n"
				"* **Manual Check:** Call **" + HELPLINE + "** if the delay is excessive.",
				
			"Help: General assistance needed":
				"* **SUJHAA Dashboard:** Use the dedicated **Help & Support** section in your dashboard.\n"
				"* **Helpline:** Call the SUJHAA Help Desk at **" + HELPLINE + "**.",
		}
		
		# ✅ MASTER RESPONSE: Consolidated response for "I have a problem on the portal."
		MASTER_RESPONSE = (
			"Here is a quick guide to common SUJHAA issues:\n\n"
			"**1. Application Rejected:**\n" + HELP_RESPONSES["Help: Application rejected, what next?"] + "\n\n"
			"**2. Forgot Login/ID:**\n" + HELP_RESPONSES["Help: Forgot password or beneficiary ID"] + "\n\n"
			"**3. Status Stuck/Not Updating:**\n" + HELP_RESPONSES["Help: Application status is stuck or not updating"] + "\n\n"
			"**4. General Assistance/Other Issue:**\n" + HELP_RESPONSES["Help: General assistance needed"]
		)
	
	# --- Hindi Responses ---
	elif target_lang == 'hi':
		HELP_RESPONSES = {
			"Help: Application rejected, what next?":
				"* **कारण जांचें:** **लॉग इन** करके खारिज होने का सटीक कारण देखें: " + LOGIN_URL + "\n"
				"* **कार्य:** समस्या **ठीक करें** (दस्तावेज़ अपलोड करें) और **पुनः सबमिट** करें।\n"
				"* **हेल्पलाइन:** SUJHAA डैशबोर्ड पर **सहायता** का उपयोग करें या **" + HELPLINE + "** पर कॉल करें।",
				
			"Help: Forgot password or beneficiary ID":
				"* **पासवर्ड भूल गए:** [**लॉगिन पेज**](" + LOGIN_URL + ") पर 'पासवर्ड भूल गए' पर क्लिक करें।\n"
				"* **लाभार्थी आईडी:** अपने पंजीकृत **ईमेल इनबॉक्स** (स्पैम सहित) की जाँच करें।\n"
				"* **संपर्क करें:** आगे की सहायता के लिए **" + HELPLINE + "** पर कॉल करें।",
				
			"Help: Application status is stuck or not updating":
				"* **प्रतीक्षा करें:** सत्यापन में कई सप्ताह लग सकते हैं।\n"
				"* **खाता जांचें:** **लॉग इन** करें (" + LOGIN_URL + ") और सुनिश्चित करें कि कोई **दस्तावेज़ अनुरोध** लंबित नहीं है।\n"
				"* **मैनुअल जांच:** यदि देरी अधिक है, तो **" + HELPLINE + "** पर कॉल करें।",
				
			"Help: General assistance needed":
				"* **SUJHAA डैशबोर्ड:** डैशबोर्ड के अंदर उपलब्ध **सहायता एवं समर्थन** अनुभाग का उपयोग करें।\n"
				"* **हेल्पलाइन:** SUJHAA हेल्प डेस्क को **" + HELPLINE + "** पर कॉल करें।",
		}
		
		# ✅ MASTER RESPONSE: Consolidated response for "पोर्टल पर मुझे एक समस्या है"
		MASTER_RESPONSE = (
			"SUJHAA की सामान्य समस्याओं के लिए एक त्वरित मार्गदर्शिका यहाँ दी गई है:\n\n"
			"**1. आवेदन खारिज हुआ:**\n" + HELP_RESPONSES["Help: Application rejected, what next?"] + "\n\n"
			"**2. लॉगिन/आईडी भूल गए:**\n" + HELP_RESPONSES["Help: Forgot password or beneficiary ID"] + "\n\n"
			"**3. स्थिति फँसी हुई/अपडेट नहीं:**\n" + HELP_RESPONSES["Help: Application status is stuck or not updating"] + "\n\n"
			"**4. सामान्य सहायता/अन्य:**\n" + HELP_RESPONSES["Help: General assistance needed"]
		)

	# --- Tamil Responses (Add your Tamil translations here, keeping the structure) ---
	elif target_lang == 'ta':
		HELP_RESPONSES = {
			"Help: Application rejected, what next?":
				"* **காரணத்தைச் சரிபார்க்கவும்:** நிராகரிப்புக்கான காரணத்தை அறிய **உள்நுழையவும்**: " + LOGIN_URL + "\n"
				"* **நடவடிக்கை:** சிக்கலை **சரிசெய்து** (ஆவணத்தைப் பதிவேற்றவும்) **மீண்டும் சமர்ப்பிக்கவும்**.\n"
				"* **உதவி எண்:** SUJHAA டாஷ்போர்டில் உள்ள **ஆதரவு** அம்சத்தைப் பயன்படுத்தவும் அல்லது **" + HELPLINE + "** என்ற எண்ணில் அழைக்கவும்.",
				
			"Help: Forgot password or beneficiary ID":
				"* **மறந்த கடவுச்சொல்:** [**உள்நுழைவுப் பக்கத்திற்கு**](" + LOGIN_URL + ") சென்று 'கடவுச்சொல்லை மறந்தீர்களா?' என்பதைக் கிளிக் செய்யவும்.\n"
				"* **பயனாளி ஐடி:** உங்கள் பதிவு செய்யப்பட்ட **மின்னஞ்சல் இன்பாக்ஸை** சரிபார்க்கவும்.\n"
				"* **தொடர்புக்கு:** மேலதிக உதவிக்கு **" + HELPLINE + "** என்ற எண்ணில் அழைக்கவும்.",
				
			"Help: Application status is stuck or not updating":
				"* **காத்திருக்கவும்:** சரிபார்ப்பு செயல்முறைகளுக்கு பல வாரங்கள் ஆகலாம்.\n"
				"* **கணக்கைச் சரிபார்க்கவும்:** **உள்நுழையவும்** (" + LOGIN_URL + ") மற்றும் **ஆவணக் கோரிக்கை** எதுவும் நிலுவையில் இல்லை என்பதை உறுதிப்படுத்தவும்.\n"
				"* **கைமுறைச் சரிபார்ப்பு:** காலதாமதம் அதிகமாக இருந்தால், **" + HELPLINE + "** என்ற எண்ணில் அழைக்கவும்.",
				
			"Help: General assistance needed":
				"* **SUJHAA டாஷ்போர்டு:** டாஷ்போர்டில் உள்ள **உதவி மற்றும் ஆதரவு** பகுதியைப் பயன்படுத்தவும்.\n"
				"* **உதவி எண்:** SUJHAA உதவி மையத்தை **" + HELPLINE + "** என்ற எண்ணில் அழைக்கவும்.",
		}
		
		# ✅ MASTER RESPONSE: Consolidated response for "போர்ட்டலில் எனக்கு ஒரு சிக்கல் உள்ளது"
		MASTER_RESPONSE = (
			"பொதுவான SUJHAA சிக்கல்களுக்கான விரைவான வழிகாட்டி இங்கே:\n\n"
			"**1. விண்ணப்பம் நிராகரிப்பு:**\n" + HELP_RESPONSES["Help: Application rejected, what next?"] + "\n\n"
			"**2. உள்நுழைவு/ஐடி மறந்துவிட்டது:**\n" + HELP_RESPONSES["Help: Forgot password or beneficiary ID"] + "\n\n"
			"**3. நிலை மாறாமல் உள்ளது/புதுப்பிக்கவில்லை:**\n" + HELP_RESPONSES["Help: Application status is stuck or not updating"] + "\n\n"
			"**4. பொது உதவி/மற்ற சிக்கல்:**\n" + HELP_RESPONSES["Help: General assistance needed"]
		)
	
	# --- Gujarati Responses (Add your Gujarati translations here, keeping the structure) ---
	elif target_lang == 'gu':
		HELP_RESPONSES = {
			"Help: Application rejected, what next?":
				"* **કારણ તપાસો:** નામંજૂર થવાનું કારણ જોવા માટે **લોગ ઇન** કરો: " + LOGIN_URL + "\n"
				"* **ક્રિયા:** સમસ્યાને **સુધારો** (દસ્તાવેજ અપલોડ કરો) અને **ફરીથી સબમિટ** કરો.\n"
				"* **હેલ્પલાઇન:** SUJHAA ડેશબોર્ડ પર **સહાય** સુવિધાનો ઉપયોગ કરો અથવા **" + HELPLINE + "** પર કોલ કરો.",
				
			"Help: Forgot password or beneficiary ID":
				"* **પાસવર્ડ ભૂલી ગયા:** [**લોગિન પેજ**](" + LOGIN_URL + ") પર 'પાસવર્ડ ભૂલી ગયા' પર ક્લિક કરો.\n"
				"* **લાભાર્થી ID:** તમારા નોંધાયેલ **ઇમેઇલ ઇનબોક્સ** (સ્પામ સહિત) તપાસો.\n"
				"* **સંપર્ક:** વધુ સહાય માટે **" + HELPLINE + "** પર કોલ કરો.",
				
			"Help: Application status is stuck or not updating":
				"* **રાહ જુઓ:** ચકાસણી પ્રક્રિયાઓમાં કેટલાક અઠવાડિયા લાગી શકે છે. પૂરતો સમય આપો.\n"
				"* **એકાઉન્ટ તપાસો:** **લોગ ઇન** કરો (" + LOGIN_URL + ") અને ખાતરી કરો કે કોઈ **દસ્તાવેજ વિનંતી** બાકી નથી.\n"
				"* **મેન્યુઅલ તપાસ:** જો વિલંબ વધુ હોય, તો **" + HELPLINE + "** પર કોલ કરો。",
				
			"Help: General assistance needed":
				"* **SUJHAA ડેશબોર્ડ:** ડેશબોર્ડની અંદર ઉપલબ્ધ **સહાય અને સમર્થન** વિભાગનો ઉપયોગ કરો.\n"
				"* **હેલ્પલાઇન:** SUJHAA હેલ્પ ડેસ્કને **" + HELPLINE + "** પર કોલ કરો.",
		}
		
		# ✅ MASTER RESPONSE: Consolidated response for "પોર્ટલ પર મને એક સમસ્યા છે"
		MASTER_RESPONSE = (
			"સામાન્ય SUJHAA સમસ્યાઓ માટેની ઝડપી માર્ગદર્શિકા અહીં છે:\n\n"
			"**1. અરજી નામંજૂર:**\n" + HELP_RESPONSES["Help: Application rejected, what next?"] + "\n\n"
			"**2. લોગિન/ID ભૂલી ગયા:**\n" + HELP_RESPONSES["Help: Forgot password or beneficiary ID"] + "\n\n"
			"**3. સ્થિતિ અટકી ગઈ/અપડેટ નથી:**\n" + HELP_RESPONSES["Help: Application status is stuck or not updating"] + "\n\n"
			"**4. સામાન્ય સહાય/અન્ય:**\n" + HELP_RESPONSES["Help: General assistance needed"]
		)
	
	# --- Check for hardcoded response first and return immediately if found ---
	
	# ✅ NEW MASTER QUERY CHECK
	
	
	# =========================================================================
	# (Continue with the original prompt for general queries)
	# =========================================================================
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
✅ IMPORTANT INCOME RULE (FIXED)
━━━━━━━━━━━━━━━━━━━━
If user asks about **minimum income eligibility**:

Reply EXACTLY like this (no deviation):

"PM-AJAY does not prescribe a single national minimum income limit.
Income eligibility is determined by **State / UT governments** under SCSP guidelines.
In most states, the annual family income limit generally falls between **₹1 lakh to ₹2.5 lakh**, depending on the specific scheme."

━━━━━━━━━━━━━━━━━━━━
📝 APPLICATION PROCESS (WITH LINKS)
━━━━━━━━━━━━━━━━━━━━
When explaining application steps, ALWAYS include:

- **Registration**: https://sujhaa-frontend.vercel.app/register
- **Login**: https://sujhaa-frontend.vercel.app/login

Example format:
- Register on SUJHAA: https://sujhaa-frontend.vercel.app/register
- Login after verification: https://sujhaa-frontend.vercel.app/login
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
				"ta": "மன்னிக்கவும், குரலை புரிந்துகொள்ள முடியவில்லை。",
				"gu": "માફ કરશો, અવાજ સમજાયો નથી。",
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

	# IMPORTANT: Call build_prompt to get the response (or the full prompt text)
	prompt_or_response = build_prompt(user_query, history_text, target_lang)

	# If prompt_or_response is a hardcoded support response (either specific or master), use it directly
	if user_query.startswith("Help:") :
		ai_resp = prompt_or_response
	else:
		# Process through the AI model
		try:
			ai_resp = model.generate_content(prompt_or_response).text
		except Exception as e:
			# print(f"Gemini API Error: {e}") # Uncomment for debugging
			fallback = {
				'hi': "अभी जानकारी उपलब्ध नहीं है। कृपया बाद में प्रयास करें।",
				'ta': "தகவல் கிடைக்கவில்லை. பின்னர் முயற்சிக்கவும்。",
				'gu': "માહિતી ઉપલબ્ધ નથી. થોડા સમય પછી પ્રયત્ન કરો。",
				'en': "I cannot respond right now. Please try again later."
			}
			ai_resp = fallback.get(target_lang, fallback["en"])

	tts_audio = text_to_speech(ai_resp, target_lang) if req.wants_audio else None

	return {
		"text": ai_resp,
		"language": target_lang,
		"tts_audio": tts_audio
	}