import os
import uuid
import re
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import asyncio
import edge_tts

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['REPORTS_FOLDER'] = 'reports'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max limit
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure necessary directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)
app.config['AUDIO_FOLDER'] = os.path.join(app.root_path, 'static', 'audio')
os.makedirs(app.config['AUDIO_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    role = db.Column(db.String(50), nullable=False)
    avatar_path = db.Column(db.String(255), nullable=True)

class TrainingSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50), unique=True, nullable=False)
    module_type = db.Column(db.String(50), default="Communication")
    mode = db.Column(db.String(20), default="voice")
    input_language = db.Column(db.String(50), default="English")
    reply_language = db.Column(db.String(50), default="English")
    overall_score = db.Column(db.Integer, default=85)
    fluency_score = db.Column(db.Integer, default=85)
    grammar_score = db.Column(db.Integer, default=80)
    vocabulary_score = db.Column(db.Integer, default=88)
    total_words = db.Column(db.Integer, default=0)
    total_exchanges = db.Column(db.Integer, default=1)
    duration_mins = db.Column(db.Integer, default=5)
    strengths = db.Column(db.Text, nullable=True)
    weaknesses = db.Column(db.Text, nullable=True)
    recommendations = db.Column(db.Text, nullable=True)
    transcript_summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

MULTILINGUAL_AI_COACHING = {
    'en': {
        'name': 'English',
        'greeting': 'Your message has been processed with real-time NLP analysis. Here is your evaluation:',
        'tip': 'Practice pacing and incorporate strong transitional words to enhance speech flow.',
        'corrected_intro': 'Suggested Revision for Clarity & Professionalism',
        'strengths_default': ['Clear articulate thought flow', 'Appropriate core vocabulary', 'Good overall coherence'],
        'weaknesses_default': ['Occasional hesitation or filler phrases', 'Could benefit from advanced connectors'],
        'plan_step_1': 'Practice speaking with deliberate 2-second pauses rather than verbal fillers.',
        'plan_step_2': 'Incorporate sophisticated transitional phrases (e.g., furthermore, consequently).',
        'plan_step_3': 'Review sentence structure to eliminate fragmented clauses.'
    },
    'ta': {
        'name': 'Tamil',
        'greeting': 'உங்கள் கருத்து தெளிவாக உள்ளது. மொழி ஆளுமை மற்றும் பேசும் வேகத்தை மேம்படுத்த சில பரிந்துரைகள்:',
        'tip': 'வாக்கியங்களுக்கு இடையே தேவையின்றி இடைவெளி விடுவதைத் தவிர்த்து சரளமாகப் பேசப் பழகுங்கள்.',
        'corrected_intro': 'தெளிவான மற்றும் தொழில்முறை வாக்கிய அமைப்பு:',
        'strengths_default': ['நல்ல கருத்துப் பரிமாற்றம்', 'சரியான உச்சரிப்பு முறை', 'பொருத்தமான சொல் பயன்பாடு'],
        'weaknesses_default': ['சிறு தயக்கங்கள்', 'வாக்கிய இணைப்புகளில் கூடுதல் கவனம் தேவை'],
        'plan_step_1': 'தயக்கங்களைத் தவிர்த்து தொடர்ச்சியாக பேச பயிற்சி செய்யுங்கள்.',
        'plan_step_2': 'புதிய சொற்களஞ்சியங்களை தினசரி வாக்கியங்களில் பயன்படுத்தி பாருங்கள்.',
        'plan_step_3': 'சரியான நிறுத்தற்குறிகளுடன் பேசப் பழகவும்.'
    },
    'hi': {
        'name': 'Hindi',
        'greeting': 'आपकी बात स्पष्ट है। भाषा प्रवाह, व्याकरण और शब्द चयन को और बेहतर बनाने के लिए विश्लेषण:',
        'tip': 'वाक्यों के बीच अनावश्यक ठहराव से बचें और आत्मविश्वास से बोलें।',
        'corrected_intro': 'सुझाया गया परिष्कृत एवं स्पष्ट वाक्य:',
        'strengths_default': ['स्पष्ट अभिव्यक्ति', 'सटीक शब्द चयन', 'संतुलित वाक्य संरचना'],
        'weaknesses_default': ['बोलने में हल्का संकोच', 'संयोजी शब्दों का सीमित प्रयोग'],
        'plan_step_1': 'बिना झिझक के निरंतर बोलने का दैनिक अभ्यास करें।',
        'plan_step_2': 'उन्नत शब्दावली और नए मुहावरों का प्रयोग बढ़ाएं।',
        'plan_step_3': 'व्याकरणिक शुद्धता पर विशेष ध्यान दें.'
    },
    'te': {
        'name': 'Telugu',
        'greeting': 'మీ భావవ్యక్తీకరణ బాగుంది. వ్యాకరణం మరియు వాక్య నిర్మాణాన్ని మరింత మెరుగుపరచడానికి విశ్లేషణ:',
        'tip': 'వాక్యాల మధ్య అనవసరమైన విరామాలను తగ్గించి ధారాళంగా మాట్లాడటం ప్రాక్టీస్ చేయండి.',
        'corrected_intro': 'స్పష్టమైన మరియు వృత్తిపరమైన వాక్య నిర్మాణం:',
        'strengths_default': ['స్పష్టమైన ఆలోచన', 'సరియైన పదాల ఎంపిక', 'మంచి సంభాషణ ప్రవాహం'],
        'weaknesses_default': ['కొద్దిపాటి తడబాటు', 'వాక్య సంధానంలో జాగ్రత్త అవసరం'],
        'plan_step_1': 'ధారాళంగా మాట్లాడటానికి రోజువారీ అభ్యాసం చేయండి.',
        'plan_step_2': 'నూతన పదకోశాన్ని వినియోగించండి.',
        'plan_step_3': 'ఆత్మవిశ్వాసంతో వాక్యాలను ముగించండి.'
    },
    'ml': {
        'name': 'Malayalam',
        'greeting': 'നിങ്ങളുടെ ആശയവിനിമയം വ്യക്തമാണ്. വാക്യഘടനയും സംഭാഷണ ശൈലിയും കൂടുതൽ മെച്ചപ്പെടുത്താനുള്ള അവലോകനം:',
        'tip': 'സംഭാഷണത്തിനിടയിലെ അനാവശ്യമായ ഇടവേളകൾ കുറച്ച് സ്വാഭാവികമായി സംസാരിക്കാൻ ശ്രമിക്കുക.',
        'corrected_intro': 'കൂടുതൽ വ്യക്തവും പ്രൊഫഷണലുമായ തിരുത്തൽ:',
        'strengths_default': ['വ്യക്തമായ ആശയവിനിമയം', 'നല്ല പദസമ്പത്ത്', 'ശരിയായ ഉച്ചാരണം'],
        'weaknesses_default': ['ചെറിയ പതർച്ച', 'വാക്യങ്ങളുടെ തുടർച്ചയിൽ ശ്രദ്ധ വേണം'],
        'plan_step_1': 'സ്വാഭാവികമായ ഒഴുക്കോടെ സംസാരിക്കാൻ പരിശീലിക്കുക.',
        'plan_step_2': 'പുതിയ വാക്കുകൾ സംഭാഷണത്തിൽ ഉൾപ്പെടുത്തുക.',
        'plan_step_3': 'ശരിയായ വാക്യഘടന ഉറപ്പാക്കുക.'
    },
    'kn': {
        'name': 'Kannada',
        'greeting': 'ನಿಮ್ಮ ಸಂವಹನ ಸ್ಪಷ್ಟವಾಗಿದೆ. ನಿರರ್ಗಳತೆ ಮತ್ತು ವ್ಯಾಕರಣ ನಿಖರತೆಯನ್ನು ಹೆಚ್ಚಿಸಲು ವಿಶ್ಲೇಷಣೆ:',
        'tip': 'ಮಾತನಾಡುವಾಗ ಅನಗತ್ಯ ವಿರಾಮಗಳನ್ನು ತಪ್ಪಿಸಿ ನಿರರ್ಗಳತೆಗೆ ಒತ್ತು ನೀಡಿ.',
        'corrected_intro': 'ಸ್ಪಷ್ಟ ಮತ್ತು ವೃತ್ತಿಪರ ವಾಕ್ಯ ರಚನೆ:',
        'strengths_default': ['ಉತ್ತಮ ಅಭಿವ್ಯಕ್ತಿ', 'ಸೂಕ್ತ ಶಬ್ದಬಳಕೆ', 'ಸ್ಪಷ್ಟ ಆಲೋಚನೆ'],
        'weaknesses_default': ['ಸ್ವಲ್ಪ ಹಿಂಜರಿಕೆ', 'ಸಂಕೀರ್ಣ ವಾಕ್ಯಗಳಲ್ಲಿ ಸುಧಾರಣೆಯ ಅಗತ್ಯವಿದೆ'],
        'plan_step_1': 'ದಿನನಿತ್ಯ ನಿರರ್ಗಳವಾಗಿ ಮಾತನಾಡುವ ಅಭ್ಯಾಸ ಮಾಡಿ.',
        'plan_step_2': 'ವ್ಯಾಕರಣಬದ್ಧ ವಾಕ್ಯ ರಚನೆಗೆ ಗಮನ ಕೊಡಿ.',
        'plan_step_3': 'ಹೊಸ ಪದಗಳನ್ನು ಬಳಸಿ ಸಂಭಾಷಿಸಿ.'
    },
    'bn': {
        'name': 'Bengali',
        'greeting': 'আপনার বক্তব্য স্পষ্ট। ভাষার সাবলীলতা ও ব্যাকরণগত নির্ভুলতা বৃদ্ধির জন্য বিশ্লেষণ:',
        'tip': 'বাক্যের মাঝে অতিরিক্ত বিরতি এড়িয়ে সাবলীলভাবে কথা বলার অভ্যাস করুন।',
        'corrected_intro': 'স্পষ্ট ও পেশাদার বাক্য গঠন:',
        'strengths_default': ['স্পষ্ট যোগাযোগ', 'সঠিক শব্দচয়ন', 'প্রশংসনীয় আত্মবিশ্বাস'],
        'weaknesses_default': ['সামান্য দ্বিধা', 'বাক্য সংযোজকের ব্যবহারে উন্নতি প্রয়োজন'],
        'plan_step_1': 'নিয়মিত কথা বলার সাবলীলতা অনুশীলন করুন।',
        'plan_step_2': 'নতুন শব্দ ভাণ্ডার প্রয়োগ করুন।',
        'plan_step_3': 'ব্যাকরণের সঠিকতার দিকে নজর দিন।'
    },
    'mr': {
        'name': 'Marathi',
        'greeting': 'तुमचा संवाद स्पष्ट आहे. संभाषण कौशल्य आणि व्याकरण अचूकता वाढवण्यासाठी विश्लेषण:',
        'tip': 'बोलताना अनावश्यक थांबणे टाळा आणि वाक्यप्रवाहावर लक्ष केंद्रित करा.',
        'corrected_intro': 'सुधारित आणि व्यावसायिक वाक्यरचना:',
        'strengths_default': ['स्पष्ट विचार मांडणी', 'योग्य शब्दांची निवड', 'चांगला आत्मविश्वास'],
        'weaknesses_default': ['थोडासा संकोच', 'वाक्यांच्या जोडणीत सुधारणा आवश्यक'],
        'plan_step_1': 'सातत्यपूर्ण संभाषणाचा सराव करा.',
        'plan_step_2': 'प्रगत शब्दावलीचा वापर वाढवा.',
        'plan_step_3': 'व्याकरणाच्या नियमांचे पालन करा.'
    },
    'gu': {
        'name': 'Gujarati',
        'greeting': 'તમારો સંવાદ સ્પષ્ટ છે. ભાષા પ્રવાહ અને વ્યાકરણની ચોકસાઈ વધારવા માટેનું વિશ્લેષણ:',
        'tip': 'બોલતી વખતે બિનજરૂરી અટકવાનું ટાળો અને આત્મવિશ્વાસ સાથે બોલો.',
        'corrected_intro': 'સ્પષ્ટ અને વ્યવસાયિક વાક્ય રચના:',
        'strengths_default': ['સારી અભિવ્યક્તિ', 'યોગ્ય શબ્દ પસંદગી', 'સંતોષકારક સંવાદ'],
        'weaknesses_default': ['હળવો સંકોચ', 'વાક્ય જોડાણમાં વધુ ધ્યાન આપવું'],
        'plan_step_1': 'દરરોજ બોલવાનો પ્રવાહ સુધારવા પ્રેક્ટિસ કરો.',
        'plan_step_2': 'નવા શબ્દોનો યોગ્ય ઉપયોગ કરો.',
        'plan_step_3': 'વાક્યની રચના વધુ મજબૂત બનાવો.'
    },
    'pa': {
        'name': 'Punjabi',
        'greeting': 'ਤੁਹਾਡਾ ਸੁਨੇਹਾ ਸਪਸ਼ਟ ਹੈ। ਬੋਲਚਾਲ ਦੀ ਰਵਾਨਗੀ ਅਤੇ ਵਿਆਕਰਨ ਸੁਧਾਰਨ ਲਈ ਵਿਸ਼ਲੇਸ਼ਣ:',
        'tip': 'ਗੱਲਬਾਤ ਦੌਰਾਨ ਝਿਜਕ ਨੂੰ ਦੂਰ ਕਰਕੇ ਰਵਾਨਗੀ ਨਾਲ ਬੋਲਣ ਦਾ ਅਭਿਆਸ ਕਰੋ।',
        'corrected_intro': 'ਸੁਧਾਰਿਆ ਅਤੇ ਪੇਸ਼ੇਵਰ ਵਾਕ ਰੂਪ:',
        'strengths_default': ['ਸਪਸ਼ਟ ਵਿਚਾਰ', 'ਵਧੀਆ ਸ਼ਬਦਾਵਲੀ', 'ਚੰਗਾ ਆਤਮਵਿਸ਼ਵਾਸ'],
        'weaknesses_default': ['ਥੋੜ੍ਹੀ ਝਿਜਕ', 'ਵਾਕ ਜੋੜਾਂ ਵਿੱਚ ਸੁਧਾਰ ਦੀ ਲੋੜ'],
        'plan_step_1': 'ਲਗਾਤਾਰ ਬੋਲਣ ਦਾ ਅਭਿਆਸ ਜਾਰੀ ਰੱਖੋ।',
        'plan_step_2': 'ਨਵੇਂ ਸ਼ਬਦਾਂ ਦੀ ਵਰਤੋਂ ਵਧਾਓ।',
        'plan_step_3': 'ਵਿਆਕਰਨਿਕ ਸ਼ੁੱਧਤਾ ਵੱਲ ਧਿਆਨ ਦਿਓ।'
    },
    'ur': {
        'name': 'Urdu',
        'greeting': 'آپ کا اندازِ بیان واضح ہے۔ روانی، گرامر اور الفاظ کے انتخاب کو مزید نکھارنے کا تجزیہ:',
        'tip': 'بات چیت میں بلاوجہ وقفے سے گریز کریں اور اعتماد کے ساتھ بات کریں۔',
        'corrected_intro': 'بہتر اور معیاری جملے کی ساخت:',
        'strengths_default': ['واضح اظہار', 'موزوں الفاظ کا چناؤ', 'اچھی خود اعتمادی'],
        'weaknesses_default': ['ہلکا سا تردد', 'جملوں کے ربط میں مزید بہتری کی گنجائش'],
        'plan_step_1': 'مسلسل روانی کے ساتھ بولنے کی مشق کریں۔',
        'plan_step_2': 'نئے اور معیاری الفاظ کا استعمال کریں۔',
        'plan_step_3': 'قواعد و انشاء پر خصوصی توجہ دیں۔'
    }
}

# Initialize Database and seeded User
with app.app_context():
    db.create_all()
    if not User.query.first():
        default_user = User(
            name="Jane Doe",
            email="jane.doe@example.com",
            role="Premium Learner",
            avatar_path=None
        )
        db.session.add(default_user)
        db.session.commit()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compute_nav_stats():
    """Compute lightweight live navbar stats from the database."""
    sessions = TrainingSession.query.all()
    if not sessions:
        return {
            "today_mins": 0,
            "goal_pct": 0,
            "streak": 0,
            "avg_fluency": 0
        }
    
    today = datetime.utcnow().date()
    today_mins = sum(s.duration_mins or 0 for s in sessions if s.created_at and s.created_at.date() == today)
    goal_pct = min(100, round((today_mins / 20) * 100))
    
    session_dates = sorted(list({s.created_at.date() for s in sessions if s.created_at}), reverse=True)
    streak = 0
    if session_dates:
        if session_dates[0] == today or session_dates[0] == (today - timedelta(days=1)):
            expected = session_dates[0]
            for d in session_dates:
                if d == expected:
                    streak += 1
                    expected = expected - timedelta(days=1)
                else:
                    break
                    
    avg_fluency = round(sum(s.fluency_score or 0 for s in sessions) / len(sessions))
    
    return {
        "today_mins": today_mins,
        "goal_pct": goal_pct,
        "streak": streak,
        "avg_fluency": avg_fluency
    }

def compute_dashboard_stats():
    """Compute comprehensive dynamic statistics for the Dashboard."""
    sessions = TrainingSession.query.order_by(TrainingSession.created_at.desc()).all()
    total_sessions = len(sessions)
    
    today = datetime.utcnow().date()
    today_sessions = [s for s in sessions if s.created_at and s.created_at.date() == today]
    today_mins = sum(s.duration_mins or 0 for s in today_sessions)
    target_mins = 20
    goal_progress_pct = min(100, round((today_mins / target_mins) * 100))
    mins_left = max(0, target_mins - today_mins)
    
    session_dates = sorted(list({s.created_at.date() for s in sessions if s.created_at}), reverse=True)
    streak = 0
    if session_dates:
        if session_dates[0] == today or session_dates[0] == (today - timedelta(days=1)):
            expected = session_dates[0]
            for d in session_dates:
                if d == expected:
                    streak += 1
                    expected = expected - timedelta(days=1)
                else:
                    break

    if not sessions:
        start_of_week = today - timedelta(days=today.weekday())
        heatmap_days = []
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        for i in range(7):
            d = start_of_week + timedelta(days=i)
            heatmap_days.append({
                "name": day_names[i],
                "date": d.strftime("%b %d"),
                "mins": 0,
                "opacity": 0.05,
                "is_zero": True
            })
            
        return {
            "total_sessions": 0,
            "total_speaking_time": 0,
            "avg_confidence": 0,
            "improvement": "0%",
            "ai_feedback": {
                "top_strength": "No data available.",
                "top_weakness": "No data available.",
                "suggested_focus": "Complete a practice session to receive personalized insights."
            },
            "daily_goal": {
                "today_minutes": 0,
                "target_minutes": target_mins,
                "progress_percent": 0,
                "minutes_left": target_mins,
                "streak_days": 0
            },
            "distribution": [0, 0, 0, 0],
            "distribution_labels": ['Communication', 'Tech Interviews', 'HR Interviews', 'Voice Training'],
            "voice_analytics": {
                "speaking_speed": 0,
                "speed_status": "No data",
                "pause_frequency": 0,
                "filler_words": 0,
                "filler_status": "No data"
            },
            "recent_sessions": [],
            "heatmap": heatmap_days,
            "has_data": False
        }

    total_speaking_time = sum(s.duration_mins or 0 for s in sessions)
    avg_confidence = round(sum(s.overall_score or 0 for s in sessions) / total_sessions)
    
    if total_sessions >= 2:
        half = total_sessions // 2
        recent_avg = sum(s.overall_score or 0 for s in sessions[:half]) / half
        older_avg = sum(s.overall_score or 0 for s in sessions[half:]) / (total_sessions - half)
        diff = round(recent_avg - older_avg)
        improvement = f"+{diff}%" if diff > 0 else f"{diff}%"
    else:
        improvement = "0%"

    latest = sessions[0]
    top_strength = latest.strengths.split('|')[0].strip() if latest.strengths else "Clear pronunciation and steady pacing."
    top_weakness = latest.weaknesses.split('|')[0].strip() if latest.weaknesses else "Occasional use of filler words."
    suggested_focus = latest.recommendations.split('|')[0].strip() if latest.recommendations else "Practice structured answers and deliberate pausing."

    comm_cnt = len([s for s in sessions if s.module_type == 'Communication'])
    tech_cnt = len([s for s in sessions if 'Tech' in (s.module_type or '') or s.module_type == 'Mock Interview'])
    hr_cnt = len([s for s in sessions if 'HR' in (s.module_type or '')])
    voice_cnt = len([s for s in sessions if 'Voice' in (s.module_type or '')])
    dist_total = max(1, comm_cnt + tech_cnt + hr_cnt + voice_cnt)
    distribution = [
        round((comm_cnt / dist_total) * 100),
        round((tech_cnt / dist_total) * 100),
        round((hr_cnt / dist_total) * 100),
        round((voice_cnt / dist_total) * 100)
    ]

    total_words = sum(s.total_words or 0 for s in sessions)
    speaking_speed = round(total_words / max(1, total_speaking_time)) if total_speaking_time > 0 and total_words > 0 else 0
    pause_frequency = max(1, round(sum(s.total_exchanges or 0 for s in sessions) / total_sessions)) if total_sessions > 0 else 0
    filler_words = sum(max(0, (100 - (s.fluency_score or 80)) // 3) for s in sessions)

    start_of_week = today - timedelta(days=today.weekday())
    heatmap_days = []
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    for i in range(7):
        d = start_of_week + timedelta(days=i)
        d_mins = sum(s.duration_mins or 0 for s in sessions if s.created_at and s.created_at.date() == d)
        opacity = 0.05 if d_mins == 0 else min(1.0, 0.2 + (d_mins / 40) * 0.8)
        heatmap_days.append({
            "name": day_names[i],
            "date": d.strftime("%b %d"),
            "mins": d_mins,
            "opacity": round(opacity, 2),
            "is_zero": (d_mins == 0)
        })

    recent_sessions_list = []
    for s in sessions[:5]:
        created = s.created_at or datetime.utcnow()
        if created.date() == today:
            date_label = "Today"
        elif created.date() == (today - timedelta(days=1)):
            date_label = "Yesterday"
        else:
            date_label = created.strftime("%b %d")
            
        recent_sessions_list.append({
            "session_id": s.session_id,
            "date_label": date_label,
            "time_label": created.strftime("%I:%M %p"),
            "module_type": s.module_type,
            "mode": (s.mode or 'voice').capitalize(),
            "duration_mins": s.duration_mins or 5,
            "overall_score": s.overall_score or 0
        })

    return {
        "total_sessions": total_sessions,
        "total_speaking_time": total_speaking_time,
        "avg_confidence": avg_confidence,
        "improvement": improvement,
        "ai_feedback": {
            "top_strength": top_strength,
            "top_weakness": top_weakness,
            "suggested_focus": suggested_focus
        },
        "daily_goal": {
            "today_minutes": today_mins,
            "target_minutes": target_mins,
            "progress_percent": goal_progress_pct,
            "minutes_left": mins_left,
            "streak_days": streak
        },
        "distribution": distribution,
        "distribution_labels": ['Communication', 'Tech Interviews', 'HR Interviews', 'Voice Training'],
        "voice_analytics": {
            "speaking_speed": speaking_speed,
            "speed_status": "Optimal" if 110 <= speaking_speed <= 160 else "Good",
            "pause_frequency": pause_frequency,
            "filler_words": filler_words,
            "filler_status": "Optimal" if filler_words <= 8 else "Needs Work"
        },
        "recent_sessions": recent_sessions_list,
        "heatmap": heatmap_days,
        "has_data": True
    }

@app.context_processor
def inject_user():
    """Make user data and live dynamic navbar stats available to all templates."""
    user = User.query.first()
    
    # Generate default UI Avatar if no custom upload exists
    if not user:
        avatar_url = "https://ui-avatars.com/api/?name=User&background=0d6efd&color=fff&size=150"
        user_data = {"name": "Jane Doe", "email": "jane.doe@example.com", "role": "Premium Learner", "avatar": avatar_url}
    elif not user.avatar_path:
        avatar_url = f"https://ui-avatars.com/api/?name={user.name.replace(' ', '+')}&background=0d6efd&color=fff&size=150"
        user_data = {"name": user.name, "email": user.email, "role": user.role, "avatar": avatar_url}
    else:
        avatar_url = url_for('uploaded_file', filename=user.avatar_path)
        user_data = {"name": user.name, "email": user.email, "role": user.role, "avatar": avatar_url}
        
    nav_stats = compute_nav_stats()
    return dict(user=user_data, nav_stats=nav_stats)

@app.before_request
def set_default_preferences():
    """Ensure predefined preferences are active as defaults unless changed."""
    if 'email_notifications' not in session:
        session['email_notifications'] = True
    if 'dark_mode' not in session:
        session['dark_mode'] = False
    if 'ai_voice' not in session:
        session['ai_voice'] = 'en'
    if 'ai_voice_type' not in session:
        session['ai_voice_type'] = 'female'

# -------------------------------------------------------------
# Routing: Serve Uploaded Files
# -------------------------------------------------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded user profile pictures."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# -------------------------------------------------------------
# Routing: Dashboard & Dynamic Stats
# -------------------------------------------------------------
@app.route('/')
def dashboard():
    """Main dashboard view with dynamically calculated stats."""
    stats = compute_dashboard_stats()
    return render_template('dashboard.html', stats=stats)

@app.route('/api/dashboard/stats')
def api_dashboard_stats():
    """API endpoint to fetch live dashboard statistics."""
    stats = compute_dashboard_stats()
    return jsonify(stats)

@app.route('/logout')
def logout():
    """Dummy logout route."""
    return redirect(url_for('dashboard'))

@app.route('/profile/update', methods=['POST'])
def update_profile():
    """Handle profile updates from the modal."""
    user = User.query.first()
    
    name = request.form.get('name')
    email = request.form.get('email')
    role = request.form.get('role')
    
    if name:
        user.name = name
    if email:
        user.email = email
    if role:
        user.role = role
        
    # Handle File Upload
    if 'profile_picture' in request.files:
        file = request.files['profile_picture']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Create a unique filename using user ID to avoid overwriting issues/caching issues temporarily
            unique_filename = f"user_{user.id}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            user.avatar_path = unique_filename
            
    db.session.commit()
        
    return redirect(url_for('dashboard'))


# -------------------------------------------------------------
# NLP Engine: Communication Skills Analysis & Linguistic Diagnostics
# -------------------------------------------------------------
def analyze_communication_input(text, mode='voice', input_lang='en', reply_lang='en'):
    """Analyze communication message with comprehensive mistake detection, 
    actionable corrections, linguistic explanations, and professional polish.
    """
    clean_text = text.strip() if text else ""
    if not clean_text:
        clean_text = "Hello, I am practicing communication skills today."

    # Enforce English-only for Text mode input
    if mode == 'text':
        input_lang = 'en'
        
    words = [w for w in re.split(r'\s+', clean_text) if w]
    word_count = len(words)
    base_lang = input_lang.split('-')[0].lower() if '-' in input_lang else input_lang.lower()
    
    mistakes = []
    corrected_sentence = clean_text

    # 1. Verbal Filler Analysis (crucial for spoken communication)
    fillers = ['um', 'uh', 'er', 'ah', 'like', 'you know', 'basically', 'actually', 'sort of', 'kind of']
    lower_text = clean_text.lower()
    found_fillers = []
    for f in fillers:
        matches = re.findall(r'\b' + re.escape(f) + r'\b', lower_text)
        if matches:
            found_fillers.extend(matches)
    filler_count = len(found_fillers)
    
    if mode == 'voice' and filler_count > 0:
        unique_fillers = list(set(found_fillers))
        mistakes.append({
            "what_said": ", ".join([f'"{u}"' for u in unique_fillers]),
            "category": "Verbal Filler / Fluency",
            "what_was_incorrect": f"Used {filler_count} filler word(s) ({', '.join(unique_fillers)})",
            "why_incorrect": "Verbal fillers break listener engagement and reduce perceived confidence and authority.",
            "how_to_correct": "Replace verbal fillers with brief, silent 1-second pauses to organize your thoughts.",
            "corrected_phrase": "Pause silently instead of saying " + ", ".join([f'"{u}"' for u in unique_fillers])
        })
        # Remove filler words from corrected sentence
        for f in ['um', 'uh', 'er', 'ah']:
            corrected_sentence = re.sub(r'\b' + f + r'[, ]*', '', corrected_sentence, flags=re.IGNORECASE)
        corrected_sentence = re.sub(r'\s+', ' ', corrected_sentence).strip()

    # 2. English Linguistic Error Detection
    if base_lang == 'en':
        # A. Subject-Verb Agreement: he/she/it don't -> doesn't
        for m in re.finditer(r"\b(he|she|it)\s+don't\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} doesn't"
            mistakes.append({
                "what_said": orig_match,
                "category": "Subject-Verb Agreement",
                "what_was_incorrect": f"Used 'don\'t' with third-person singular '{sub}'",
                "why_incorrect": f"Third-person singular subjects ('he', 'she', 'it') take 'doesn\'t' (does not), not 'don\'t'.",
                "how_to_correct": f"Use '{fix}' instead of '{orig_match}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # B. Subject-Verb Agreement: he/she/it have -> has
        for m in re.finditer(r"\b(he|she|it)\s+have\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} has"
            mistakes.append({
                "what_said": orig_match,
                "category": "Subject-Verb Agreement",
                "what_was_incorrect": f"Used base verb 'have' with singular subject '{sub}'",
                "why_incorrect": f"Third-person singular subjects take 'has' in the present tense.",
                "how_to_correct": f"Say '{fix}' instead of '{orig_match}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # C. Subject-Verb Agreement: I/you/we/they has -> have
        for m in re.finditer(r"\b(i|you|we|they)\s+has\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} have"
            mistakes.append({
                "what_said": orig_match,
                "category": "Subject-Verb Agreement",
                "what_was_incorrect": f"Used singular 'has' with '{sub}'",
                "why_incorrect": f"The pronoun '{sub}' takes the base verb 'have' in the present tense.",
                "how_to_correct": f"Say '{fix}' instead of '{orig_match}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # D. Subject-Verb Agreement: they/we/you is -> are
        for m in re.finditer(r"\b(they|we|you)\s+is\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} are"
            mistakes.append({
                "what_said": orig_match,
                "category": "Subject-Verb Agreement",
                "what_was_incorrect": f"Singular verb 'is' used with '{sub}'",
                "why_incorrect": f"Plural and second-person pronouns ('they', 'we', 'you') require the plural verb 'are'.",
                "how_to_correct": f"Say '{fix}' instead of '{orig_match}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # E. Indefinite Pronoun Agreement: everyone are / everybody are / each are -> is
        for m in re.finditer(r"\b(everyone|everybody|each\s+of\s+them|anyone|someone|nobody)\s+are\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} is"
            mistakes.append({
                "what_said": orig_match,
                "category": "Indefinite Pronoun Agreement",
                "what_was_incorrect": f"Plural verb 'are' used with singular pronoun '{sub}'",
                "why_incorrect": f"Indefinite pronouns like '{sub}' are grammatically singular and require 'is'.",
                "how_to_correct": f"Change '{orig_match}' to '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # F. Past Tense with Time references: yesterday/last week + present verb
        past_time_regex = r"\b(yesterday|last\s+night|last\s+week|last\s+month|last\s+year|ago)\s+(?:i|we|he|she|they)?\s*(go|see|eat|buy|take|give|come|write|speak|make|do|watch|work|visit)\b"
        for m in re.finditer(past_time_regex, corrected_sentence, re.IGNORECASE):
            time_word = m.group(1)
            present_verb = m.group(2).lower()
            if present_verb in PAST_VERB_PAIRS:
                past_verb = PAST_VERB_PAIRS[present_verb]
                orig_match = m.group(0)
                fix = orig_match.replace(m.group(2), past_verb)
                mistakes.append({
                    "what_said": orig_match,
                    "category": "Verb Tense Inconsistency",
                    "what_was_incorrect": f"Present tense '{present_verb}' used with past time marker '{time_word}'",
                    "why_incorrect": f"Completed actions in the past indicated by '{time_word}' require the simple past tense ('{past_verb}').",
                    "how_to_correct": f"Change '{present_verb}' to '{past_verb}'.",
                    "corrected_phrase": fix
                })
                corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # G. Double past: did / didn't + past verb
        for m in re.finditer(r"\b(did|didn't|did\s+not)\s+(went|saw|ate|bought|took|came|wrote|spoke|made|watched|found)\b", corrected_sentence, re.IGNORECASE):
            aux = m.group(1)
            past_verb = m.group(2).lower()
            if past_verb in BASE_VERB_PAIRS:
                base_verb = BASE_VERB_PAIRS[past_verb]
                orig_match = m.group(0)
                fix = f"{aux} {base_verb}"
                mistakes.append({
                    "what_said": orig_match,
                    "category": "Auxiliary Verb Rule",
                    "what_was_incorrect": f"Double past tense ('{aux} {past_verb}')",
                    "why_incorrect": f"The auxiliary verb '{aux}' already carries the past tense; the following main verb must be in base form ('{base_verb}').",
                    "how_to_correct": f"Use '{aux} {base_verb}' instead of '{aux} {past_verb}'.",
                    "corrected_phrase": fix
                })
                corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # H. Collocation: I am agree -> I agree
        for m in re.finditer(r"\b(i\s+am\s+agree|i'm\s+agree)\b", corrected_sentence, re.IGNORECASE):
            orig_match = m.group(0)
            fix = "I agree"
            mistakes.append({
                "what_said": orig_match,
                "category": "Grammar & Collocation",
                "what_was_incorrect": "Incorrect use of 'am' before verb 'agree'",
                "why_incorrect": "'Agree' is already a verb and does not need the auxiliary 'am'.",
                "how_to_correct": "Say 'I agree' instead of 'I am agree'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # I. Double comparative: more better / more easier
        for m in re.finditer(r"\bmore\s+(better|easier|faster|simpler|cheaper|harder|bigger)\b", corrected_sentence, re.IGNORECASE):
            adj = m.group(1)
            orig_match = m.group(0)
            fix = f"much {adj}" if adj in ['better', 'easier'] else adj
            mistakes.append({
                "what_said": orig_match,
                "category": "Comparative Adjective Error",
                "what_was_incorrect": f"Double comparative '{orig_match}'",
                "why_incorrect": f"'{adj}' is already in comparative form; adding 'more' is redundant.",
                "how_to_correct": f"Say '{fix}' instead of '{orig_match}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # J. Collocation: do a mistake -> make a mistake
        for m in re.finditer(r"\b(do|did|doing|does)\s+(?:a\s+)?mistake\b", corrected_sentence, re.IGNORECASE):
            v = m.group(1).lower()
            orig_match = m.group(0)
            fix = "make a mistake" if v in ['do', 'does'] else "made a mistake" if v == 'did' else "making a mistake"
            mistakes.append({
                "what_said": orig_match,
                "category": "Verb Collocation",
                "what_was_incorrect": f"Used verb '{v}' with 'mistake'",
                "why_incorrect": "In English, the standard verb pairing for 'mistake' is 'make' (make a mistake), not 'do'.",
                "how_to_correct": f"Use '{fix}' instead of '{orig_match}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # K. Preposition: discuss about -> discuss
        for m in re.finditer(r"\bdiscuss\s+about\b", corrected_sentence, re.IGNORECASE):
            orig_match = m.group(0)
            fix = "discuss"
            mistakes.append({
                "what_said": orig_match,
                "category": "Preposition Redundancy",
                "what_was_incorrect": "Redundant preposition 'about' after 'discuss'",
                "why_incorrect": "'Discuss' is a transitive verb that directly takes the topic object without 'about'.",
                "how_to_correct": "Use 'discuss' directly (e.g., 'discuss the project').",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # L. Preposition: listen music / listen him -> listen to
        for m in re.finditer(r"\blisten\s+(music|him|her|them|the\s+teacher|podcast|audio)\b", corrected_sentence, re.IGNORECASE):
            obj = m.group(1)
            orig_match = m.group(0)
            fix = f"listen to {obj}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Missing Preposition",
                "what_was_incorrect": f"Missing preposition 'to' with 'listen'",
                "why_incorrect": "The verb 'listen' requires the preposition 'to' before its object.",
                "how_to_correct": f"Say '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # M. Preposition: married with -> married to
        for m in re.finditer(r"\bmarried\s+with\b", corrected_sentence, re.IGNORECASE):
            orig_match = m.group(0)
            fix = "married to"
            mistakes.append({
                "what_said": orig_match,
                "category": "Preposition Usage",
                "what_was_incorrect": "Used 'married with' instead of 'married to'",
                "why_incorrect": "In standard English, the adjective 'married' pairs with the preposition 'to'.",
                "how_to_correct": "Say 'married to'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # N. Preposition: good in english -> good at
        for m in re.finditer(r"\bgood\s+in\s+(english|speaking|math|coding|programming|communication)\b", corrected_sentence, re.IGNORECASE):
            subj = m.group(1)
            orig_match = m.group(0)
            fix = f"good at {subj}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Preposition Usage",
                "what_was_incorrect": f"Used 'good in' for skill proficiency",
                "why_incorrect": "To express skill or proficiency, the adjective 'good' pairs with 'at'.",
                "how_to_correct": f"Say '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_phrase := fix)

        # O. Pronoun Introduction: Myself Rahul -> I am Rahul / My name is Rahul
        for m in re.finditer(r"\bmyself\s+([A-Za-z]+)\b", corrected_sentence, re.IGNORECASE):
            name = m.group(1)
            orig_match = m.group(0)
            fix = f"I am {name}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Self-Introduction Pronoun Rule",
                "what_was_incorrect": f"Reflexive pronoun 'myself' used as introduction subject",
                "why_incorrect": "'Myself' is a reflexive pronoun and cannot stand alone as the subject of a sentence.",
                "how_to_correct": f"Say '{fix}' or 'My name is {name}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # P. Redundancies: revert back / repeat again
        for m in re.finditer(r"\brevert\s+back\b", corrected_sentence, re.IGNORECASE):
            orig_match = m.group(0)
            fix = "revert"
            mistakes.append({
                "what_said": orig_match,
                "category": "Redundancy Error",
                "what_was_incorrect": "'revert back' is redundant",
                "why_incorrect": "'Revert' already means to reply or return; 'back' is unnecessary.",
                "how_to_correct": "Use 'revert' or 'reply'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        for m in re.finditer(r"\brepeat\s+again\b", corrected_sentence, re.IGNORECASE):
            orig_match = m.group(0)
            fix = "repeat"
            mistakes.append({
                "what_said": orig_match,
                "category": "Redundancy Error",
                "what_was_incorrect": "'repeat again' is redundant",
                "why_incorrect": "'Repeat' already signifies saying or doing something again.",
                "how_to_correct": "Use 'repeat'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Q. Word order: I like very much coding -> I really like coding
        for m in re.finditer(r"\b(i|we|they|he|she)\s+like\s+very\s+much\s+([a-zA-Z\s]+)\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            obj = m.group(2).strip()
            orig_match = m.group(0)
            fix = f"{sub} really like {obj}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Sentence Structure & Word Order",
                "what_was_incorrect": "Misplaced adverb 'very much' between verb and object",
                "why_incorrect": "In English, degree adverbs usually precede the verb ('really like') or appear at the end ('like coding very much').",
                "how_to_correct": f"Say '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

    # Clean punctuation and capitalization
    has_capitalization = clean_text[0].isupper() if clean_text else False
    has_punctuation = clean_text.endswith(('.', '!', '?')) if clean_text else False
    
    if corrected_sentence:
        corrected_sentence = corrected_sentence[0].upper() + corrected_sentence[1:]
        if not corrected_sentence.endswith(('.', '!', '?')):
            corrected_sentence += '.'

    # 3. Dynamic Score Calculations based on identified mistakes
    has_mistakes = len(mistakes) > 0
    if not has_mistakes:
        fluency = max(88, min(98, 85 + min(word_count, 10)))
        grammar = 95 if (has_capitalization and has_punctuation) else 90
        vocab = max(84, min(96, 85 + (2 if word_count > 8 else 0)))
    else:
        penalty = len(mistakes) * 8
        fluency = max(60, min(86, 82 - (filler_count * 5)))
        grammar = max(55, min(80, 85 - penalty))
        vocab = max(65, min(88, 80))
        
    overall = round((fluency * 0.35) + (grammar * 0.35) + (vocab * 0.30))

    # 4. Generate Executive / Professional Polish Version
    clean_lower = clean_text.lower()
    if any(p in clean_lower for p in ["thank you for giving me this opportunity", "first of all", "good morning thank"]):
        professional_polish = "Good morning! Thank you very much for this opportunity to introduce myself and share my qualifications with you today."
    elif any(p in clean_lower for p in ["myself", "my name is", "i am practicing"]):
        professional_polish = f"Good day. I am pleased to introduce myself and discuss my background, key competencies, and professional goals."
    elif any(p in clean_lower for p in ["i want to improve", "how to improve", "practicing communication"]):
        professional_polish = "I am actively working on refining my communication fluency, structuring my thoughts concisely, and delivering impactful presentations."
    elif has_mistakes:
        professional_polish = corrected_sentence
    else:
        # Elevate slightly for executive presence
        professional_polish = corrected_sentence

    # 5. Build Coaching Insights Explanation
    if has_mistakes:
        categories_str = ", ".join(list(set(m['category'] for m in mistakes)))
        explanation = f"Identified {len(mistakes)} area(s) for improvement: {categories_str}. Review each correction breakdown above to master these standard communication rules."
    else:
        explanation = "Your sentence demonstrates accurate grammar, clear phrasing, and strong conversational cadence. To elevate your impact in professional or interview settings, review the executive polish suggestion above."

    # Language coaching templates
    coach_data = MULTILINGUAL_AI_COACHING.get(reply_lang if len(reply_lang) == 2 else 'en', MULTILINGUAL_AI_COACHING['en'])
    
    return {
        "word_count": word_count,
        "filler_count": filler_count,
        "has_mistakes": has_mistakes,
        "mistakes_count": len(mistakes),
        "mistakes": mistakes,
        "fluency": fluency,
        "grammar": grammar,
        "vocabulary": vocab,
        "overall": overall,
        "mode": mode,
        "input_lang": input_lang,
        "reply_lang": reply_lang,
        "reply_lang_name": coach_data['name'],
        "ai_greeting": coach_data['greeting'],
        "tip": coach_data['tip'],
        "corrected_intro": "Suggested Polished Revision" if not has_mistakes else "Grammatically Corrected Sentence",
        "original_text": clean_text,
        "corrected_text": corrected_sentence,
        "professional_polish": professional_polish,
        "explanation": explanation,
        "recommendations": coach_data['strengths_default']
    }


# -------------------------------------------------------------
# Routing: Communication Skill Development Module
# -------------------------------------------------------------
@app.route('/communication')
def communication():
    """Communication module interface supporting multilingual voice and English text."""
    languages = [
        {"code": "en", "name": "English"},
        {"code": "ta", "name": "Tamil"},
        {"code": "hi", "name": "Hindi"},
        {"code": "te", "name": "Telugu"},
        {"code": "ml", "name": "Malayalam"},
        {"code": "kn", "name": "Kannada"},
        {"code": "bn", "name": "Bengali"},
        {"code": "mr", "name": "Marathi"},
        {"code": "gu", "name": "Gujarati"},
        {"code": "pa", "name": "Punjabi"},
        {"code": "ur", "name": "Urdu"}
    ]
    return render_template('communication.html', languages=languages)

@app.route('/api/communication/process', methods=['POST'])
def process_communication():
    """API endpoint to process communication input (voice or text) with NLP analysis and auto-save session."""
    data = request.json or {}
    text = data.get('text', '')
    mode = data.get('input_mode', 'voice') # 'voice' or 'text'
    input_lang = data.get('input_lang', 'en')
    reply_lang = data.get('reply_lang', 'en')
    
    # Requirement: In Text Mode, English is default & only input language
    if mode == 'text':
        input_lang = 'en'
        
    analysis = analyze_communication_input(text, mode=mode, input_lang=input_lang, reply_lang=reply_lang)
    
    # Store session history
    comm_history = session.get('comm_history', [])
    comm_history.append({
        'user_text': text,
        'mode': mode,
        'input_lang': input_lang,
        'reply_lang': reply_lang,
        'analysis': analysis,
        'timestamp': datetime.utcnow().strftime("%H:%M:%S")
    })
    session['comm_history'] = comm_history

    # Language mapping for display
    lang_name_map = {
        'en': 'English', 'ta': 'Tamil', 'hi': 'Hindi', 'te': 'Telugu',
        'ml': 'Malayalam', 'kn': 'Kannada', 'bn': 'Bengali', 'mr': 'Marathi',
        'gu': 'Gujarati', 'pa': 'Punjabi', 'ur': 'Urdu'
    }
    input_lang_display = lang_name_map.get(input_lang, input_lang.capitalize())
    reply_lang_display = lang_name_map.get(reply_lang, reply_lang.capitalize())

    # Get or create active session ID
    comm_session_id = session.get('current_comm_session_id')
    if not comm_session_id:
        comm_session_id = f"COMM-{uuid.uuid4().hex[:6].upper()}"
        session['current_comm_session_id'] = comm_session_id

    # Compute live metrics from comm_history
    total_words = sum(item['analysis']['word_count'] for item in comm_history)
    total_exchanges = len(comm_history)
    avg_fluency = round(sum(item['analysis']['fluency'] for item in comm_history) / total_exchanges)
    avg_grammar = round(sum(item['analysis']['grammar'] for item in comm_history) / total_exchanges)
    avg_vocab = round(sum(item['analysis']['vocabulary'] for item in comm_history) / total_exchanges)
    overall_score = round((avg_fluency * 0.35) + (avg_grammar * 0.35) + (avg_vocab * 0.30))
    duration_mins = max(1, round(total_exchanges * 1.5))
    transcript_summary = " • ".join([f"Ex{i+1}: {item['user_text'][:50]}" for i, item in enumerate(comm_history[:5])])

    strengths_list = []
    weaknesses_list = []
    if avg_fluency >= 80:
        strengths_list.append("High conversational fluency and natural cadence.")
    else:
        weaknesses_list.append("Hesitation during complex expressions; practice breathing pauses.")
    if avg_grammar >= 80:
        strengths_list.append("Strong grammatical accuracy and coherent sentence bounds.")
    else:
        weaknesses_list.append("Occasional subject-verb and tense mismatches in quick replies.")
    if avg_vocab >= 80:
        strengths_list.append("Varied and professional vocabulary selection.")
    else:
        weaknesses_list.append("Repetitive basic adjectives; try incorporating more precise synonyms.")

    strengths_str = " | ".join(strengths_list) if strengths_list else "Clear articulation and responsive delivery."
    weaknesses_str = " | ".join(weaknesses_list) if weaknesses_list else "Practice continuous speech without filler words."
    recommendations_str = "Daily 15-minute speaking practice with focus on deliberate phrasing."

    # Persist live progress immediately into SQLite database
    try:
        existing_sess = TrainingSession.query.filter_by(session_id=comm_session_id).first()
        if existing_sess:
            existing_sess.mode = mode.capitalize()
            existing_sess.input_language = input_lang_display
            existing_sess.reply_language = reply_lang_display
            existing_sess.overall_score = overall_score
            existing_sess.fluency_score = avg_fluency
            existing_sess.grammar_score = avg_grammar
            existing_sess.vocabulary_score = avg_vocab
            existing_sess.total_words = total_words
            existing_sess.total_exchanges = total_exchanges
            existing_sess.duration_mins = duration_mins
            existing_sess.strengths = strengths_str
            existing_sess.weaknesses = weaknesses_str
            existing_sess.recommendations = recommendations_str
            existing_sess.transcript_summary = transcript_summary
        else:
            new_sess = TrainingSession(
                session_id=comm_session_id,
                module_type="Communication",
                mode=mode.capitalize(),
                input_language=input_lang_display,
                reply_language=reply_lang_display,
                overall_score=overall_score,
                fluency_score=avg_fluency,
                grammar_score=avg_grammar,
                vocabulary_score=avg_vocab,
                total_words=total_words,
                total_exchanges=total_exchanges,
                duration_mins=duration_mins,
                strengths=strengths_str,
                weaknesses=weaknesses_str,
                recommendations=recommendations_str,
                transcript_summary=transcript_summary,
                created_at=datetime.utcnow()
            )
            db.session.add(new_sess)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error auto-saving communication session: {e}")
    
    return jsonify({
        "status": "success",
        "analysis": analysis,
        "reply_lang": reply_lang,
        "input_lang": input_lang,
        "mode": mode,
        "session_id": comm_session_id
    })

@app.route('/api/communication/complete_session', methods=['POST'])
def complete_communication_session():
    """Complete communication session, compile holistic metrics, save to DB, and return report."""
    data = request.json or {}
    mode = data.get('mode', 'voice')
    input_lang = data.get('input_lang', 'English')
    reply_lang = data.get('reply_lang', 'English')
    
    if mode == 'text':
        input_lang = 'English'
        
    comm_history = session.get('comm_history', [])
    
    if comm_history:
        total_words = sum(item['analysis']['word_count'] for item in comm_history)
        total_exchanges = len(comm_history)
        avg_fluency = round(sum(item['analysis']['fluency'] for item in comm_history) / total_exchanges)
        avg_grammar = round(sum(item['analysis']['grammar'] for item in comm_history) / total_exchanges)
        avg_vocab = round(sum(item['analysis']['vocabulary'] for item in comm_history) / total_exchanges)
        overall_score = round((avg_fluency * 0.35) + (avg_grammar * 0.35) + (avg_vocab * 0.30))
        duration_mins = max(1, round(total_exchanges * 1.5))
        transcript_summary = " • ".join([f"Ex{i+1}: {item['user_text'][:50]}" for i, item in enumerate(comm_history[:5])])
    else:
        # Default baseline if session completed directly
        total_words = data.get('total_words', 85)
        total_exchanges = data.get('total_exchanges', 3)
        avg_fluency = data.get('fluency_score', 84)
        avg_grammar = data.get('grammar_score', 82)
        avg_vocab = data.get('vocab_score', 86)
        overall_score = round((avg_fluency * 0.35) + (avg_grammar * 0.35) + (avg_vocab * 0.30))
        duration_mins = 4
        transcript_summary = "Completed interactive communication training module."

    # Identify strengths & growth areas based on real performance
    strengths_list = []
    weaknesses_list = []
    
    if avg_fluency >= 80:
        strengths_list.append("High conversational fluency and natural cadence.")
    else:
        weaknesses_list.append("Hesitation during complex expressions; practice breathing pauses.")
        
    if avg_grammar >= 80:
        strengths_list.append("Strong grammatical accuracy and coherent sentence bounds.")
    else:
        weaknesses_list.append("Occasional subject-verb and tense mismatches in quick replies.")
        
    if avg_vocab >= 80:
        strengths_list.append("Varied and professional vocabulary selection.")
    else:
        weaknesses_list.append("Repetitive basic adjectives; try incorporating more precise synonyms.")
        
    if mode == 'voice':
        strengths_list.append("Clear audio delivery and responsive speaking speed.")
    else:
        strengths_list.append("Well-structured written responses with consistent formatting.")
        
    coach_data = MULTILINGUAL_AI_COACHING.get(reply_lang if len(reply_lang) == 2 else 'en', MULTILINGUAL_AI_COACHING['en'])
    recommendations_list = [
        coach_data['plan_step_1'],
        coach_data['plan_step_2'],
        coach_data['plan_step_3']
    ]

    session_id = session.get('current_comm_session_id') or f"COMM-{uuid.uuid4().hex[:6].upper()}"
    
    # Save or update session record in database
    try:
        sess_record = TrainingSession.query.filter_by(session_id=session_id).first()
        if sess_record:
            sess_record.mode = mode.capitalize() if isinstance(mode, str) else mode
            sess_record.input_language = input_lang
            sess_record.reply_language = reply_lang
            sess_record.overall_score = overall_score
            sess_record.fluency_score = avg_fluency
            sess_record.grammar_score = avg_grammar
            sess_record.vocabulary_score = avg_vocab
            sess_record.total_words = total_words
            sess_record.total_exchanges = total_exchanges
            sess_record.duration_mins = duration_mins
            sess_record.strengths = " | ".join(strengths_list)
            sess_record.weaknesses = " | ".join(weaknesses_list)
            sess_record.recommendations = " | ".join(recommendations_list)
            sess_record.transcript_summary = transcript_summary
        else:
            new_session = TrainingSession(
                session_id=session_id,
                module_type="Communication",
                mode=mode.capitalize() if isinstance(mode, str) else mode,
                input_language=input_lang,
                reply_language=reply_lang,
                overall_score=overall_score,
                fluency_score=avg_fluency,
                grammar_score=avg_grammar,
                vocabulary_score=avg_vocab,
                total_words=total_words,
                total_exchanges=total_exchanges,
                duration_mins=duration_mins,
                strengths=" | ".join(strengths_list),
                weaknesses=" | ".join(weaknesses_list),
                recommendations=" | ".join(recommendations_list),
                transcript_summary=transcript_summary,
                created_at=datetime.utcnow()
            )
            db.session.add(new_session)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error finalizing communication session: {e}")
    
    # Reset active session buffer for fresh subsequent practice
    session.pop('current_comm_session_id', None)
    session['comm_history'] = []
    
    return jsonify({
        "status": "success",
        "session_id": session_id,
        "date": datetime.utcnow().strftime("%b %d, %Y • %I:%M %p"),
        "module": "Communication Training",
        "mode": mode.capitalize(),
        "input_language": input_lang,
        "reply_language": reply_lang,
        "overall_score": overall_score,
        "fluency_score": avg_fluency,
        "grammar_score": avg_grammar,
        "vocabulary_score": avg_vocab,
        "total_words": total_words,
        "total_exchanges": total_exchanges,
        "duration_mins": duration_mins,
        "strengths": strengths_list,
        "weaknesses": weaknesses_list,
        "recommendations": recommendations_list,
        "performance_rating": "Advanced Communicator" if overall_score >= 85 else "Proficient Communicator" if overall_score >= 70 else "Developing Communicator"
    })


# -------------------------------------------------------------
# Routing: Interview Skill Development Module
# -------------------------------------------------------------
@app.route('/interview')
def interview():
    """Mock interview module interface."""
    return render_template('interview.html')

@app.route('/voice-trainer')
def voice_trainer():
    """Real-time AI Voice Communication Trainer module."""
    return render_template('voice_trainer.html', languages=SUPPORTED_LANGUAGES)

# -------------------------------------------------------------
# Routing: In-Depth 16+ Question Mock Interview Pipeline
# -------------------------------------------------------------
TOTAL_MOCK_INTERVIEW_QUESTIONS = 16

def build_dynamic_mock_interview_questions(job_role, company_type, domain, skills_str, candidate_name="Candidate", experience="mid"):
    """
    Generates a personalized, comprehensive pool of 16 unique, non-repeating mock interview questions
    structured across all 6 essential interview stages.
    """
    skills_list = [s.strip() for s in skills_str.split(',') if s.strip()]
    skill_1 = skills_list[0] if len(skills_list) > 0 else "core technology stack"
    skill_2 = skills_list[1] if len(skills_list) > 1 else (skills_list[0] if len(skills_list) > 0 else "system tooling")
    skill_3 = skills_list[2] if len(skills_list) > 2 else "software engineering principles"
    
    comp_type = company_type if company_type else "technology company"
    dom = domain if domain else "technology"
    role = job_role if job_role else "Software Engineer"
    name = candidate_name if candidate_name else "Candidate"
    
    questions = [
        # Stage 1: Opening & Role Motivation (Q1 - Q2)
        f"Hello {name}! Welcome to your technical interview for the {role} position at our {comp_type}. To start, could you introduce yourself and walk us through your professional journey in {dom}?",
        f"What specifically drew you to apply for this {role} opportunity at our {comp_type}, and how does working within the {dom} sector align with your career goals?",
        
        # Stage 2: Core Technical Competency & Deep Dive (Q3 - Q6)
        f"Your profile emphasizes expertise in {skill_1}. Could you explain a complex architecture, component, or workflow you built using {skill_1}, and how you ensured high performance and reliability?",
        f"In this role, you will frequently integrate {skill_1} with {skill_2}. Could you share an experience where you combined these technologies to solve a challenging business requirement?",
        f"When developing features with {skill_3}, what is your approach to code modularity, automated testing, and continuous integration (CI/CD) pipelines?",
        f"Can you walk us through a difficult technical bug, memory leak, or performance bottleneck you diagnosed in a {dom} project? What was your step-by-step troubleshooting methodology?",
        
        # Stage 3: System Architecture, Data & Scalability (Q7 - Q9)
        f"If we asked you to design a high-availability, low-latency microservice for {dom} that handles sudden 10x traffic spikes, what architecture, caching strategies, and load balancing would you select?",
        f"How do you evaluate database choices (SQL vs. NoSQL) and API design paradigms (REST vs. GraphQL/gRPC) when handling transactional data in the {dom} domain?",
        f"In a fast-paced {comp_type} environment, how do you manage the balance between rapid feature delivery and minimizing long-term technical debt?",
        
        # Stage 4: Behavioral & Problem Solving (STAR Method) (Q10 - Q12)
        f"Describe a situation where a major project deadline was at risk due to shifting requirements or technical roadblocks. How did you prioritize tasks and lead the project to a successful outcome?",
        f"Tell me about a time you experienced a technical disagreement with a team member or stakeholder regarding system design. How did you navigate the discussion and reach alignment?",
        f"Technology stacks evolve rapidly. Can you describe a scenario where you had to learn an unfamiliar tool or framework on short notice and successfully implement it in production?",
        
        # Stage 5: Domain Expertise & Quality Standards (Q13 - Q15)
        f"What emerging technological innovations (such as AI automation or modern cloud paradigms) do you believe will have the greatest impact on the {dom} industry in the coming years?",
        f"Security, privacy, and compliance are essential in {dom} applications. What defensive coding practices and vulnerability checks do you incorporate into your daily workflow?",
        f"How do you ensure that the technical systems you build translate into exceptional user experience, reliability, and tangible value for end customers in the {dom} space?",
        
        # Stage 6: Leadership, Culture & Closing (Q16)
        f"Reflecting on our conversation today, what unique engineering strength would you bring to our team at this {comp_type}, and what questions do you have for us regarding our team culture or roadmap?"
    ]
    return questions


@app.route('/api/interview/upload_company', methods=['POST'])
def upload_company_details():
    """API endpoint to upload company profile/JD for in-depth 16+ question interview generation."""
    job_role = request.form.get('job_role', 'Candidate')
    company_type = request.form.get('company_type', 'Technology Company')
    domain = request.form.get('industry_domain', 'Technology')
    skills = request.form.get('key_skills', 'Problem Solving, Architecture')
    candidate_name = request.form.get('candidate_name', 'there')
    experience = request.form.get('experience', 'mid')
    
    # Process file upload if provided
    if 'cv_file' in request.files:
        file = request.files['cv_file']
        if file and allowed_file(file.filename):
            pass
            
    questions = build_dynamic_mock_interview_questions(
        job_role=job_role,
        company_type=company_type,
        domain=domain,
        skills_str=skills,
        candidate_name=candidate_name,
        experience=experience
    )
    
    first_question = questions[0]
    
    session['interview_state'] = {
        'question_idx': 1,
        'total_questions': len(questions),
        'job_role': job_role,
        'company_type': company_type,
        'domain': domain,
        'skills': skills,
        'candidate_name': candidate_name,
        'experience': experience,
        'questions': questions,
        'history': []
    }
    
    return jsonify({
        "status": "success", 
        "message": f"Company details processed and {len(questions)}-question interview generated",
        "total_questions": len(questions),
        "first_question": first_question
    })

@app.route('/api/interview/process', methods=['POST'])
def process_interview_response():
    """API endpoint to handle user answer and provide AI feedback across 16+ questions."""
    data = request.json or {}
    answer = data.get('answer', '').strip()
    
    state = session.get('interview_state', {})
    q_idx = state.get('question_idx', 1)
    questions = state.get('questions', [])
    total_q = len(questions) if questions else TOTAL_MOCK_INTERVIEW_QUESTIONS
    
    # Analyze candidate answer quality
    words = answer.split()
    word_count = len(words)
    answer_lower = answer.lower()
    
    if word_count < 10:
        feedback = "Your response is very brief. In competitive interviews, use the STAR format (Situation, Task, Action, Result) to provide concrete context and explain your personal contribution."
    elif any(term in answer_lower for term in ['because', 'result', 'implemented', 'optimized', 'designed', 'tested', 'resolved', 'improved', 'architecture']):
        feedback = "Strong, structured response! You clearly articulated the technical approach and emphasized positive outcomes. Continue demonstrating this clarity."
    else:
        feedback = "Good foundation. To enhance your answer, consider citing quantifiable results or key trade-offs to make your technical experience stand out even more."
        
    is_complete = (q_idx >= total_q)
    
    if not is_complete and q_idx < len(questions):
        next_q = questions[q_idx]
    else:
        next_q = "Thank you for your time and thoughtful responses! This concludes our comprehensive 16-question mock interview. You can review your overall performance in the Reports section."
        
    # Store session history
    interview_history = state.get('history', [])
    interview_history.append({
        'question_idx': q_idx,
        'question': questions[q_idx-1] if q_idx-1 < len(questions) else f"Question {q_idx}",
        'answer': answer,
        'feedback': feedback
    })
    
    state['question_idx'] = q_idx + 1
    state['history'] = interview_history
    session['interview_state'] = state
    
    # Auto-save / upsert interview session in database
    try:
        intv_session_id = session.get('current_interview_session_id')
        if not intv_session_id:
            intv_session_id = f"INTV-{uuid.uuid4().hex[:6].upper()}"
            session['current_interview_session_id'] = intv_session_id
            
        overall_score = min(96, max(74, 80 + min(word_count, 14)))
        total_intv_words = sum(len(item['answer'].split()) for item in interview_history)
        total_intv_exchanges = len(interview_history)
        intv_duration = max(2, round(total_intv_exchanges * 1.5))
        summary_text = f"Practiced {total_intv_exchanges} interview questions for {state.get('job_role', 'Technical Role')}."

        sess_record = TrainingSession.query.filter_by(session_id=intv_session_id).first()
        if sess_record:
            sess_record.overall_score = overall_score
            sess_record.total_words = total_intv_words
            sess_record.total_exchanges = total_intv_exchanges
            sess_record.duration_mins = intv_duration
            sess_record.transcript_summary = summary_text
        else:
            new_session = TrainingSession(
                session_id=intv_session_id,
                module_type="Mock Interview",
                mode="Voice / Text",
                input_language="English",
                reply_language="English",
                overall_score=overall_score,
                fluency_score=86,
                grammar_score=88,
                vocabulary_score=85,
                total_words=total_intv_words,
                total_exchanges=total_intv_exchanges,
                duration_mins=intv_duration,
                strengths="Comprehensive technical depth, structured STAR method responses, domain problem solving.",
                weaknesses="Focus on quantifying business metrics in architectural trade-off answers.",
                recommendations="Continue practicing 16+ question deep mock rounds to maintain high interview endurance.",
                transcript_summary=summary_text,
                created_at=datetime.utcnow()
            )
            db.session.add(new_session)
        db.session.commit()
        
        if is_complete:
            session.pop('current_interview_session_id', None)
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Error auto-saving interview session: {e}")
            
    return jsonify({
        "status": "success",
        "message": "Interview response analyzed",
        "current_question_idx": q_idx,
        "next_question_idx": q_idx + 1 if not is_complete else total_q,
        "total_questions": total_q,
        "feedback": feedback,
        "next_question": next_q,
        "is_complete": is_complete
    })

# -------------------------------------------------------------
# Supported Multilingual Languages
# -------------------------------------------------------------
SUPPORTED_LANGUAGES = [
    {"code": "en", "name": "English"},
    {"code": "ta", "name": "Tamil"},
    {"code": "hi", "name": "Hindi"},
    {"code": "te", "name": "Telugu"},
    {"code": "ml", "name": "Malayalam"},
    {"code": "kn", "name": "Kannada"},
    {"code": "bn", "name": "Bengali"},
    {"code": "mr", "name": "Marathi"},
    {"code": "gu", "name": "Gujarati"},
    {"code": "pa", "name": "Punjabi"},
    {"code": "ur", "name": "Urdu"}
]

# -------------------------------------------------------------
# Routing: Real-Time Voice Trainer NLP Engine
# -------------------------------------------------------------

VOICE_MAP = {
    'en': {'female': 'en-US-AriaNeural', 'male': 'en-US-GuyNeural'},
    'ta': {'female': 'ta-IN-PallaviNeural', 'male': 'ta-IN-ValluvarNeural'},
    'hi': {'female': 'hi-IN-SwaraNeural', 'male': 'hi-IN-MadhurNeural'},
    'ur': {'female': 'ur-PK-UzmaNeural', 'male': 'ur-PK-AsadNeural'},
    'te': {'female': 'te-IN-ShrutiNeural', 'male': 'te-IN-MohanNeural'},
    'ml': {'female': 'ml-IN-SobhanaNeural', 'male': 'ml-IN-MidhunNeural'},
    'kn': {'female': 'kn-IN-SapnaNeural', 'male': 'kn-IN-GaganNeural'},
    'bn': {'female': 'bn-IN-TanishaaNeural', 'male': 'bn-IN-BashkarNeural'},
    'mr': {'female': 'mr-IN-AarohiNeural', 'male': 'mr-IN-ManoharNeural'},
    'gu': {'female': 'gu-IN-DhwaniNeural', 'male': 'gu-IN-NiranjanNeural'},
    'pa': {'female': 'pa-IN-OjasNeural', 'male': 'pa-IN-OjasNeural'},
    'fr': {'female': 'fr-FR-DeniseNeural', 'male': 'fr-FR-HenriNeural'}
}

def generate_voice_tts_file(text, lang_code='en', voice_type='female'):
    """Generate audio file asynchronously for Real-Time Voice Trainer and return static URL."""
    try:
        base_lang = lang_code.split('-')[0].lower() if '-' in lang_code else lang_code.lower()
        if base_lang.startswith('lang:'): 
            base_lang = base_lang.split(':')[1]
            
        gender = 'male' if voice_type in ['male', 'adult_male'] else 'female'
        lang_voices = VOICE_MAP.get(base_lang, VOICE_MAP['en'])
        voice = lang_voices.get(gender, lang_voices.get('female')) if isinstance(lang_voices, dict) else lang_voices
        
        filename = f"live_tts_{uuid.uuid4().hex}.mp3"
        filepath = os.path.join(app.config['AUDIO_FOLDER'], filename)
        
        async def run_edge_tts():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(filepath)
            
        asyncio.run(run_edge_tts())
        return f"/static/audio/{filename}"
    except Exception as e:
        app.logger.warning(f"Voice Trainer TTS Warning: {e}")
        return None

PAST_VERB_PAIRS = {
    'go': 'went', 'see': 'saw', 'eat': 'ate', 'buy': 'bought', 'take': 'took',
    'give': 'gave', 'come': 'came', 'write': 'wrote', 'speak': 'spoke',
    'make': 'made', 'do': 'did', 'watch': 'watched', 'play': 'played',
    'work': 'worked', 'visit': 'visited', 'meet': 'met', 'know': 'knew',
    'get': 'got', 'think': 'thought', 'tell': 'told', 'become': 'became'
}

BASE_VERB_PAIRS = {v: k for k, v in PAST_VERB_PAIRS.items()}

def analyze_realtime_voice_input(text, lang_code='en', voice_type='female'):
    """
    Intelligent NLP analyzer for Real-Time Voice Trainer:
    1. Extracts topic context and crafts natural, non-repetitive conversational AI reply.
    2. Identifies exact mistakes (grammar, tense, subject-verb, prepositions, word choice, idioms).
    3. Produces clear 5-point explanation for each identified error.
    4. Calculates realistic speech & language metrics.
    5. Formulates spoken feedback for AI TTS in the matching language & voice gender.
    """
    cleaned_text = text.strip()
    words = cleaned_text.split()
    word_count = len(words)
    base_lang = lang_code.split('-')[0].lower() if '-' in lang_code else lang_code.lower()
    
    mistakes = []
    corrected_sentence = cleaned_text

    # 1. Linguistic error detection for English
    if base_lang == 'en':
        # Subject-Verb Agreement: he/she/it don't -> doesn't
        for m in re.finditer(r"\b(he|she|it)\s+don't\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} doesn't"
            mistakes.append({
                "what_said": orig_match,
                "category": "Subject-Verb Agreement",
                "what_was_incorrect": f"Incorrect auxiliary 'don't' with third-person singular '{sub}'",
                "why_incorrect": f"Third-person singular subjects ('he', 'she', 'it') take 'doesn't' (does not) instead of 'don't' (do not).",
                "how_to_correct": f"Replace '{orig_match}' with '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Subject-Verb Agreement: he/she/it have -> has
        for m in re.finditer(r"\b(he|she|it)\s+have\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} has"
            mistakes.append({
                "what_said": orig_match,
                "category": "Subject-Verb Agreement",
                "what_was_incorrect": f"Use of base verb 'have' with singular subject '{sub}'",
                "why_incorrect": f"Third-person singular subjects require the singular verb form 'has' in the present tense.",
                "how_to_correct": f"Change 'have' to 'has'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Subject-Verb Agreement: I/you/we/they has -> have
        for m in re.finditer(r"\b(i|you|we|they)\s+has\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} have"
            mistakes.append({
                "what_said": orig_match,
                "category": "Subject-Verb Agreement",
                "what_was_incorrect": f"Use of singular verb 'has' with '{sub}'",
                "why_incorrect": f"The pronoun '{sub}' takes the base verb 'have' in the present tense.",
                "how_to_correct": f"Change 'has' to 'have'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Subject-Verb Agreement: they/we/you is -> are
        for m in re.finditer(r"\b(they|we|you)\s+is\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            orig_match = m.group(0)
            fix = f"{sub} are"
            mistakes.append({
                "what_said": orig_match,
                "category": "Subject-Verb Agreement",
                "what_was_incorrect": f"Singular be-verb 'is' used with '{sub}'",
                "why_incorrect": f"Plural and second-person pronouns ('they', 'we', 'you') require the plural be-verb 'are'.",
                "how_to_correct": f"Change 'is' to 'are'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Past Tense with Time references: yesterday/last week + present verb
        past_time_regex = r"\b(yesterday|last\s+night|last\s+week|last\s+month|last\s+year|ago)\s+(?:i|we|he|she|they)?\s*(go|see|eat|buy|take|give|come|write|speak|make|do|watch|work|visit)\b"
        for m in re.finditer(past_time_regex, corrected_sentence, re.IGNORECASE):
            time_word = m.group(1)
            present_verb = m.group(2).lower()
            if present_verb in PAST_VERB_PAIRS:
                past_verb = PAST_VERB_PAIRS[present_verb]
                orig_match = m.group(0)
                fix = orig_match.replace(m.group(2), past_verb)
                mistakes.append({
                    "what_said": orig_match,
                    "category": "Verb Tense Error",
                    "what_was_incorrect": f"Present tense '{present_verb}' used with past time marker '{time_word}'",
                    "why_incorrect": f"Completed actions in the past indicated by '{time_word}' require the simple past tense ('{past_verb}') instead of the present tense ('{present_verb}').",
                    "how_to_correct": f"Change '{present_verb}' to '{past_verb}'.",
                    "corrected_phrase": fix
                })
                corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Double past: did / didn't + past verb
        for m in re.finditer(r"\b(did|didn't|did\s+not)\s+(went|saw|ate|bought|took|came|wrote|spoke|made|watched)\b", corrected_sentence, re.IGNORECASE):
            aux = m.group(1)
            past_verb = m.group(2).lower()
            if past_verb in BASE_VERB_PAIRS:
                base_verb = BASE_VERB_PAIRS[past_verb]
                orig_match = m.group(0)
                fix = f"{aux} {base_verb}"
                mistakes.append({
                    "what_said": orig_match,
                    "category": "Auxiliary Verb Error",
                    "what_was_incorrect": f"Double past tense ('{aux} {past_verb}')",
                    "why_incorrect": f"The auxiliary verb '{aux}' already carries the past tense; the main verb following it must remain in its base form ('{base_verb}').",
                    "how_to_correct": f"Use '{aux} {base_verb}' instead of '{aux} {past_verb}'.",
                    "corrected_phrase": fix
                })
                corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Idiomatic & Collocation: I am agree -> I agree
        for m in re.finditer(r"\b(i\s+am\s+agree|i'm\s+agree)\b", corrected_sentence, re.IGNORECASE):
            orig_match = m.group(0)
            fix = "I agree"
            mistakes.append({
                "what_said": orig_match,
                "category": "Grammar & Collocation",
                "what_was_incorrect": "Incorrect use of 'am' with active verb 'agree'",
                "why_incorrect": "'Agree' is already a complete verb and does not require the auxiliary verb 'am'.",
                "how_to_correct": "Say 'I agree' instead of 'I am agree'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Double comparative: more better / more easier / etc.
        for m in re.finditer(r"\bmore\s+(better|easier|faster|simpler|cheaper|harder|bigger)\b", corrected_sentence, re.IGNORECASE):
            adj = m.group(1)
            orig_match = m.group(0)
            fix = f"much {adj}" if adj in ['better', 'easier'] else adj
            mistakes.append({
                "what_said": orig_match,
                "category": "Comparative Adjective Error",
                "what_was_incorrect": f"Double comparative '{orig_match}'",
                "why_incorrect": f"'{adj}' is already a comparative adjective; adding 'more' creates an ungrammatical redundancy.",
                "how_to_correct": f"Use '{adj}' or '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Collocation: do a mistake / did a mistake -> make / made a mistake
        for m in re.finditer(r"\b(do|did|doing|does)\s+(?:a\s+)?mistake\b", corrected_sentence, re.IGNORECASE):
            v = m.group(1).lower()
            orig_match = m.group(0)
            fix = "make a mistake" if v in ['do', 'does'] else "made a mistake" if v == 'did' else "making a mistake"
            mistakes.append({
                "what_said": orig_match,
                "category": "Verb Collocation Error",
                "what_was_incorrect": f"Incorrect verb '{v}' used with 'mistake'",
                "why_incorrect": "In English, the natural verb collocation for 'mistake' is 'make' (make a mistake), not 'do'.",
                "how_to_correct": f"Use '{fix}' instead of '{orig_match}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Preposition: discuss about -> discuss
        for m in re.finditer(r"\bdiscuss\s+about\b", corrected_sentence, re.IGNORECASE):
            orig_match = m.group(0)
            fix = "discuss"
            mistakes.append({
                "what_said": orig_match,
                "category": "Preposition Redundancy",
                "what_was_incorrect": "Unnecessary preposition 'about' after 'discuss'",
                "why_incorrect": "'Discuss' is a transitive verb that takes a direct object without 'about'.",
                "how_to_correct": "Use 'discuss' directly (e.g., 'discuss the topic').",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Preposition: listen music / listen him -> listen to
        for m in re.finditer(r"\blisten\s+(music|him|her|them|the\s+teacher)\b", corrected_sentence, re.IGNORECASE):
            obj = m.group(1)
            orig_match = m.group(0)
            fix = f"listen to {obj}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Preposition Error",
                "what_was_incorrect": f"Missing preposition 'to' with 'listen'",
                "why_incorrect": "The verb 'listen' requires the preposition 'to' before a direct object.",
                "how_to_correct": f"Say '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Preposition: married with -> married to
        for m in re.finditer(r"\bmarried\s+with\b", corrected_sentence, re.IGNORECASE):
            orig_match = m.group(0)
            fix = "married to"
            mistakes.append({
                "what_said": orig_match,
                "category": "Preposition Error",
                "what_was_incorrect": "Incorrect preposition 'with' used with 'married'",
                "why_incorrect": "In standard English, one is 'married to' someone, not 'married with'.",
                "how_to_correct": "Use 'married to'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Preposition: good in english -> good at
        for m in re.finditer(r"\bgood\s+in\s+(english|speaking|math|coding|programming|communication)\b", corrected_sentence, re.IGNORECASE):
            subj = m.group(1)
            orig_match = m.group(0)
            fix = f"good at {subj}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Preposition Error",
                "what_was_incorrect": f"Incorrect preposition 'in' with proficiency adjective 'good'",
                "why_incorrect": "To express skill or proficiency, the adjective 'good' pairs with 'at'.",
                "how_to_correct": f"Say '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Pronoun: Myself Rahul -> I am Rahul / My name is Rahul
        for m in re.finditer(r"\bmyself\s+([A-Za-z]+)\b", corrected_sentence, re.IGNORECASE):
            name = m.group(1)
            orig_match = m.group(0)
            fix = f"I am {name}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Pronoun Error",
                "what_was_incorrect": "Reflexive pronoun 'myself' used as introduction subject",
                "why_incorrect": "'Myself' is a reflexive pronoun and cannot stand alone as the subject of a sentence.",
                "how_to_correct": f"Say '{fix}' or 'My name is {name}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Word Order: I like very much coding -> I really like coding
        for m in re.finditer(r"\b(i|we|they|he|she)\s+like\s+very\s+much\s+([a-zA-Z\s]+)\b", corrected_sentence, re.IGNORECASE):
            sub = m.group(1)
            obj = m.group(2).strip()
            orig_match = m.group(0)
            fix = f"{sub} really like {obj}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Sentence Structure & Word Order",
                "what_was_incorrect": "Misplaced adverb 'very much' between transitive verb and object",
                "why_incorrect": "In English, degree adverbs usually precede the verb ('really like') or appear at the end ('like coding very much').",
                "how_to_correct": f"Say '{fix}' or '{sub} like {obj} very much'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Article: an university / an unique -> a
        for m in re.finditer(r"\ban\s+(university|unique|useful|uniform|european)\b", corrected_sentence, re.IGNORECASE):
            w = m.group(1)
            orig_match = m.group(0)
            fix = f"a {w}"
            mistakes.append({
                "what_said": orig_match,
                "category": "Article Error",
                "what_was_incorrect": f"Incorrect article 'an' before consonant sound in '{w}'",
                "why_incorrect": f"Although '{w}' begins with a vowel letter, it starts with a consonant 'y' sound (/juː/), requiring 'a'.",
                "how_to_correct": f"Use '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

        # Uncountable nouns: informations / advices -> information / advice
        for m in re.finditer(r"\b(informations|advices|equipments|furnitures)\b", corrected_sentence, re.IGNORECASE):
            w = m.group(1)
            orig_match = m.group(0)
            fix = w[:-1] if w.endswith('s') else w
            mistakes.append({
                "what_said": orig_match,
                "category": "Uncountable Noun Error",
                "what_was_incorrect": f"Pluralization of uncountable noun '{orig_match}'",
                "why_incorrect": f"'{w}' is an uncountable noun in English and does not take a plural 's'.",
                "how_to_correct": f"Use the singular uncountable form '{fix}'.",
                "corrected_phrase": fix
            })
            corrected_sentence = re.sub(r"\b" + re.escape(orig_match) + r"\b", fix, corrected_sentence, flags=re.IGNORECASE)

    # Clean sentence capitalization and ending punctuation
    if corrected_sentence:
        corrected_sentence = corrected_sentence[0].upper() + corrected_sentence[1:]
        if not corrected_sentence.endswith(('.', '?', '!')):
            corrected_sentence += '.'

    # Build highlighted sentence representations for visual feedback
    highlighted_user_text = cleaned_text
    for mis in mistakes:
        escaped_err = re.escape(mis['what_said'])
        highlighted_user_text = re.sub(
            escaped_err,
            f'<mark class="bg-danger text-white px-2 py-0 rounded shadow-sm fw-semibold" title="{mis["what_was_incorrect"]}">{mis["what_said"]}</mark>',
            highlighted_user_text,
            flags=re.IGNORECASE
        )

    # 2. Contextual Conversational Response (Eliminates repetitive generic replies)
    conversational_reply = generate_contextual_voice_reply(cleaned_text, base_lang, mistakes)
    
    # 3. Calculate Performance Metrics
    has_errors = len(mistakes) > 0
    grammar_score = max(60, 95 - (len(mistakes) * 12)) if has_errors else min(98, 88 + min(word_count, 10))
    fluency_score = min(98, max(70, 75 + min(word_count * 2, 20) - (len(mistakes) * 4)))
    confidence_level = "High" if fluency_score >= 85 and not has_errors else "Solid" if fluency_score >= 75 else "Developing"
    
    # Build tips
    if has_errors:
        primary_mistake = mistakes[0]
        tips = f"Focus on: {primary_mistake['how_to_correct']}"
        spoken_feedback = f"{conversational_reply} Quick tip: remember to say '{primary_mistake['corrected_phrase']}' instead of '{primary_mistake['what_said']}'."
    else:
        tips = "Excellent phrasing and natural speech pace! Keep challenging yourself with complex ideas."
        spoken_feedback = conversational_reply

    analysis_data = {
        "original": cleaned_text,
        "highlighted_original": highlighted_user_text,
        "corrected": corrected_sentence,
        "grammar": f"{grammar_score}%" if not has_errors else f"{len(mistakes)} issue{'s' if len(mistakes)>1 else ''} detected ({grammar_score}%)",
        "structure": "Well-structured thought" if word_count > 6 else "Short expression",
        "vocab": "Varied & expressive" if word_count > 8 else "Standard conversational",
        "fluency": f"{fluency_score}%",
        "length": f"{word_count} words",
        "confidence": confidence_level,
        "tips": tips
    }

    # 4. Generate High-Quality Edge-TTS Audio
    audio_url = generate_voice_tts_file(spoken_feedback, lang_code=base_lang, voice_type=voice_type)

    return {
        "status": "success",
        "reply": conversational_reply,
        "spoken_text": spoken_feedback,
        "audio_url": audio_url,
        "has_mistakes": has_errors,
        "mistakes_count": len(mistakes),
        "mistakes": mistakes,
        "analysis": analysis_data
    }


def generate_contextual_voice_reply(text, lang_code='en', mistakes=None):
    """Generate meaningful, non-repetitive conversational response based on what user actually said."""
    text_lower = text.lower().strip()
    
    if lang_code.startswith('ta'):
        if any(w in text_lower for w in ['வணக்கம்', 'ஹலோ', 'காலை', 'மாலை']):
            return "வணக்கம்! உங்களுடன் உரையாடுவதில் மிக்க மகிழ்ச்சி. இன்று நீங்கள் எந்த தலைப்பைப் பற்றி பேச விரும்புகிறீர்கள்?"
        elif any(w in text_lower for w in ['பெயர்', 'படிக்கிறேன்', 'கல்லூரி', 'பல்கலைக்கழகம்', 'வேலை']):
            return "உங்களை அறிமுகப்படுத்தியதற்கு மிக்க நன்றி! உங்கள் கல்வி மற்றும் பணி அனுபவம் சிறப்பானது. உங்கள் எதிர்கால இலக்குகள் என்ன?"
        elif any(w in text_lower for w in ['ஆங்கிலம்', 'பேச', 'பயிற்சி', 'கற்றுக்கொள்ள']):
            return "தொடர்ந்து பேசிப் பழகுவது உங்கள் மொழித்திறனை வெகுவாக உயர்த்தும். உங்கள் அன்றாட அனுபவங்களை பகிர்ந்துகொள்ளுங்கள்."
        else:
            return "நீங்கள் கூறிய கருத்து மிகவும் பயனுள்ளது. இதைப் பற்றி உங்கள் மேலும் சில எண்ணங்களை பகிர்ந்துகொள்ள முடியுமா?"

    # English Natural Contexts
    # 1. Greetings & Openers
    if re.search(r"\b(hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening)\b", text_lower):
        if re.search(r"\b(how\s+are\s+you|how\s+is\s+it\s+going|how're\s+you)\b", text_lower):
            return "Hello! I am doing wonderful, thank you for asking. How is your day going, and what topic would you like to practice discussing today?"
        return "Hello! It is fantastic to connect with you. What topic or speaking skill are you excited to practice today?"

    # 2. Self Introduction & Background
    if re.search(r"\b(my\s+name\s+is|i\s+am\s+(?:a\s+)?student|studying|graduated|i\s+work\s+as|i'm\s+from|i\s+live\s+in|myself)\b", text_lower):
        return "It's a pleasure to get to know you! Sharing your background out loud is a great communication exercise. What are your biggest interests or projects right now?"

    # 3. Interviews / Career / Work Experience
    if re.search(r"\b(interview|job|career|work|company|project|resume|team|manager|client|developer|engineer|office)\b", text_lower):
        return "That's a very valuable professional perspective. Explaining projects clearly and emphasizing your problem-solving approach makes a strong impression in interviews. How did you and your team tackle that?"

    # 4. Tech / AI / Programming
    if re.search(r"\b(python|javascript|code|coding|software|ai|artificial\s+intelligence|data|web|app|application|algorithm|cloud)\b", text_lower):
        return "Technology is evolving rapidly, and discussing technical concepts out loud is the best way to master them. What kinds of applications or tools are you most interested in building?"

    # 5. Hobbies, Sports & Entertainment
    if re.search(r"\b(hobby|hobbies|music|song|movie|film|book|reading|cricket|football|game|play|travel|traveling|cook|cooking)\b", text_lower):
        return "That sounds like a wonderful experience! Talking about your hobbies helps develop natural inflection and descriptive vocabulary. What was the most memorable part of that for you?"

    # 6. Education / Learning English
    if re.search(r"\b(english|communication|learn|practice|improve|accent|fluency|vocabulary|grammar|college|school|exam)\b", text_lower):
        return "Consistent vocal practice is the fastest way to build confidence and natural fluency. What specific area of speaking do you want to master next?"

    # 7. Questions directed to AI
    if text_lower.endswith('?') or re.search(r"\b(what\s+do\s+you\s+think|can\s+you\s+tell|how\s+can\s+i|what\s+is\s+your|do\s+you\s+know)\b", text_lower):
        return "That's an insightful question! Focusing on clear articulation, steady pacing, and structured sentences makes any conversation engaging. What is your perspective on it?"

    # 8. Dynamic thoughtful reply based on extracted keywords
    meaningful_words = [w for w in re.findall(r'\b[a-z]{4,}\b', text_lower) if w not in {'this', 'that', 'with', 'from', 'have', 'were', 'they', 'your', 'about', 'some', 'what', 'when', 'where', 'there', 'here', 'also'}]
    key_topic = f"'{meaningful_words[0]}'" if meaningful_words else "your thought"
    return f"You raised a great point regarding {key_topic}. Expressing your viewpoint with clear pacing builds strong conversational fluency. How do you see that developing further?"


@app.route('/api/live_voice_analyze', methods=['POST'])
def live_voice_analyze():
    """API endpoint to process real-time voice streaming chunks with accurate mistake identification and contextual audio feedback."""
    data = request.json or {}
    text = data.get('text', '')
    lang = data.get('lang') or session.get('ai_voice', 'en')
    voice_type = session.get('ai_voice_type', 'female')
    
    if not text.strip():
        return jsonify({
            "status": "error",
            "reply": "I couldn't hear any speech. Please try speaking into your microphone again.",
            "spoken_text": "I couldn't hear any speech. Please try speaking into your microphone again.",
            "audio_url": None,
            "has_mistakes": False,
            "mistakes_count": 0,
            "mistakes": [],
            "analysis": {}
        })
        
    result = analyze_realtime_voice_input(text, lang_code=lang, voice_type=voice_type)
    
    # Auto-save voice training practice session in SQLite DB
    try:
        voice_sess_id = session.get('current_voice_session_id')
        words_count = len(text.split())
        fluency_val = int(result.get('analysis', {}).get('fluency', 85))
        
        if not voice_sess_id or not TrainingSession.query.filter_by(session_id=voice_sess_id).first():
            voice_sess_id = f"VOICE-{uuid.uuid4().hex[:6].upper()}"
            session['current_voice_session_id'] = voice_sess_id
            new_sess = TrainingSession(
                session_id=voice_sess_id,
                module_type="Voice Trainer",
                mode="Voice",
                input_language="Tamil" if lang == 'ta' else "Hindi" if lang == 'hi' else "English",
                reply_language="Tamil" if lang == 'ta' else "Hindi" if lang == 'hi' else "English",
                overall_score=fluency_val,
                fluency_score=fluency_val,
                grammar_score=85 if not result.get('has_mistakes') else 75,
                vocabulary_score=85,
                total_words=words_count,
                total_exchanges=1,
                duration_mins=2,
                strengths="Real-time speech articulation and continuous vocalization.",
                weaknesses="Speech pauses and lexical precision." if result.get('has_mistakes') else "Maintain optimal speaking rate.",
                recommendations="Continue active daily voice trainer exercises.",
                transcript_summary=f"Voice practice: {text[:60]}",
                created_at=datetime.utcnow()
            )
            db.session.add(new_sess)
        else:
            existing = TrainingSession.query.filter_by(session_id=voice_sess_id).first()
            existing.total_words += words_count
            existing.total_exchanges += 1
            existing.duration_mins = max(1, round(existing.total_exchanges * 1.5))
            existing.overall_score = round((existing.overall_score + fluency_val) / 2)
            existing.fluency_score = round((existing.fluency_score + fluency_val) / 2)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Error saving voice trainer session: {e}")
        
    return jsonify(result)

# -------------------------------------------------------------
# Routing: Reports and History
# -------------------------------------------------------------
@app.route('/reports')
def reports():
    """View and download generated PDF reports with live data from database."""
    sessions = TrainingSession.query.order_by(TrainingSession.created_at.desc()).all()
    comm_scores = [s.overall_score for s in sessions if s.module_type == 'Communication']
    avg_comm_score = round(sum(comm_scores)/len(comm_scores)) if comm_scores else 0
    return render_template('reports.html', sessions=sessions, avg_comm_score=avg_comm_score)

@app.route('/history')
def history():
    """View session history, audio playbacks, and analytics."""
    sessions = TrainingSession.query.order_by(TrainingSession.created_at.desc()).all()
    return render_template('history.html', sessions=sessions)

# -------------------------------------------------------------
# API: Data Management and Permanent Data Clearing
# -------------------------------------------------------------
@app.route('/api/clear_data', methods=['POST', 'DELETE'])
@app.route('/api/sessions/clear', methods=['POST', 'DELETE'])
def clear_all_data():
    """Permanently delete all training sessions from database and reset session buffers."""
    try:
        num_deleted = db.session.query(TrainingSession).delete()
        db.session.commit()
        session.pop('comm_history', None)
        session.pop('interview_state', None)
        return jsonify({
            "status": "success",
            "message": "All reports and session history permanently cleared.",
            "deleted_count": num_deleted
        })
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Data clearing error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/sessions/<string:session_id>', methods=['DELETE', 'POST'])
def delete_single_session(session_id):
    """Permanently delete a single session by session ID."""
    try:
        sess = TrainingSession.query.filter_by(session_id=session_id).first()
        if sess:
            db.session.delete(sess)
            db.session.commit()
            return jsonify({"status": "success", "message": f"Session {session_id} deleted."})
        return jsonify({"status": "error", "message": "Session not found."}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# -------------------------------------------------------------
# API: Customization and Settings
# -------------------------------------------------------------
@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update user preferences for input/output modes, voice, and gender."""
    # Handle email notifications toggle
    email_notifications = request.form.get('email_notifications') == 'on'
    session['email_notifications'] = email_notifications

    # Handle dark mode toggle from the settings modal
    dark_mode = request.form.get('dark_mode') == 'on'
    session['dark_mode'] = dark_mode
    
    # Handle AI Voice selection (restricted to Tamil or English)
    ai_voice = request.form.get('ai_voice')
    if ai_voice in ['ta', 'en']:
        session['ai_voice'] = ai_voice
    elif ai_voice is not None:
        session['ai_voice'] = 'en'
        
    # Handle AI Voice Type / Gender selection (restricted to Male or Female)
    ai_voice_type = request.form.get('ai_voice_type')
    if ai_voice_type in ['male', 'female']:
        session['ai_voice_type'] = ai_voice_type
    elif ai_voice_type == 'adult_male':
        session['ai_voice_type'] = 'male'
    elif ai_voice_type == 'adult_female':
        session['ai_voice_type'] = 'female'
    
    # Redirect back to the page the user was on
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/api/tts', methods=['POST'])
def generate_tts():
    """Generate TTS audio file and return its URL."""
    try:
        data = request.json or {}
        text = data.get('text', '')
        lang_code = data.get('lang') or session.get('ai_voice', 'en')
        voice_type = data.get('voice_type') or session.get('ai_voice_type', 'female')
        
        if not text:
            return jsonify({"status": "error", "message": "No text provided"}), 400
            
        base_lang = lang_code.split('-')[0] if '-' in lang_code else lang_code
        if base_lang.startswith('lang:'): 
            base_lang = base_lang.split(':')[1]
            
        # Normalize gender to 'male' or 'female'
        gender = 'male' if voice_type in ['male', 'adult_male'] else 'female'
            
        voice_map = {
            'en': {
                'female': 'en-US-AriaNeural',
                'male': 'en-US-GuyNeural'
            },
            'ta': {
                'female': 'ta-IN-PallaviNeural',
                'male': 'ta-IN-ValluvarNeural'
            },
            'hi': {
                'female': 'hi-IN-SwaraNeural',
                'male': 'hi-IN-MadhurNeural'
            },
            'ur': {
                'female': 'ur-PK-UzmaNeural',
                'male': 'ur-PK-AsadNeural'
            },
            'te': {
                'female': 'te-IN-ShrutiNeural',
                'male': 'te-IN-MohanNeural'
            },
            'ml': {
                'female': 'ml-IN-SobhanaNeural',
                'male': 'ml-IN-MidhunNeural'
            },
            'kn': {
                'female': 'kn-IN-SapnaNeural',
                'male': 'kn-IN-GaganNeural'
            },
            'bn': {
                'female': 'bn-IN-TanishaaNeural',
                'male': 'bn-IN-BashkarNeural'
            },
            'mr': {
                'female': 'mr-IN-AarohiNeural',
                'male': 'mr-IN-ManoharNeural'
            },
            'gu': {
                'female': 'gu-IN-DhwaniNeural',
                'male': 'gu-IN-NiranjanNeural'
            },
            'pa': {
                'female': 'pa-IN-OjasNeural',
                'male': 'pa-IN-OjasNeural'
            },
            'fr': {
                'female': 'fr-FR-DeniseNeural',
                'male': 'fr-FR-HenriNeural'
            }
        }
        
        lang_voices = voice_map.get(base_lang, voice_map['en'])
        if isinstance(lang_voices, dict):
            voice = lang_voices.get(gender, lang_voices.get('female'))
        else:
            voice = lang_voices
            
        filename = f"tts_{uuid.uuid4().hex}.mp3"
        filepath = os.path.join(app.config['AUDIO_FOLDER'], filename)
        
        async def run_edge_tts():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(filepath)
            
        asyncio.run(run_edge_tts())
         
        audio_url = url_for('static', filename=f"audio/{filename}")
        return jsonify({"status": "success", "audio_url": audio_url})
    except Exception as e:
        app.logger.error(f"TTS Error: {str(e)}")
        return jsonify({"status": "error", "message": "Failed to generate audio.", "details": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
