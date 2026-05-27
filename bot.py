import os, random, json, pytz
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN     = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ── FILE STORAGE ─────────────────────────────────────────
DATA_FILE = "/app/coresix_users.json"

def save_users():
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(users, f, default=str)
    except Exception as e:
        print(f"Save error: {e}")

def load_users():
    global users
    try:
        with open(DATA_FILE, 'r') as f:
            loaded = json.load(f)
            users = {int(k): v for k, v in loaded.items()}
            print(f"Loaded {len(users)} users from disk")
    except FileNotFoundError:
        print("No data file — starting fresh")
        # ── SMART QUESTIONNAIRE ─────────────────────────────────
# Replaces both assessment and health profile
# Each answer maps to a pillar score + rich profile data

QUESTIONNAIRE = [
    {
        "id": "fuel",
        "pillar": "fuel",
        "question": "How would you describe your eating habits?",
        "emoji": "⚡",
        "answers": [
            {"text": "I eat whatever, whenever — not much thought goes into it", "score": 1, "profile": "poor nutrition habits, likely high processed food intake"},
            {"text": "Pretty decent but inconsistent — good days and bad days", "score": 2, "profile": "moderate nutrition, inconsistent habits"},
            {"text": "I eat well most of the time — mostly whole foods", "score": 3, "profile": "good nutrition habits, some room for improvement"},
            {"text": "Very intentional — I track, plan and prioritise nutrition", "score": 4, "profile": "strong nutrition habits, high nutritional awareness"},
        ]
    },
    {
        "id": "move",
        "pillar": "move",
        "question": "How active are you on a typical week?",
        "emoji": "💪",
        "answers": [
            {"text": "Mostly sedentary — I sit most of the day", "score": 1, "profile": "sedentary lifestyle, needs movement foundation"},
            {"text": "Light activity — occasional walks or casual exercise", "score": 2, "profile": "lightly active, building exercise habit"},
            {"text": "Moderately active — I exercise 2-3 times a week", "score": 3, "profile": "moderately active, consistent but room to grow"},
            {"text": "Very active — I train regularly and hit my step goals", "score": 4, "profile": "highly active, performance-focused"},
        ]
    },
    {
        "id": "rest",
        "pillar": "rest",
        "question": "How well do you sleep and recover?",
        "emoji": "😴",
        "answers": [
            {"text": "Poorly — I rarely get enough sleep and feel tired daily", "score": 1, "profile": "poor sleep quality, chronic fatigue likely"},
            {"text": "Inconsistent — some good nights, many bad ones", "score": 2, "profile": "inconsistent sleep, no solid sleep routine"},
            {"text": "Fairly well — I usually get 6-7 hours most nights", "score": 3, "profile": "decent sleep, small improvements needed"},
            {"text": "Really well — 7-8 hours, consistent schedule, wake refreshed", "score": 4, "profile": "good sleep hygiene, optimised recovery"},
        ]
    },
    {
        "id": "calm",
        "pillar": "calm",
        "question": "How do you handle stress and your mental state?",
        "emoji": "🧘",
        "answers": [
            {"text": "I feel overwhelmed often — stress controls me", "score": 1, "profile": "high chronic stress, needs foundational calm practices"},
            {"text": "I manage but it takes effort — some anxiety day to day", "score": 2, "profile": "moderate stress, developing coping strategies"},
            {"text": "Pretty balanced — I have tools to manage stress most of the time", "score": 3, "profile": "good stress management, some refinement needed"},
            {"text": "Very calm and grounded — I have strong mindfulness practices", "score": 4, "profile": "strong mental resilience, mindfulness practitioner"},
        ]
    },
    {
        "id": "connect",
        "pillar": "connect",
        "question": "How would you describe your relationships and social life?",
        "emoji": "🤝",
        "answers": [
            {"text": "Isolated — I feel disconnected from people around me", "score": 1, "profile": "socially isolated, needs connection foundation"},
            {"text": "Okay but surface level — I want deeper connections", "score": 2, "profile": "superficial connections, craving depth"},
            {"text": "Good relationships — I have people I can rely on", "score": 3, "profile": "solid social foundation, can deepen further"},
            {"text": "Thriving — rich meaningful relationships and strong community", "score": 4, "profile": "strong social network, community builder"},
        ]
    },
    {
        "id": "focus",
        "pillar": "focus",
        "question": "How focused and purposeful do you feel in daily life?",
        "emoji": "🎯",
        "answers": [
            {"text": "Scattered — I feel lost, distracted and without clear direction", "score": 1, "profile": "low focus and purpose, needs clarity and structure"},
            {"text": "Somewhat focused — I have goals but struggle to stay on track", "score": 2, "profile": "moderate focus, procrastination and distraction challenges"},
            {"text": "Pretty focused — I know my priorities and work toward them", "score": 3, "profile": "good focus habits, can optimise further"},
            {"text": "Laser focused — clear purpose, deep work, consistent execution", "score": 4, "profile": "high performer, strong focus and purpose clarity"},
        ]
    },
    {
        "id": "age",
        "pillar": None,
        "question": "How old are you?",
        "emoji": "🎂",
        "answers": [
            {"text": "Under 25", "score": None, "profile": "under 25, building foundations"},
            {"text": "25-35", "score": None, "profile": "25-35, peak building years"},
            {"text": "36-50", "score": None, "profile": "36-50, optimisation phase"},
            {"text": "Over 50", "score": None, "profile": "over 50, longevity focus"},
        ]
    },
    {
        "id": "sex",
        "pillar": None,
        "question": "What is your biological sex?",
        "emoji": "👤",
        "answers": [
            {"text": "Male", "score": None, "profile": "male"},
            {"text": "Female", "score": None, "profile": "female"},
            {"text": "Prefer not to say", "score": None, "profile": "unspecified"},
        ]
    },
    {
        "id": "conditions",
        "pillar": None,
        "question": "Any health conditions I should know about?",
        "emoji": "🏥",
        "answers": [
            {"text": "None — I am in good health", "score": None, "profile": "no conditions"},
            {"text": "Diabetes or blood sugar issues", "score": None, "profile": "diabetes/blood sugar"},
            {"text": "Heart condition or hypertension", "score": None, "profile": "cardiovascular condition"},
            {"text": "Anxiety, depression or mental health", "score": None, "profile": "mental health condition"},
            {"text": "Joint pain, arthritis or mobility issues", "score": None, "profile": "mobility/joint issues"},
            {"text": "Other — I will mention it in chat", "score": None, "profile": "other condition"},
        ]
    },
    {
        "id": "goal",
        "pillar": None,
        "question": "What is your biggest goal right now?",
        "emoji": "🏆",
        "answers": [
            {"text": "Lose weight and improve my body", "score": None, "profile": "weight loss and body composition"},
            {"text": "Reduce stress and feel more calm", "score": None, "profile": "stress reduction and mental wellness"},
            {"text": "Build better daily routines and discipline", "score": None, "profile": "habit building and routine"},
            {"text": "Improve energy and feel better every day", "score": None, "profile": "energy and vitality"},
            {"text": "Perform better at work or sport", "score": None, "profile": "performance optimisation"},
            {"text": "Live a longer healthier life", "score": None, "profile": "longevity and preventive health"},
        ]
    },
]

def get_q_keyboard(q_data):
    """Build keyboard for a questionnaire question."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(a["text"][:60], callback_data=f"q_{q_data['id']}_{i}")]
        for i, a in enumerate(q_data["answers"])
    ])

def next_question_idx(current_id):
    """Get index of next question."""
    ids = [q["id"] for q in QUESTIONNAIRE]
    if current_id in ids:
        idx = ids.index(current_id)
        if idx + 1 < len(QUESTIONNAIRE):
            return idx + 1
    return None


QUESTIONNAIRE = [
    {
        "id": "fuel",
        "pillar": "fuel",
        "question": "How would you describe your eating habits?",
        "emoji": "⚡",
        "answers": [
            {"text": "I eat whatever, whenever — not much thought goes into it", "score": 1, "profile": "poor nutrition habits, likely high processed food intake"},
            {"text": "Pretty decent but inconsistent — good days and bad days", "score": 2, "profile": "moderate nutrition, inconsistent habits"},
            {"text": "I eat well most of the time — mostly whole foods", "score": 3, "profile": "good nutrition habits, some room for improvement"},
            {"text": "Very intentional — I track, plan and prioritise nutrition", "score": 4, "profile": "strong nutrition habits, high nutritional awareness"},
        ]
    },
    {
        "id": "move",
        "pillar": "move",
        "question": "How active are you on a typical week?",
        "emoji": "💪",
        "answers": [
            {"text": "Mostly sedentary — I sit most of the day", "score": 1, "profile": "sedentary lifestyle, needs movement foundation"},
            {"text": "Light activity — occasional walks or casual exercise", "score": 2, "profile": "lightly active, building exercise habit"},
            {"text": "Moderately active — I exercise 2-3 times a week", "score": 3, "profile": "moderately active, consistent but room to grow"},
            {"text": "Very active — I train regularly and hit my step goals", "score": 4, "profile": "highly active, performance-focused"},
        ]
    },
    {
        "id": "rest",
        "pillar": "rest",
        "question": "How well do you sleep and recover?",
        "emoji": "😴",
        "answers": [
            {"text": "Poorly — I rarely get enough sleep and feel tired daily", "score": 1, "profile": "poor sleep quality, chronic fatigue likely"},
            {"text": "Inconsistent — some good nights, many bad ones", "score": 2, "profile": "inconsistent sleep, no solid sleep routine"},
            {"text": "Fairly well — I usually get 6-7 hours most nights", "score": 3, "profile": "decent sleep, small improvements needed"},
            {"text": "Really well — 7-8 hours, consistent schedule, wake refreshed", "score": 4, "profile": "good sleep hygiene, optimised recovery"},
        ]
    },
    {
        "id": "calm",
        "pillar": "calm",
        "question": "How do you handle stress and your mental state?",
        "emoji": "🧘",
        "answers": [
            {"text": "I feel overwhelmed often — stress controls me", "score": 1, "profile": "high chronic stress, needs foundational calm practices"},
            {"text": "I manage but it takes effort — some anxiety day to day", "score": 2, "profile": "moderate stress, developing coping strategies"},
            {"text": "Pretty balanced — I have tools to manage stress most of the time", "score": 3, "profile": "good stress management, some refinement needed"},
            {"text": "Very calm and grounded — I have strong mindfulness practices", "score": 4, "profile": "strong mental resilience, mindfulness practitioner"},
        ]
    },
    {
        "id": "connect",
        "pillar": "connect",
        "question": "How would you describe your relationships and social life?",
        "emoji": "🤝",
        "answers": [
            {"text": "Isolated — I feel disconnected from people around me", "score": 1, "profile": "socially isolated, needs connection foundation"},
            {"text": "Okay but surface level — I want deeper connections", "score": 2, "profile": "superficial connections, craving depth"},
            {"text": "Good relationships — I have people I can rely on", "score": 3, "profile": "solid social foundation, can deepen further"},
            {"text": "Thriving — rich meaningful relationships and strong community", "score": 4, "profile": "strong social network, community builder"},
        ]
    },
    {
        "id": "focus",
        "pillar": "focus",
        "question": "How focused and purposeful do you feel in daily life?",
        "emoji": "🎯",
        "answers": [
            {"text": "Scattered — I feel lost, distracted and without clear direction", "score": 1, "profile": "low focus and purpose, needs clarity and structure"},
            {"text": "Somewhat focused — I have goals but struggle to stay on track", "score": 2, "profile": "moderate focus, procrastination and distraction challenges"},
            {"text": "Pretty focused — I know my priorities and work toward them", "score": 3, "profile": "good focus habits, can optimise further"},
            {"text": "Laser focused — clear purpose, deep work, consistent execution", "score": 4, "profile": "high performer, strong focus and purpose clarity"},
        ]
    },
    {
        "id": "age",
        "pillar": None,
        "question": "How old are you?",
        "emoji": "🎂",
        "answers": [
            {"text": "Under 25", "score": None, "profile": "under 25, building foundations"},
            {"text": "25-35", "score": None, "profile": "25-35, peak building years"},
            {"text": "36-50", "score": None, "profile": "36-50, optimisation phase"},
            {"text": "Over 50", "score": None, "profile": "over 50, longevity focus"},
        ]
    },
    {
        "id": "sex",
        "pillar": None,
        "question": "What is your biological sex?",
        "emoji": "👤",
        "answers": [
            {"text": "Male", "score": None, "profile": "male"},
            {"text": "Female", "score": None, "profile": "female"},
            {"text": "Prefer not to say", "score": None, "profile": "unspecified"},
        ]
    },
    {
        "id": "conditions",
        "pillar": None,
        "question": "Any health conditions I should know about?",
        "emoji": "🏥",
        "answers": [
            {"text": "None — I am in good health", "score": None, "profile": "no conditions"},
            {"text": "Diabetes or blood sugar issues", "score": None, "profile": "diabetes/blood sugar"},
            {"text": "Heart condition or hypertension", "score": None, "profile": "cardiovascular condition"},
            {"text": "Anxiety, depression or mental health", "score": None, "profile": "mental health condition"},
            {"text": "Joint pain, arthritis or mobility issues", "score": None, "profile": "mobility/joint issues"},
            {"text": "Other — I will mention it in chat", "score": None, "profile": "other condition"},
        ]
    },
    {
        "id": "goal",
        "pillar": None,
        "question": "What is your biggest goal right now?",
        "emoji": "🏆",
        "answers": [
            {"text": "Lose weight and improve my body", "score": None, "profile": "weight loss and body composition"},
            {"text": "Reduce stress and feel more calm", "score": None, "profile": "stress reduction and mental wellness"},
            {"text": "Build better daily routines and discipline", "score": None, "profile": "habit building and routine"},
            {"text": "Improve energy and feel better every day", "score": None, "profile": "energy and vitality"},
            {"text": "Perform better at work or sport", "score": None, "profile": "performance optimisation"},
            {"text": "Live a longer healthier life", "score": None, "profile": "longevity and preventive health"},
        ]
    },
]

def get_q_keyboard(q_data):
    """Build keyboard for a questionnaire question."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(a["text"][:60], callback_data=f"q_{q_data['id']}_{i}")]
        for i, a in enumerate(q_data["answers"])
    ])

def next_question_idx(current_id):
    """Get index of next question."""
    ids = [q["id"] for q in QUESTIONNAIRE]
    if current_id in ids:
        idx = ids.index(current_id)
        if idx + 1 < len(QUESTIONNAIRE):
            return idx + 1
    return None

users = {}

# ── PILLARS ──────────────────────────────────────────────
PILLARS = {
    "fuel":    {"name":"Fuel",    "emoji":"⚡", "desc":"Nutrition"},
    "move":    {"name":"Move",    "emoji":"💪", "desc":"Movement"},
    "rest":    {"name":"Rest",    "emoji":"😴", "desc":"Sleep & Recovery"},
    "calm":    {"name":"Calm",    "emoji":"🧘", "desc":"Stress Management"},
    "connect": {"name":"Connect", "emoji":"🤝", "desc":"Social Connection"},
    "focus":   {"name":"Focus",   "emoji":"🎯", "desc":"Purpose & Mindset"},
}
PIDS = list(PILLARS.keys())

# ── HABIT LADDER ─────────────────────────────────────────
# 5 rungs per pillar — user masters each before unlocking next
LADDER = {
    "fuel": [
        {"habit": "Drink a full glass of water before your first coffee", "desc": "Anchor to your morning routine. Takes 30 seconds."},
        {"habit": "Eat breakfast sitting down with no phone or screens", "desc": "One mindful meal a day changes your relationship with food."},
        {"habit": "Add a source of protein to every meal today", "desc": "Eggs, nuts, yogurt, chicken — any protein counts."},
        {"habit": "Plan tomorrow's meals before you go to bed tonight", "desc": "5 minutes of planning saves hours of bad decisions."},
        {"habit": "Eat whole foods for every meal today — nothing ultra-processed", "desc": "This is Fuel mastery. Your body will thank you."},
    ],
    "move": [
        {"habit": "Do 5 push-ups before stepping into the shower", "desc": "Anchor to your shower routine. Always happens."},
        {"habit": "Take a 10-minute walk outside after lunch", "desc": "Movement after eating improves energy and digestion."},
        {"habit": "Complete a 20-minute workout — any type counts", "desc": "Three times this week. Build the pattern."},
        {"habit": "Hit 7000 steps today — track it on your phone", "desc": "Daily movement is more important than occasional exercise."},
        {"habit": "Complete your planned training session — no shortcuts", "desc": "This is Move mastery. You show up every time."},
    ],
    "rest": [
        {"habit": "Make your bed within 5 minutes of waking up", "desc": "First win of the day. Sets the tone for everything."},
        {"habit": "Put your phone in another room 15 minutes before sleep", "desc": "The single biggest sleep quality improvement you can make."},
        {"habit": "Go to bed at the same time as last night", "desc": "Consistency beats duration. Same time every night."},
        {"habit": "Get 10 minutes of natural light within 30 minutes of waking", "desc": "Sets your circadian rhythm for the whole day."},
        {"habit": "Complete a full wind-down routine — no screens, dim lights, same steps every night", "desc": "This is Rest mastery. Sleep is your superpower."},
    ],
    "calm": [
        {"habit": "Take 3 slow deep breaths before opening any social app", "desc": "Creates a pause between stimulus and response."},
        {"habit": "Write one thing you are grateful for before checking your phone", "desc": "Trains your brain to scan for good before bad."},
        {"habit": "Sit in silence for 5 minutes with your morning drink", "desc": "No inputs. Just you and your thoughts."},
        {"habit": "Do a 10-minute guided meditation today", "desc": "Use any app or YouTube. Consistency matters more than perfection."},
        {"habit": "Complete a full mindfulness practice — meditation, journaling, and one intentional breath break", "desc": "This is Calm mastery. You own your nervous system."},
    ],
    "connect": [
        {"habit": "Send one genuine message to someone you care about", "desc": "Not a reply — an initiation. You reach out first."},
        {"habit": "Give one specific genuine compliment to someone today", "desc": "Specific beats generic. Name what you actually appreciate."},
        {"habit": "Have one conversation today with your phone face-down", "desc": "Full presence is the rarest gift you can give."},
        {"habit": "Call instead of texting one person today", "desc": "Voice builds connection that text never can."},
        {"habit": "Plan and commit to one meaningful in-person connection this week", "desc": "This is Connect mastery. Relationships are your wealth."},
    ],
    "focus": [
        {"habit": "Write your single most important task before opening email", "desc": "Name your MIT — Most Important Task — before the noise starts."},
        {"habit": "Set a 25-minute timer and work on one thing only", "desc": "One Pomodoro. No switching. No checking."},
        {"habit": "Complete your three most important tasks before any reactive work", "desc": "Lead with creation, not response."},
        {"habit": "Block 90 minutes of deep work with no interruptions", "desc": "Your best work happens in uninterrupted flow."},
        {"habit": "Finish the day with a full shutdown ritual — clear inbox, write tomorrow's plan", "desc": "This is Focus mastery. Your time belongs to you."},
    ],
}

SLOTS = {
    "morning":   {"label":"Morning",   "default":"07:00"},
    "midday":    {"label":"Midday",    "default":"12:00"},
    "afternoon": {"label":"Afternoon", "default":"16:00"},
    "night":     {"label":"Night",     "default":"21:00"},
}

TIMEZONES = {
    "New York":      "America/New_York",
    "Chicago":       "America/Chicago",
    "Los Angeles":   "America/Los_Angeles",
    "Toronto":       "America/Toronto",
    "Sao Paulo":     "America/Sao_Paulo",
    "London":        "Europe/London",
    "Paris":         "Europe/Paris",
    "Berlin":        "Europe/Berlin",
    "Madrid":        "Europe/Madrid",
    "Amsterdam":     "Europe/Amsterdam",
    "Dubai":         "Asia/Dubai",
    "Riyadh":        "Asia/Riyadh",
    "Cairo":         "Africa/Cairo",
    "Istanbul":      "Europe/Istanbul",
    "Nairobi":       "Africa/Nairobi",
    "Mumbai":        "Asia/Kolkata",
    "Singapore":     "Asia/Singapore",
    "Hong Kong":     "Asia/Hong_Kong",
    "Tokyo":         "Asia/Tokyo",
    "Sydney":        "Australia/Sydney",
}

TZ_REGIONS = {
    "Americas":    ["New York","Chicago","Los Angeles","Toronto","Sao Paulo"],
    "Europe":      ["London","Paris","Berlin","Madrid","Amsterdam"],
    "Middle East": ["Dubai","Riyadh","Cairo","Istanbul","Nairobi"],
    "Asia":        ["Mumbai","Singapore","Hong Kong","Tokyo","Sydney"],
}

# ── SMART QUESTIONNAIRE ─────────────────────────────────
# Replaces both assessment and health profile
# Each answer maps to a pillar score + rich profile data

QUESTIONNAIRE = [
    {
        "id": "fuel",
        "pillar": "fuel",
        "question": "How would you describe your eating habits?",
        "emoji": "⚡",
        "answers": [
            {"text": "I eat whatever, whenever — not much thought goes into it", "score": 1, "profile": "poor nutrition habits, likely high processed food intake"},
            {"text": "Pretty decent but inconsistent — good days and bad days", "score": 2, "profile": "moderate nutrition, inconsistent habits"},
            {"text": "I eat well most of the time — mostly whole foods", "score": 3, "profile": "good nutrition habits, some room for improvement"},
            {"text": "Very intentional — I track, plan and prioritise nutrition", "score": 4, "profile": "strong nutrition habits, high nutritional awareness"},
        ]
    },
    {
        "id": "move",
        "pillar": "move",
        "question": "How active are you on a typical week?",
        "emoji": "💪",
        "answers": [
            {"text": "Mostly sedentary — I sit most of the day", "score": 1, "profile": "sedentary lifestyle, needs movement foundation"},
            {"text": "Light activity — occasional walks or casual exercise", "score": 2, "profile": "lightly active, building exercise habit"},
            {"text": "Moderately active — I exercise 2-3 times a week", "score": 3, "profile": "moderately active, consistent but room to grow"},
            {"text": "Very active — I train regularly and hit my step goals", "score": 4, "profile": "highly active, performance-focused"},
        ]
    },
    {
        "id": "rest",
        "pillar": "rest",
        "question": "How well do you sleep and recover?",
        "emoji": "😴",
        "answers": [
            {"text": "Poorly — I rarely get enough sleep and feel tired daily", "score": 1, "profile": "poor sleep quality, chronic fatigue likely"},
            {"text": "Inconsistent — some good nights, many bad ones", "score": 2, "profile": "inconsistent sleep, no solid sleep routine"},
            {"text": "Fairly well — I usually get 6-7 hours most nights", "score": 3, "profile": "decent sleep, small improvements needed"},
            {"text": "Really well — 7-8 hours, consistent schedule, wake refreshed", "score": 4, "profile": "good sleep hygiene, optimised recovery"},
        ]
    },
    {
        "id": "calm",
        "pillar": "calm",
        "question": "How do you handle stress and your mental state?",
        "emoji": "🧘",
        "answers": [
            {"text": "I feel overwhelmed often — stress controls me", "score": 1, "profile": "high chronic stress, needs foundational calm practices"},
            {"text": "I manage but it takes effort — some anxiety day to day", "score": 2, "profile": "moderate stress, developing coping strategies"},
            {"text": "Pretty balanced — I have tools to manage stress most of the time", "score": 3, "profile": "good stress management, some refinement needed"},
            {"text": "Very calm and grounded — I have strong mindfulness practices", "score": 4, "profile": "strong mental resilience, mindfulness practitioner"},
        ]
    },
    {
        "id": "connect",
        "pillar": "connect",
        "question": "How would you describe your relationships and social life?",
        "emoji": "🤝",
        "answers": [
            {"text": "Isolated — I feel disconnected from people around me", "score": 1, "profile": "socially isolated, needs connection foundation"},
            {"text": "Okay but surface level — I want deeper connections", "score": 2, "profile": "superficial connections, craving depth"},
            {"text": "Good relationships — I have people I can rely on", "score": 3, "profile": "solid social foundation, can deepen further"},
            {"text": "Thriving — rich meaningful relationships and strong community", "score": 4, "profile": "strong social network, community builder"},
        ]
    },
    {
        "id": "focus",
        "pillar": "focus",
        "question": "How focused and purposeful do you feel in daily life?",
        "emoji": "🎯",
        "answers": [
            {"text": "Scattered — I feel lost, distracted and without clear direction", "score": 1, "profile": "low focus and purpose, needs clarity and structure"},
            {"text": "Somewhat focused — I have goals but struggle to stay on track", "score": 2, "profile": "moderate focus, procrastination and distraction challenges"},
            {"text": "Pretty focused — I know my priorities and work toward them", "score": 3, "profile": "good focus habits, can optimise further"},
            {"text": "Laser focused — clear purpose, deep work, consistent execution", "score": 4, "profile": "high performer, strong focus and purpose clarity"},
        ]
    },
    {
        "id": "age",
        "pillar": None,
        "question": "How old are you?",
        "emoji": "🎂",
        "answers": [
            {"text": "Under 25", "score": None, "profile": "under 25, building foundations"},
            {"text": "25-35", "score": None, "profile": "25-35, peak building years"},
            {"text": "36-50", "score": None, "profile": "36-50, optimisation phase"},
            {"text": "Over 50", "score": None, "profile": "over 50, longevity focus"},
        ]
    },
    {
        "id": "sex",
        "pillar": None,
        "question": "What is your biological sex?",
        "emoji": "👤",
        "answers": [
            {"text": "Male", "score": None, "profile": "male"},
            {"text": "Female", "score": None, "profile": "female"},
            {"text": "Prefer not to say", "score": None, "profile": "unspecified"},
        ]
    },
    {
        "id": "conditions",
        "pillar": None,
        "question": "Any health conditions I should know about?",
        "emoji": "🏥",
        "answers": [
            {"text": "None — I am in good health", "score": None, "profile": "no conditions"},
            {"text": "Diabetes or blood sugar issues", "score": None, "profile": "diabetes/blood sugar"},
            {"text": "Heart condition or hypertension", "score": None, "profile": "cardiovascular condition"},
            {"text": "Anxiety, depression or mental health", "score": None, "profile": "mental health condition"},
            {"text": "Joint pain, arthritis or mobility issues", "score": None, "profile": "mobility/joint issues"},
            {"text": "Other — I will mention it in chat", "score": None, "profile": "other condition"},
        ]
    },
    {
        "id": "goal",
        "pillar": None,
        "question": "What is your biggest goal right now?",
        "emoji": "🏆",
        "answers": [
            {"text": "Lose weight and improve my body", "score": None, "profile": "weight loss and body composition"},
            {"text": "Reduce stress and feel more calm", "score": None, "profile": "stress reduction and mental wellness"},
            {"text": "Build better daily routines and discipline", "score": None, "profile": "habit building and routine"},
            {"text": "Improve energy and feel better every day", "score": None, "profile": "energy and vitality"},
            {"text": "Perform better at work or sport", "score": None, "profile": "performance optimisation"},
            {"text": "Live a longer healthier life", "score": None, "profile": "longevity and preventive health"},
        ]
    },
]

def get_q_keyboard(q_data):
    """Build keyboard for a questionnaire question."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(a["text"][:60], callback_data=f"q_{q_data['id']}_{i}")]
        for i, a in enumerate(q_data["answers"])
    ])

def next_question_idx(current_id):
    """Get index of next question."""
    ids = [q["id"] for q in QUESTIONNAIRE]
    if current_id in ids:
        idx = ids.index(current_id)
        if idx + 1 < len(QUESTIONNAIRE):
            return idx + 1
    return None

users = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "name": "", "step": "welcome",
            "scores": {}, "streak": 0,
            "timezone": "UTC",
            "reminders": {"morning":"07:00","midday":"12:00","afternoon":"16:00","night":"21:00"},
            "reminders_active": False,
            "personal_goals": [], "adding_goal": False,
            "profile": {"age":None,"sex":None,"fitness":None,"conditions":[],"medications":[],"sleep_quality":None,"stress_level":None},
            "profile_step": None,
            "onboarding": None, "setting_slot": None, "q_index": 0, "q_answers": {},
            # Habit ladder progress per pillar
            "ladder": {pid: {"rung": 0, "days": 0, "last_date": None} for pid in PIDS},
            "checked_today": {},      # pid -> True if done today
            "macro_log": [],
            "weekly_history": [],
            "score_history": [],
            "mood": None, "mood_date": None,
            "last_active_date": None,
            "missed_days_alerted": False,
            "pattern_sent_week": None,
        }
    return users[uid]

def get_current_habit(user, pid):
    """Get the current habit for a pillar based on ladder progress."""
    rung = user["ladder"][pid]["rung"]
    rung = min(rung, len(LADDER[pid]) - 1)
    return LADDER[pid][rung]

def get_rung_display(user, pid):
    """Get rung display string."""
    rung = user["ladder"][pid]["rung"]
    days = user["ladder"][pid]["days"]
    total = len(LADDER[pid])
    return f"Rung {rung+1}/{total} · {days} days"

def can_unlock_next(user, pid):
    """Check if user can unlock next rung."""
    rung = user["ladder"][pid]["rung"]
    return rung < len(LADDER[pid]) - 1

def is_mastered(user, pid):
    """Check if pillar is fully mastered."""
    return user["ladder"][pid]["rung"] >= len(LADDER[pid]) - 1 and user["ladder"][pid]["days"] >= 1

# ── GROQ ─────────────────────────────────────────────────
async def groq(prompt, system, max_tokens=300):
    import httpx
    if not GROQ_API_KEY:
        return ""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={"model":"llama-3.3-70b-versatile","messages":[{"role":"system","content":system},{"role":"user","content":prompt}],"max_tokens":max_tokens,"temperature":0.9},
            headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

async def ai_msg(user, purpose):
    name = user["name"] or "champ"
    streak = user["streak"]
    prompts = {
        "morning":  f"Morning message for {name}. Streak: {streak}. 1 punchy sentence.",
        "all_done": f"{name} completed all habits today. Streak {streak}. Short celebration. Make it feel earned.",
        "start":    f"{name} just started CoreSix. One punchy welcome. Make them feel ready.",
        "mastered": f"{name} just mastered a habit after {streak} days. Celebrate this milestone. 2 sentences max.",
    }
    try:
        return await groq(prompts.get(purpose,"Keep going."), "Direct habit coach. Short punchy texts. Max 2 sentences.", max_tokens=80)
    except:
        defaults = {"morning":f"Morning {name}. Let's go.","all_done":f"All done. {streak} days straight.","start":f"Welcome {name}. One habit at a time.","mastered":f"Mastered. That habit is yours forever now, {name}."}
        return defaults.get(purpose,"Keep going.")

# ── KEYBOARDS ─────────────────────────────────────────────
def main_habit_kb(user):
    """Show today's habits with ladder info."""
    btns = []
    today = datetime.now().strftime("%Y-%m-%d")
    pids = get_active_pillars(user)
    for pid in pids:
        p = PILLARS[pid]
        done = user["checked_today"].get(pid) == today
        rung_info = get_rung_display(user, pid)
        label = f"✅ {p['emoji']} {p['name']}" if done else f"{p['emoji']} {p['name']} · {rung_info}"
        btns.append([InlineKeyboardButton(label, callback_data=f"habit_{pid}")])
    return InlineKeyboardMarkup(btns)

def get_active_pillars(user):
    """Get top 3 pillars based on scores — weakest first."""
    scores = user["scores"]
    if not scores:
        return PIDS[:3]
    return sorted(PIDS, key=lambda p: scores.get(p, 3))[:3]

def habit_detail_kb(pid, user):
    """Keyboard for a single habit detail view."""
    today = datetime.now().strftime("%Y-%m-%d")
    done = user["checked_today"].get(pid) == today
    btns = []
    if not done:
        btns.append([InlineKeyboardButton("✅ I did this today!", callback_data=f"done_{pid}")])
    if can_unlock_next(user, pid):
        btns.append([InlineKeyboardButton("🔓 I've mastered this → unlock next", callback_data=f"unlock_{pid}")])
    btns.append([InlineKeyboardButton("← Back to habits", callback_data="back_habits")])
    return InlineKeyboardMarkup(btns)

def reminders_kb(user):
    btns = [[InlineKeyboardButton(f"{SLOTS[s]['label']} - {user['reminders'].get(s,SLOTS[s]['default'])}", callback_data=f"setslot_{s}")] for s in SLOTS]
    status = "ON" if user["reminders_active"] else "OFF"
    btns.append([InlineKeyboardButton(f"Reminders: {status} - tap to toggle", callback_data="toggle_reminders")])
    btns.append([InlineKeyboardButton("Save and Activate", callback_data="save_reminders")])
    return InlineKeyboardMarkup(btns)

def score_kb(pid):
    return InlineKeyboardMarkup([[InlineKeyboardButton(str(n), callback_data=f"score_{pid}_{n}") for n in range(1,6)]])

def tz_region_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton(r, callback_data=f"tz_region_{r}")] for r in TZ_REGIONS])

def tz_city_kb(region):
    return InlineKeyboardMarkup([[InlineKeyboardButton(c, callback_data=f"tz_set_{c}")] for c in TZ_REGIONS.get(region,[])])

def goals_kb(goals):
    btns = [[InlineKeyboardButton(f"Remove: {g[:35]}", callback_data=f"rmgoal_{i}")] for i,g in enumerate(goals)]
    btns.append([InlineKeyboardButton("Add a goal", callback_data="add_goal")])
    if goals:
        btns.append([InlineKeyboardButton("Clear all", callback_data="clear_goals")])
    return InlineKeyboardMarkup(btns)

# ── COMMANDS ──────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    user["name"] = update.effective_user.first_name or "Hero"
    user["step"] = "onboarding"
    user["onboarding"] = "questionnaire"
    user["q_index"] = 0
    user["q_answers"] = {}
    q = QUESTIONNAIRE[0]
    await update.message.reply_text(
        f"CoreSix - 6 pillars. One habit. Master it. Level up.\n\n"
        f"Welcome {user['name']}! Let me learn about you first.\n\n"
        f"10 quick questions - no numbers, just honest answers.\n\n"
        f"Question 1 of {len(QUESTIONNAIRE)}\n"
        f"{q['emoji']} {q['question']}",
        reply_markup=get_q_keyboard(q)
    )

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if user["step"] != "active":
        await update.message.reply_text("Send /start to set up first!")
        return
    pids = get_active_pillars(user)
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"Your habits today - Day {user['streak']+1}\n"]
    for pid in pids:
        p = PILLARS[pid]
        h = get_current_habit(user, pid)
        done = user["checked_today"].get(pid) == today
        rung = get_rung_display(user, pid)
        lines.append(f"{'✅' if done else p['emoji']} {p['name']} [{rung}]")
        if not done:
            lines.append(f"   {h['habit']}")
        lines.append("")
    lines.append("Tap a pillar to check in or level up")
    await update.message.reply_text("\n".join(lines), reply_markup=main_habit_kb(user))

async def cmd_ladder(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show full ladder progress for all pillars."""
    uid = update.effective_user.id
    user = get_user(uid)
    lines = ["Your Habit Ladder Progress\n"]
    for pid in PIDS:
        p = PILLARS[pid]
        rung = user["ladder"][pid]["rung"]
        days = user["ladder"][pid]["days"]
        total = len(LADDER[pid])
        stars = "⭐" * (rung+1) + "☆" * (total-rung-1)
        lines.append(f"{p['emoji']} {p['name']} {stars}")
        lines.append(f"   Rung {rung+1}/{total} · {days} days on this habit")
        current = LADDER[pid][min(rung, total-1)]["habit"]
        lines.append(f"   Current: {current[:50]}...")
        lines.append("")
    await update.message.reply_text("\n".join(lines))

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    scores = user["scores"]
    sc = "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {scores.get(p,'?')}/5" for p in PIDS]) if scores else "Not assessed"
    today = datetime.now().strftime("%Y-%m-%d")
    done_today = sum(1 for pid in PIDS if user["checked_today"].get(pid)==today)
    await update.message.reply_text(
        f"CoreSix - {user['name']}\n\n"
        f"Streak: {user['streak']} days\n"
        f"Done today: {done_today} habits\n\n"
        f"Scores:\n{sc}\n\n"
        f"Send /ladder to see your full progress\n"
        f"Send /habit to check in"
    )

async def cmd_assess(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    user["step"] = "assess"
    user["scores"] = {}
    p = PILLARS[PIDS[0]]
    await update.message.reply_text(
        f"Rate each pillar 1-5.\n1 = struggling - 5 = thriving\n\n{p['emoji']} {p['name']} - {p['desc']}",
        reply_markup=score_kb(PIDS[0])
    )

async def cmd_reminders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    await update.message.reply_text("Your Reminder Schedule\nTap a time to change it:", reply_markup=reminders_kb(user))

async def cmd_goals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    goals = user.get("personal_goals",[])
    text = "Your Personal Goals\n\n" + ("\n".join([f"{i+1}. {g}" for i,g in enumerate(goals)]) if goals else "No goals set yet.")
    await update.message.reply_text(text, reply_markup=goals_kb(goals))

async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    p = user.get("profile",{})
    lines = [
        "Your Health Profile\n",
        f"Age: {p.get('age') or 'Not set'}",
        f"Sex: {p.get('sex') or 'Not set'}",
        f"Fitness: {p.get('fitness') or 'Not set'}",
        f"Conditions: {', '.join(p.get('conditions',[])) or 'None'}",
        f"Medications: {', '.join(p.get('medications',[])) or 'None'}",
        f"Sleep: {p.get('sleep_quality') or 'Not set'}",
        f"Stress: {p.get('stress_level') or 'Not set'}",
    ]
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Update Profile", callback_data="profile_start")],
            [InlineKeyboardButton("Clear Profile", callback_data="profile_clear")],
        ])
    )

async def cmd_timezone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    await update.message.reply_text(
        f"Your timezone: {user.get('timezone','UTC')}\n\nChange it:",
        reply_markup=tz_region_kb()
    )

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user.get("weekly_history"):
        await update.message.reply_text("No data yet. Complete some habits first!")
        return
    h7 = user["weekly_history"][-7:]
    days = len(h7)
    total = sum(len(r.get("pillars",[])) for r in h7)
    pc = {}
    for r in h7:
        for p in r.get("pillars",[]): pc[p] = pc.get(p,0)+1
    breakdown = "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {c}x" for p,c in sorted(pc.items(),key=lambda x:-x[1])]) or "No data"
    try:
        report = await groq(
            f"Weekly CoreSix report for {user['name']}. Days: {days}/7. Habits: {total}. Top pillars: {breakdown}. Give honest punchy coaching.",
            "Direct habit coach. Weekly review. Max 4 sentences.", max_tokens=200
        )
    except:
        report = f"{days}/7 days. {total} habits done. Keep showing up."
    await update.message.reply_text(f"Weekly Report\n\n{days}/7 days - {total} habits\n\nPillar breakdown:\n{breakdown}\n\nCoach:\n{report}")

# ── CALLBACKS ─────────────────────────────────────────────
async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    data = q.data

    # ── Habit detail view ──
    if data.startswith("habit_"):
        pid = data.replace("habit_","")
        p = PILLARS[pid]
        h = get_current_habit(user, pid)
        rung = user["ladder"][pid]["rung"]
        days = user["ladder"][pid]["days"]
        total = len(LADDER[pid])
        today = datetime.now().strftime("%Y-%m-%d")
        done = user["checked_today"].get(pid) == today
        stars = "⭐" * (rung+1) + "☆" * (total-rung-1)

        text = (
            f"{p['emoji']} {p['name']} - Rung {rung+1} of {total}\n"
            f"{stars}\n\n"
            f"Your current habit:\n"
            f"{h['habit']}\n\n"
            f"Why this works:\n{h['desc']}\n\n"
            f"Days on this habit: {days}\n\n"
            f"{'✅ Done today!' if done else 'Not done yet today.'}"
        )
        if can_unlock_next(user, pid):
            text += f"\n\nReady to level up? Tap below when you feel you have truly mastered this habit."
        elif not can_unlock_next(user, pid) and rung >= total-1:
            text += f"\n\n🏆 {p['name']} MASTERED! You have reached the top."

        await q.edit_message_text(text, reply_markup=habit_detail_kb(pid, user))

    # ── Mark habit done ──
    elif data.startswith("done_"):
        pid = data.replace("done_","")
        today = datetime.now().strftime("%Y-%m-%d")
        if user["checked_today"].get(pid) == today:
            await q.answer("Already done today!")
            return
        user["checked_today"][pid] = today
        user["last_active_date"] = today
        user["missed_days_alerted"] = False

        # Update ladder days
        last = user["ladder"][pid].get("last_date")
        if last != today:
            user["ladder"][pid]["days"] += 1
            user["ladder"][pid]["last_date"] = today

        # Check if all active pillars done
        pids = get_active_pillars(user)
        all_done = all(user["checked_today"].get(p)==today for p in pids)
        if all_done:
            user["streak"] += 1
            user["weekly_history"].append({
                "date": today,
                "day_of_week": datetime.now().strftime("%A"),
                "pillars": pids,
                "streak": user["streak"],
            })
            user["weekly_history"] = user["weekly_history"][-30:]
            save_users()
            msg = await ai_msg(user, "all_done")
            await q.edit_message_text(
                f"All done today! Day {user['streak']} complete.\n\n{msg}\n\nSend /habit tomorrow to keep going.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("See My Ladder", callback_data="show_ladder")]])
            )
        else:
            save_users()
            p = PILLARS[pid]
            days = user["ladder"][pid]["days"]
            await q.edit_message_text(
                f"Done! {p['emoji']} {p['name']} checked in. Day {days} on this habit.\n\nKeep going — tap below for your other habits.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to habits", callback_data="back_habits")]])
            )

    # ── Unlock next rung ──
    elif data.startswith("unlock_"):
        pid = data.replace("unlock_","")
        p = PILLARS[pid]
        old_rung = user["ladder"][pid]["rung"]
        if not can_unlock_next(user, pid):
            await q.answer("Already at the top!")
            return
        user["ladder"][pid]["rung"] += 1
        user["ladder"][pid]["days"] = 0
        save_users()
        new_rung = user["ladder"][pid]["rung"]
        new_habit = LADDER[pid][new_rung]
        msg = await ai_msg(user, "mastered")
        await q.edit_message_text(
            f"Rung {old_rung+1} MASTERED! {p['emoji']}\n\n{msg}\n\n"
            f"Your new habit - Rung {new_rung+1}:\n\n"
            f"{new_habit['habit']}\n\n"
            f"{new_habit['desc']}\n\n"
            f"Take your time. Master this before moving on.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to habits", callback_data="back_habits")]])
        )

    # ── Back to habits ──
    elif data == "back_habits":
        pids = get_active_pillars(user)
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [f"Your habits today - Day {user['streak']+1}\n"]
        for pid in pids:
            p = PILLARS[pid]
            h = get_current_habit(user, pid)
            done = user["checked_today"].get(pid) == today
            rung_info = get_rung_display(user, pid)
            lines.append(f"{'✅' if done else p['emoji']} {p['name']} [{rung_info}]")
            if not done:
                lines.append(f"   {h['habit']}")
            lines.append("")
        await q.edit_message_text("\n".join(lines), reply_markup=main_habit_kb(user))

    # ── Show ladder ──
    elif data == "show_ladder":
        lines = ["Your Habit Ladder\n"]
        for pid in PIDS:
            p = PILLARS[pid]
            rung = user["ladder"][pid]["rung"]
            days = user["ladder"][pid]["days"]
            total = len(LADDER[pid])
            stars = "⭐"*(rung+1) + "☆"*(total-rung-1)
            lines.append(f"{p['emoji']} {p['name']} {stars} - {days} days")
        await q.edit_message_text("\n".join(lines))

    # ── Questionnaire ──
    elif data.startswith("q_"):
        parts = data.split("_", 2)
        q_id = parts[1]
        a_idx = int(parts[2])
        q_data = next((q for q in QUESTIONNAIRE if q["id"]==q_id), None)
        if not q_data:
            return
        answer = q_data["answers"][a_idx]
        user["q_answers"][q_id] = {"answer": answer["text"], "profile": answer["profile"], "score": answer["score"]}

        # Apply pillar score if applicable
        if q_data["pillar"] and answer["score"]:
            user["scores"][q_data["pillar"]] = answer["score"]

        # Apply profile data
        if q_id == "age":
            user["profile"]["age"] = answer["profile"]
        elif q_id == "sex":
            user["profile"]["sex"] = answer["profile"]
        elif q_id == "conditions":
            if answer["profile"] != "no conditions":
                user["profile"]["conditions"] = [answer["profile"]]
        elif q_id == "goal":
            if answer["profile"] not in user.get("personal_goals",[]):
                user["personal_goals"] = [answer["profile"]]

        # Next question or finish
        next_idx = next_question_idx(q_id)
        if next_idx is not None:
            user["q_index"] = next_idx
            next_q = QUESTIONNAIRE[next_idx]
            total = len(QUESTIONNAIRE)
            save_users()
            await q.edit_message_text(
                f"Question {next_idx+1} of {total}\n{next_q['emoji']} {next_q['question']}",
                reply_markup=get_q_keyboard(next_q)
            )
        else:
            # All questions answered — finish setup
            user["step"] = "active"
            user["onboarding"] = None
            save_users()

            # Build summary
            ranked = sorted(PIDS, key=lambda p: user["scores"].get(p, 3))
            weakest = PILLARS[ranked[0]]
            goal = user.get("personal_goals",["building better habits"])[0]

            try:
                summary = await groq(
                    f"User {user['name']} completed their CoreSix profile. "
                    f"Pillar scores: {', '.join([f'{PILLARS[p]["name"]}:{user["scores"].get(p,"?")}' for p in PIDS])}. "
                    f"Main goal: {goal}. Age: {user['profile'].get('age')}. "
                    f"Write a 2-sentence personal welcome that references their weakest area and goal.",
                    "Warm direct habit coach. Personal welcome. Reference actual data. Max 2 sentences.",
                    max_tokens=100
                )
            except:
                summary = f"Based on your answers, {weakest['name']} is your biggest opportunity. Let's start there and build from the ground up."

            await q.edit_message_text(
                "Profile complete! Here is what I know about you:\n\n"
                "Your pillars (weakest first):\n" +
                "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {'⭐'*user['scores'].get(p,1)}" for p in ranked]) +
                f"\n\nMain goal: {goal}\n\n{summary}\n\nNow let me set up your reminders.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Set My Reminders", callback_data="show_reminders")],
                    [InlineKeyboardButton("Skip - Start Now", callback_data="get_habits_now")],
                ])
            )

    elif data == "show_reminders":
        await q.edit_message_text("Set Your Daily Reminders\nTap a time to change it:", reply_markup=reminders_kb(user))

    # ── Onboarding ──
    elif data == "onboard_skip_goals":
        user["adding_goal"] = False
        user["onboarding"] = "timezone"
        await q.edit_message_text(
            "Step 2 of 4 - Your Timezone\n\nSo your reminders arrive at the right time.\n\nWhere are you based?",
            reply_markup=tz_region_kb()
        )

    elif data.startswith("tz_region_"):
        region = data.replace("tz_region_","")
        await q.edit_message_text(f"Pick your city:", reply_markup=tz_city_kb(region))

    elif data.startswith("tz_set_"):
        city = data.replace("tz_set_","")
        tz = TIMEZONES.get(city,"UTC")
        user["timezone"] = tz
        save_users()
        if user.get("onboarding") == "timezone":
            user["onboarding"] = "reminders"
            await q.edit_message_text(
                f"Timezone set to {city}!\n\nStep 3 of 4 - Daily Reminders\n\nI will reach out 4 times a day with your habits.\nTap each time to change it.",
                reply_markup=reminders_kb(user)
            )
        else:
            await q.edit_message_text(f"Timezone updated to {city}!")

    elif data == "save_reminders":
        user["reminders_active"] = True
        schedule_reminders(ctx.application, uid)
        save_users()
        lines = "\n".join([f"{SLOTS[s]['label']}: {user['reminders'].get(s)}" for s in SLOTS])
        if user.get("onboarding") == "reminders":
            user["onboarding"] = "assess"
            await q.edit_message_text(
                f"Reminders set!\n{lines}\n\nStep 4 of 4 - Quick Assessment\n\nRate each pillar 1-5 so I know which habits to focus on first.\n1 = struggling   5 = thriving",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Start Assessment", callback_data="assess")],
                    [InlineKeyboardButton("Skip - Start Now", callback_data="onboard_done")],
                ])
            )
        else:
            profile = user.get("profile",{})
            profile_done = all([profile.get("age"), profile.get("sex")])
            await q.edit_message_text(
                f"Reminders activated!\n\n{lines}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Set Health Profile", callback_data="profile_start")] if not profile_done else [InlineKeyboardButton("Get Today's Habits", callback_data="get_habits_now")],
                    [InlineKeyboardButton("Get Today's Habits", callback_data="get_habits_now")] if not profile_done else [],
                ])
            )

    elif data == "toggle_reminders":
        user["reminders_active"] = not user["reminders_active"]
        save_users()
        await q.edit_message_text("Reminder Schedule:", reply_markup=reminders_kb(user))

    elif data.startswith("setslot_"):
        slot = data.replace("setslot_","")
        user["setting_slot"] = slot
        current = user["reminders"].get(slot, SLOTS[slot]["default"])
        await q.edit_message_text(f"Change {SLOTS[slot]['label']} reminder\n\nCurrent: {current}\n\nReply with time in HH:MM format\nExample: 08:30 or 21:00")

    # ── Assessment ──
    elif data == "assess":
        user["step"] = "assess"
        user["scores"] = {}
        p = PILLARS[PIDS[0]]
        await q.edit_message_text(
            f"Rate each pillar 1-5.\n1 = struggling - 5 = thriving\n\n{p['emoji']} {p['name']} - {p['desc']}",
            reply_markup=score_kb(PIDS[0])
        )

    elif data.startswith("score_"):
        _, pid, score = data.split("_")
        user["scores"][pid] = int(score)
        scored = list(user["scores"].keys())
        remaining = [p for p in PIDS if p not in scored]
        if remaining:
            p = PILLARS[remaining[0]]
            await q.edit_message_text(
                f"{len(scored)}/6 rated\n\n{p['emoji']} {p['name']} - {p['desc']}",
                reply_markup=score_kb(remaining[0])
            )
        else:
            user["step"] = "active"
            save_users()
            ranked = sorted(PIDS, key=lambda p: user["scores"].get(p,3))
            lines = [f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {user['scores'][p]}/5" for p in ranked]
            if user.get("onboarding"):
                user["onboarding"] = None
                await q.edit_message_text(
                    "Assessment done!\n\nYour pillars (weakest first):\n" + "\n".join(lines) +
                    "\n\nI will focus on your 3 weakest pillars first.\nEach pillar has 5 habits to master — one at a time.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Set Health Profile", callback_data="profile_start")],
                        [InlineKeyboardButton("Start My Journey!", callback_data="get_habits_now")],
                    ])
                )
            else:
                await q.edit_message_text(
                    "Assessment updated!\n\nYour pillars:\n" + "\n".join(lines) +
                    "\n\nSend /habit to get today's habits."
                )

    elif data == "onboard_done":
        user["step"] = "active"
        user["onboarding"] = None
        save_users()
        await q.edit_message_text(
            f"All set, {user['name']}!\n\nEach of your 3 focus pillars has a habit ladder with 5 rungs.\nMaster each habit at your own pace before unlocking the next.\n\nSend /habit to begin.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Get My First Habits!", callback_data="get_habits_now")]])
        )

    elif data == "get_habits_now":
        user["step"] = "active"
        user["missed_days_alerted"] = False
        pids = get_active_pillars(user)
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [f"Your habits today - Day {user['streak']+1}\n"]
        for pid in pids:
            p = PILLARS[pid]
            h = get_current_habit(user, pid)
            rung_info = get_rung_display(user, pid)
            lines.append(f"{p['emoji']} {p['name']} [Rung 1/5 - Day 1]")
            lines.append(f"   {h['habit']}")
            lines.append("")
        lines.append("Tap a pillar to check in")
        await q.edit_message_text("\n".join(lines), reply_markup=main_habit_kb(user))

    # ── Goals ──
    elif data == "add_goal":
        user["adding_goal"] = True
        await q.edit_message_text(
            "Add a Personal Goal\n\nType your goal below.\nExamples:\n- Drink more water\n- Eat more protein\n- Sleep before midnight\n- Walk 10000 steps"
        )

    elif data == "add_another_goal":
        user["adding_goal"] = True
        goals = user.get("personal_goals",[])
        await q.edit_message_text(
            f"You have {len(goals)} goal(s):\n" + "\n".join([f"- {g}" for g in goals]) + "\n\nType your next goal:"
        )

    elif data.startswith("rmgoal_"):
        idx = int(data.replace("rmgoal_",""))
        goals = user.get("personal_goals",[])
        if 0 <= idx < len(goals):
            goals.pop(idx)
            user["personal_goals"] = goals
            save_users()
            await q.edit_message_text("Goal removed. Send /goals to manage.")

    elif data == "clear_goals":
        user["personal_goals"] = []
        save_users()
        await q.edit_message_text("Goals cleared. Send /goals to add new ones.")

    # ── Profile ──
    elif data == "profile_start":
        user["profile_step"] = "age"
        await q.edit_message_text("Health Profile - Step 1 of 7\n\nHow old are you?\n\nJust type your age (e.g. 35)")

    elif data == "profile_clear":
        user["profile"] = {"age":None,"sex":None,"fitness":None,"conditions":[],"medications":[],"sleep_quality":None,"stress_level":None}
        save_users()
        await q.edit_message_text("Profile cleared. Send /profile to set it up again.")

    elif data.startswith("profile_sex_"):
        user["profile"]["sex"] = data.replace("profile_sex_","")
        user["profile_step"] = "fitness"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 3 of 7\n\nFitness level?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Sedentary", callback_data="profile_fitness_sedentary")],
                [InlineKeyboardButton("Lightly active", callback_data="profile_fitness_light")],
                [InlineKeyboardButton("Moderately active", callback_data="profile_fitness_moderate")],
                [InlineKeyboardButton("Very active", callback_data="profile_fitness_active")],
                [InlineKeyboardButton("Athlete", callback_data="profile_fitness_athlete")],
            ])
        )

    elif data.startswith("profile_fitness_"):
        user["profile"]["fitness"] = data.replace("profile_fitness_","")
        user["profile_step"] = "conditions"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 4 of 7\n\nAny medical conditions?\nType them or tap Skip.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip", callback_data="profile_skip_conditions")]])
        )

    elif data == "profile_skip_conditions":
        user["profile"]["conditions"] = []
        user["profile_step"] = "medications"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 5 of 7\n\nAny medications?\nType them or tap Skip.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip", callback_data="profile_skip_medications")]])
        )

    elif data == "profile_skip_medications":
        user["profile"]["medications"] = []
        user["profile_step"] = "sleep"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 6 of 7\n\nSleep quality?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Poor - under 5h", callback_data="profile_sleep_poor")],
                [InlineKeyboardButton("Fair - 5-6h", callback_data="profile_sleep_fair")],
                [InlineKeyboardButton("Good - 7-8h", callback_data="profile_sleep_good")],
                [InlineKeyboardButton("Excellent - 8h+", callback_data="profile_sleep_excellent")],
            ])
        )

    elif data.startswith("profile_sleep_"):
        user["profile"]["sleep_quality"] = data.replace("profile_sleep_","")
        user["profile_step"] = "stress"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 7 of 7\n\nTypical stress level?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Low", callback_data="profile_stress_low")],
                [InlineKeyboardButton("Moderate", callback_data="profile_stress_moderate")],
                [InlineKeyboardButton("High", callback_data="profile_stress_high")],
                [InlineKeyboardButton("Very high", callback_data="profile_stress_very_high")],
            ])
        )

    elif data.startswith("profile_stress_"):
        user["profile"]["stress_level"] = data.replace("profile_stress_","")
        user["profile_step"] = None
        if user.get("onboarding"):
            user["step"] = "active"
            user["onboarding"] = None
        save_users()
        await q.edit_message_text(
            "Profile complete! Every habit from now on is personalised for you.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Get My Habits!", callback_data="get_habits_now")]])
        )

# ── REMINDERS ─────────────────────────────────────────────
async def send_reminder(context):
    uid = context.job.data["uid"]
    purpose = context.job.data["purpose"]
    user = get_user(uid)
    if not user["reminders_active"] or user["step"] != "active":
        return
    today = datetime.now().strftime("%Y-%m-%d")
    pids = get_active_pillars(user)
    done_count = sum(1 for p in pids if user["checked_today"].get(p)==today)
    total = len(pids)
    if purpose == "morning":
        msg = await ai_msg(user, "morning")
        lines = [f"Good morning, {user['name'] or 'champ'}! {msg}\n"]
        for pid in pids:
            p = PILLARS[pid]
            h = get_current_habit(user, pid)
            done = user["checked_today"].get(pid) == today
            rung_info = get_rung_display(user, pid)
            lines.append(f"{'✅' if done else p['emoji']} {p['name']} [{rung_info}]")
            if not done:
                lines.append(f"   {h['habit']}")
        try:
            await context.bot.send_message(chat_id=uid, text="\n".join(lines), reply_markup=main_habit_kb(user))
        except Exception as e:
            print(f"Reminder err: {e}")
    else:
        nudges = {
            "midday":    f"Midday check — {done_count}/{total} done. Keep going!",
            "afternoon": f"Afternoon push — {done_count}/{total} habits done. Still time.",
            "night":     f"Day wrapping up — {done_count}/{total} habits. Streak: {user['streak']}.",
        }
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=nudges.get(purpose, "Stay on track!"),
                reply_markup=main_habit_kb(user) if done_count < total else None
            )
        except Exception as e:
            print(f"Reminder err: {e}")

def schedule_reminders(app, uid):
    user = get_user(uid)
    try: tz = pytz.timezone(user.get("timezone","UTC"))
    except: tz = pytz.UTC
    for job in app.job_queue.get_jobs_by_name(str(uid)):
        job.schedule_removal()
    if not user["reminders_active"]: return
    for slot, info in SLOTS.items():
        t_str = user["reminders"].get(slot, info["default"])
        try:
            h, m = map(int, t_str.split(":"))
            app.job_queue.run_daily(send_reminder, time=time(hour=h, minute=m, tzinfo=tz), name=str(uid), data={"uid":uid,"purpose":slot})
        except Exception as e:
            print(f"Schedule err {slot}: {e}")

async def check_missed_days(context):
    today_dt = datetime.now()
    for uid, user in users.items():
        if user.get("step") != "active": continue
        last = user.get("last_active_date")
        if not last: continue
        try:
            days_missed = (today_dt - datetime.strptime(last, "%Y-%m-%d")).days
            if days_missed >= 2 and not user.get("missed_days_alerted"):
                user["missed_days_alerted"] = True
                name = user["name"] or "champ"
                try:
                    msg = await groq(f"{name} missed {days_missed} days. Streak was {user['streak']}. Short personal message to bring them back. 2 sentences.", "Direct habit coach. Personal outreach. Real talk.")
                except:
                    msg = f"{days_missed} days gone, {name}. Your streak is waiting — one habit today brings it back."
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"{msg}\n\nSend /habit to get back on track.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Get Back on Track", callback_data="get_habits_now")]])
                )
                save_users()
        except Exception as e:
            print(f"Missed days err {uid}: {e}")

async def send_weekly_report(context):
    for uid, user in users.items():
        if user.get("step") != "active" or not user.get("weekly_history"): continue
        try:
            h7 = user["weekly_history"][-7:]
            days = len(h7)
            total = sum(len(r.get("pillars",[])) for r in h7)
            pc = {}
            for r in h7:
                for p in r.get("pillars",[]): pc[p] = pc.get(p,0)+1
            breakdown = "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {c}x" for p,c in sorted(pc.items(),key=lambda x:-x[1])])
            try:
                report = await groq(f"Weekly report for {user['name']}. {days}/7 days. {total} habits. Pillars: {breakdown}. Honest coaching.", "Direct coach. Max 3 sentences.", max_tokens=150)
            except:
                report = f"{days}/7 days. {total} habits done. Keep showing up."
            await context.bot.send_message(chat_id=uid, text=f"Weekly Report\n\n{days}/7 days - {total} habits\n\n{breakdown}\n\nCoach: {report}")
        except Exception as e:
            print(f"Weekly err {uid}: {e}")

# ── CHAT ──────────────────────────────────────────────────
async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    text = update.message.text

    if user.get("profile_step"):
        step = user["profile_step"]
        if step == "age":
            try:
                age = int(text.strip())
                assert 10 <= age <= 120
                user["profile"]["age"] = age
                user["profile_step"] = "sex"
                save_users()
                await update.message.reply_text(
                    "Health Profile - Step 2 of 7\n\nBiological sex?",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Male", callback_data="profile_sex_male")],
                        [InlineKeyboardButton("Female", callback_data="profile_sex_female")],
                        [InlineKeyboardButton("Prefer not to say", callback_data="profile_sex_unspecified")],
                    ])
                )
            except:
                await update.message.reply_text("Please enter a valid age (e.g. 35)")
            return
        elif step == "conditions":
            user["profile"]["conditions"] = [c.strip() for c in text.split(",") if c.strip()]
            user["profile_step"] = "medications"
            save_users()
            await update.message.reply_text(
                "Got it! Any medications? Type them or tap Skip.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip", callback_data="profile_skip_medications")]])
            )
            return
        elif step == "medications":
            user["profile"]["medications"] = [m.strip() for m in text.split(",") if m.strip()]
            user["profile_step"] = "sleep"
            save_users()
            await update.message.reply_text(
                "Got it! Sleep quality?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Poor", callback_data="profile_sleep_poor")],
                    [InlineKeyboardButton("Fair", callback_data="profile_sleep_fair")],
                    [InlineKeyboardButton("Good", callback_data="profile_sleep_good")],
                    [InlineKeyboardButton("Excellent", callback_data="profile_sleep_excellent")],
                ])
            )
            return

    if user.get("setting_slot"):
        slot = user["setting_slot"]
        try:
            h, m = map(int, text.strip().split(":"))
            assert 0 <= h <= 23 and 0 <= m <= 59
            user["reminders"][slot] = f"{h:02d}:{m:02d}"
            user["setting_slot"] = None
            save_users()
            await update.message.reply_text(
                f"{SLOTS[slot]['label']} set to {user['reminders'][slot]}\n\nSet other times or tap Save.",
                reply_markup=reminders_kb(user)
            )
        except:
            await update.message.reply_text("Invalid format. Please send as HH:MM example: 08:30")
        return

    if user.get("adding_goal"):
        goal = text.strip()
        if len(goal) > 5:
            goals = user.get("personal_goals",[])
            if len(goals) >= 5:
                user["adding_goal"] = False
                await update.message.reply_text("You have 5 goals already. Send /goals to remove one first.")
            else:
                goals.append(goal)
                user["personal_goals"] = goals
                user["adding_goal"] = False
                save_users()
                if user.get("onboarding") == "goals":
                    await update.message.reply_text(
                        f"Goal {len(goals)} added: {goal}\n\n{'Add another or continue.' if len(goals)<5 else 'Max 5 goals.'}",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Add Another Goal", callback_data="add_another_goal")],
                            [InlineKeyboardButton("Continue to Timezone", callback_data="onboard_skip_goals")],
                        ])
                    )
                else:
                    await update.message.reply_text(f"Goal added: {goal}\n\nSend /goals to manage.")
        else:
            await update.message.reply_text("Please describe your goal in a bit more detail.")
        return

    # AI coach
    try:
        scores_str = ", ".join([f"{PILLARS[k]['name']}:{v}/5" for k,v in user["scores"].items()]) or "not assessed"
        ladder_str = ", ".join([f"{PILLARS[p]['name']} rung {user['ladder'][p]['rung']+1}" for p in PIDS])
        reply = await groq(
            text,
            f"Habit coach for {user['name'] or 'user'}. Streak: {user['streak']}. Scores: {scores_str}. Ladder: {ladder_str}. Short punchy advice. Max 2 sentences.",
            max_tokens=100
        )
    except:
        reply = "Keep going. One habit at a time."
    await update.message.reply_text(reply)

# ── MAIN ──────────────────────────────────────────────────
def main():
    import urllib.request, time as _time
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        print("Webhook cleared")
    except Exception as e:
        print(f"Webhook: {e}")
    print("Waiting 5s...")
    _time.sleep(5)
    load_users()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("habit",     cmd_habit))
    app.add_handler(CommandHandler("ladder",    cmd_ladder))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("assess",    cmd_assess))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("goals",     cmd_goals))
    app.add_handler(CommandHandler("profile",   cmd_profile))
    app.add_handler(CommandHandler("timezone",  cmd_timezone))
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(CallbackQueryHandler(handle_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_chat))

    app.job_queue.run_daily(send_weekly_report, time=time(hour=8, minute=0, tzinfo=pytz.UTC), days=(6,), name="weekly_report")
    app.job_queue.run_daily(check_missed_days,  time=time(hour=10, minute=0, tzinfo=pytz.UTC), name="missed_days")

    async def reschedule_on_startup(app):
        for uid, user in users.items():
            if user.get("reminders_active"):
                schedule_reminders(app, uid)
                print(f"Rescheduled reminders for user {uid}")

    app.post_init = reschedule_on_startup
    print("CoreSix bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
