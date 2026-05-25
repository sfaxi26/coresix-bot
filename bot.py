import os
import json
import random
import asyncio
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# ── CONFIG ──────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TOKEN_HERE")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ── AI ──────────────────────────────────────────────────
import urllib.request
import json as _json

def call_groq(prompt, system):
    """Call Groq API synchronously."""
    if not GROQ_API_KEY:
        return ""
    try:
        payload = _json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 300,
            "temperature": 0.85,
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Groq error: {e}")
        return ""

# ── DATA ────────────────────────────────────────────────
DEFAULT_ORDER = ["fuel", "move", "rest", "calm", "connect", "focus"]

PILLARS = {
    "fuel":    {"name": "Fuel",    "emoji": "⚡", "description": "Nutrition",        "identity": "The Nourisher", "story": "Your body is where everything starts. This week you feed it with intention."},
    "move":    {"name": "Move",    "emoji": "💪", "description": "Movement",         "identity": "The Athlete",   "story": "Your body was built to move. This week you wake it up — one tiny step at a time."},
    "rest":    {"name": "Rest",    "emoji": "😴", "description": "Sleep & Recovery", "identity": "The Restorer",  "story": "Everything is rebuilt in silence. This week you give your body the gift of rest."},
    "calm":    {"name": "Calm",    "emoji": "🧘", "description": "Stress Management","identity": "The Sage",      "story": "In a noisy world, calm is a superpower. This week you find your centre."},
    "connect": {"name": "Connect", "emoji": "🤝", "description": "Social Connection","identity": "The Connector", "story": "No story is written alone. This week you invest in the people who matter."},
    "focus":   {"name": "Focus",   "emoji": "🎯", "description": "Purpose & Mindset","identity": "The Visionary", "story": "Clarity is the beginning of power. This week you sharpen your why."},
}

HABITS = {
    "fuel": [
        "Drink a full glass of water before your morning coffee",
        "Add one handful of greens to your next meal",
        "Eat breakfast sitting down without your phone",
        "Chew slowly and put your fork down between bites",
        "Drink water with every meal today",
        "Replace one snack with a piece of fruit",
        "Add one vegetable to your lunch however small",
        "Have a glass of water the moment you wake up",
        "Eat one meal today with no screen in front of you",
    ],
    "move": [
        "Do 10 jumping jacks right after your alarm",
        "Do 5 push-ups before stepping into the shower",
        "Walk around the block once after lunch",
        "Do 10 calf raises while brushing your teeth",
        "Stretch your neck and shoulders after every call",
        "Take the stairs instead of the elevator once",
        "Stand up and move for 2 minutes every hour",
        "Do a 60-second wall sit while coffee brews",
        "Walk to a colleague instead of sending a message",
    ],
    "rest": [
        "Put your phone charger across the room before bed",
        "Do 4 slow deep breaths the moment you get into bed",
        "Set a sleep alarm 30 minutes before bedtime",
        "Dim your phone brightness after 8pm",
        "Make your bed immediately after waking",
        "Sit in silence for 2 minutes after your alarm",
        "Write tomorrow's top task before closing your laptop",
        "No screens for 10 minutes before sleep",
        "Put on sleep music as soon as you sit on the couch",
    ],
    "calm": [
        "Take 3 slow breaths before opening any social app",
        "Write one thing you're grateful for before your phone",
        "Sit in silence for 2 minutes with your morning drink",
        "Name 5 things you can see right now slowly",
        "Put your phone in another room for 30 minutes",
        "Write one worry down then close the notebook",
        "Step outside and feel the air for 60 seconds",
        "Do a 2-minute body scan and notice where you hold tension",
        "Listen to one calming song with your eyes closed",
    ],
    "connect": [
        "Send one voice note to a friend instead of texting",
        "Reply to one message you've been avoiding",
        "Give someone a specific genuine compliment today",
        "Put your phone face-down during your next conversation",
        "Tell someone one thing you appreciate about them",
        "Write a 2-line message to someone you miss",
        "Make eye contact and smile at the next person you pass",
        "Call instead of texting one person today",
        "Share something funny with someone to brighten their day",
    ],
    "focus": [
        "Write your single most important task before opening email",
        "Read one page of a book before reaching for your phone",
        "Spend 2 minutes visualizing your ideal day",
        "Close all tabs except the one you're working on",
        "Set a 25-minute timer and work on one thing only",
        "Write your goal for this week in one sentence",
        "Say your top priority out loud before sitting at your desk",
        "Turn off all notifications for the next 30 minutes",
        "Write what done looks like for your main task today",
    ],
}

# ── USER STATE (in-memory, replace with DB for production) ──
users = {}  # user_id -> state dict

def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "name": "",
            "step": "welcome",         # welcome | assess | journey
            "scores": {},
            "week_order": DEFAULT_ORDER.copy(),
            "current_week": 0,
            "day_in_week": 1,
            "streak": 0,
            "checked_today": False,
            "today_habits": [],
            "selected_habit": "",
        }
    return users[user_id]

def get_week_order(scores):
    """Sort pillars by score ascending (weakest first), use default as tiebreaker."""
    return sorted(DEFAULT_ORDER, key=lambda p: (scores.get(p, 3), DEFAULT_ORDER.index(p)))

def pick_habits(pillar_id):
    """Pick 3 unique random habits for today."""
    opts = HABITS.get(pillar_id, []).copy()
    random.shuffle(opts)
    return opts[:3]

def current_pillar(user):
    pid = user["week_order"][user["current_week"]]
    return pid, PILLARS[pid]

# ── KEYBOARDS ────────────────────────────────────────────
def score_keyboard(pillar_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(str(n), callback_data=f"score_{pillar_id}_{n}")
        for n in range(1, 6)
    ]])

def habit_keyboard(habits, pillar_id):
    labels = ["🌱 Easy", "⚡ Normal", "🔥 Challenge"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{labels[i]}", callback_data=f"pick_{i}")]
        for i in range(len(habits))
    ])

def checkin_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Done — mark it in!", callback_data="checkin")
    ]])

def start_journey_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Start My Journey", callback_data="start_journey"),
        InlineKeyboardButton("📋 Assess First", callback_data="start_assess"),
    ]])

# ── HANDLERS ─────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["name"] = update.effective_user.first_name or "Hero"
    user["step"] = "welcome"

    # AI welcome message
    story = call_groq(
        f"Write a powerful 2-sentence opening for {user['name']}'s 6-week life transformation journey called CoreSix. Make it cinematic and personal. No quotes.",
        "You are a cinematic narrator for a personal transformation app. Be warm, epic, and specific. Never use clichés like 'embark' or 'journey begins'."
    )
    if not story:
        story = f"Six pillars. Six weeks. One new version of {user['name']}."

    await update.message.reply_text(
        f"✨ *Welcome to CoreSix, {user['name']}!*\n\n"
        f"_{story}_\n\n"
        "📖 *6 weeks. 6 pillars. One tiny habit a day.*\n\n"
        "⚡ Fuel · 💪 Move · 😴 Rest\n"
        "🧘 Calm · 🤝 Connect · 🎯 Focus\n\n"
        "Every day I'll send you *3 habit options* — pick the one that fits your day.\n\n"
        "Want a quick assessment to personalise your order? Or just start with Fuel?",
        parse_mode="Markdown",
        reply_markup=start_journey_keyboard()
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    pid, pillar = current_pillar(user)
    week_num = user["current_week"] + 1
    day_num = user["day_in_week"]
    streak = user["streak"]

    progress = ""
    for i, wid in enumerate(user["week_order"]):
        p = PILLARS[wid]
        if i < user["current_week"]:
            progress += f"✅ Week {i+1}: {p['emoji']} {p['name']}\n"
        elif i == user["current_week"]:
            progress += f"▶️ Week {i+1}: {p['emoji']} {p['name']} — Day {day_num}/7\n"
        else:
            progress += f"⬜ Week {i+1}: {p['emoji']} {p['name']}\n"

    await update.message.reply_text(
        f"📊 *Your CoreSix Journey*\n\n"
        f"🔥 Streak: {streak} days\n"
        f"📍 Currently: Week {week_num} — {pillar['emoji']} {pillar['name']} ({pillar['identity']})\n"
        f"📅 Day {day_num} of 7\n\n"
        f"*Roadmap:*\n{progress}",
        parse_mode="Markdown"
    )

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Send today's 3 habit options."""
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user["step"] == "welcome":
        await update.message.reply_text("Start your journey first! Send /start")
        return

    pid, pillar = current_pillar(user)
    habits = pick_habits(pid)
    user["today_habits"] = habits
    user["selected_habit"] = habits[0]
    user["checked_today"] = False

    text = (
        f"{pillar['emoji']} *Week {user['current_week']+1} — {pillar['name']} Week*\n"
        f"_{pillar['identity']}_ · Day {user['day_in_week']}/7\n\n"
        f"Pick today's tiny habit based on how you feel:\n\n"
        f"🌱 *Easy* — {habits[0]}\n\n"
        f"⚡ *Normal* — {habits[1]}\n\n"
        f"🔥 *Challenge* — {habits[2]}"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=habit_keyboard(habits, pid)
    )

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    data = query.data

    # ── Start journey ──
    if data == "start_journey":
        user["week_order"] = DEFAULT_ORDER.copy()
        user["step"] = "journey"
        pid, pillar = current_pillar(user)
        habits = pick_habits(pid)
        user["today_habits"] = habits
        user["selected_habit"] = habits[0]

        ai_story = call_groq(
            f"Write a 2-sentence cinematic opening for {user['name']}'s Week 1 — {pillar['name']} week. Identity: {pillar['identity']}. Theme: {pillar['story']}. Make it feel epic and personal.",
            "You are a cinematic narrator for a life transformation app. 2 sentences max. Be specific and powerful. No clichés."
        ) or pillar['story']

        await query.edit_message_text(
            f"🚀 *Your journey begins!*\n\n"
            f"Week 1 — {pillar['emoji']} *{pillar['name']} Week*\n"
            f"_{pillar['identity']}_\n\n"
            f"_{ai_story}_\n\n"
            f"Today's 3 habit options:\n\n"
            f"🌱 *Easy* — {habits[0]}\n\n"
            f"⚡ *Normal* — {habits[1]}\n\n"
            f"🔥 *Challenge* — {habits[2]}",
            parse_mode="Markdown",
            reply_markup=habit_keyboard(habits, pid)
        )

    # ── Start assess ──
    elif data == "start_assess":
        user["step"] = "assess"
        user["scores"] = {}
        pid = DEFAULT_ORDER[0]
        p = PILLARS[pid]
        await query.edit_message_text(
            f"📋 *Quick Assessment*\n\n"
            f"Rate each pillar 1–5 to personalise your 6-week order.\n"
            f"_1 = struggling · 5 = thriving_\n\n"
            f"{p['emoji']} *{p['name']}* — {p['description']}\n"
            f"How are you doing here?",
            parse_mode="Markdown",
            reply_markup=score_keyboard(pid)
        )

    # ── Score a pillar ──
    elif data.startswith("score_"):
        _, pid, score = data.split("_")
        user["scores"][pid] = int(score)
        scored = list(user["scores"].keys())
        remaining = [p for p in DEFAULT_ORDER if p not in scored]

        if remaining:
            next_pid = remaining[0]
            p = PILLARS[next_pid]
            progress = f"{len(scored)}/6 rated"
            await query.edit_message_text(
                f"📋 *Assessment* _{progress}_\n\n"
                f"{p['emoji']} *{p['name']}* — {p['description']}\n"
                f"How are you doing here?",
                parse_mode="Markdown",
                reply_markup=score_keyboard(next_pid)
            )
        else:
            # All scored — build order
            order = get_week_order(user["scores"])
            user["week_order"] = order
            user["step"] = "journey"
            pid, pillar = current_pillar(user)
            habits = pick_habits(pid)
            user["today_habits"] = habits
            user["selected_habit"] = habits[0]

            order_text = "\n".join([
                f"W{i+1}: {PILLARS[wid]['emoji']} {PILLARS[wid]['name']} (score: {user['scores'].get(wid,'?')}/5)"
                for i, wid in enumerate(order)
            ])

            await query.edit_message_text(
                f"✅ *Assessment complete!*\n\n"
                f"*Your personalised 6-week order:*\n{order_text}\n\n"
                f"Starting with your weakest pillar first 💪\n\n"
                f"Week 1 — {pillar['emoji']} *{pillar['name']} Week*\n"
                f"_{pillar['identity']}_\n\n"
                f"_{pillar['story']}_\n\n"
                f"Today's habits:\n\n"
                f"🌱 *Easy* — {habits[0]}\n\n"
                f"⚡ *Normal* — {habits[1]}\n\n"
                f"🔥 *Challenge* — {habits[2]}",
                parse_mode="Markdown",
                reply_markup=habit_keyboard(habits, pid)
            )

    # ── Pick a habit ──
    elif data.startswith("pick_"):
        idx = int(data.split("_")[1])
        habit = user["today_habits"][idx] if idx < len(user["today_habits"]) else ""
        user["selected_habit"] = habit
        labels = ["🌱 Easy", "⚡ Normal", "🔥 Challenge"]
        pid, pillar = current_pillar(user)

        await query.edit_message_text(
            f"{pillar['emoji']} *{pillar['name']} Week* — Day {user['day_in_week']}/7\n\n"
            f"*You picked:* {labels[idx]}\n\n"
            f"_{habit}_\n\n"
            f"When you're done, tap below to mark it in your story ✍️",
            parse_mode="Markdown",
            reply_markup=checkin_keyboard()
        )

    # ── Check in ──
    elif data == "checkin":
        user["streak"] += 1
        user["checked_today"] = True
        pid, pillar = current_pillar(user)
        streak = user["streak"]
        day = user["day_in_week"]
        habit = user["selected_habit"]

        # Advance day or week
        is_last_day = day >= 7
        is_last_week = user["current_week"] >= 5

        ai_chapter = call_groq(
            f"{user['name']} just completed day {day} of their {pillar['name']} week as {pillar['identity']}. Habit done: '{habit}'. Streak: {streak} days. Write 2 cinematic sentences narrating this moment in their story.",
            "You are a cinematic narrator. Write in second person present tense. Be specific to what they did. 2 sentences max. Make it feel earned."
        ) or f"Day {day} written into your story. Every small act compounds into the person you're becoming."

        msg = (
            f"✅ *Day {day} written into your story!*\n\n"
            f"_{ai_chapter}_\n\n"
            f"🔥 Streak: {streak} days\n\n"
        )

        if is_last_day and is_last_week:
            msg += "🏆 *You've completed the full CoreSix journey!*\nYou are not the same person who started. Send /start to begin again."
            user["step"] = "welcome"
        elif is_last_day:
            next_week = user["current_week"] + 1
            next_pid = user["week_order"][next_week]
            next_pillar = PILLARS[next_pid]
            user["current_week"] = next_week
            user["day_in_week"] = 1
            msg += (
                f"🎉 *{pillar['name']} Week complete!*\n\n"
                f"Next up: Week {next_week+1} — {next_pillar['emoji']} *{next_pillar['name']} Week*\n"
                f"_{next_pillar['identity']}_\n\n"
                f"_{next_pillar['story']}_\n\n"
                f"Send /habit tomorrow to get your new options."
            )
        else:
            user["day_in_week"] += 1
            msg += f"Day {day+1} of 7 tomorrow. Send /habit when you're ready."

        await query.edit_message_text(msg, parse_mode="Markdown")

async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle free-text messages as AI coach chat."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    text = update.message.text

    if user["step"] == "welcome":
        await update.message.reply_text("Send /start to begin your journey first!")
        return

    pid, pillar = current_pillar(user)
    scores_str = ", ".join([f"{k}:{v}" for k,v in user["scores"].items()]) or "not assessed"

    reply = call_groq(
        f"User message: {text}",
        f"You are a wise journey guide for {user['name']} on their CoreSix transformation. "
        f"Week {user['current_week']+1} — {pillar['name']} week ({pillar['identity']}). "
        f"Day {user['day_in_week']} of 7. Streak: {user['streak']} days. "
        f"Pillar scores: {scores_str}. "
        f"Speak like a mentor who knows their story. Max 3 sentences. Be warm and specific."
    )

    if not reply:
        reply = "I'm your journey guide — I'm here. Keep going, one tiny habit at a time."

    await update.message.reply_text(f"🧭 _{reply}_", parse_mode="Markdown")

# ── MAIN ─────────────────────────────────────────────────
def main():
    import time
    import urllib.request

    # Force close any existing polling sessions via raw HTTP
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
    try:
        urllib.request.urlopen(url)
        print("✅ Webhook cleared")
    except Exception as e:
        print(f"Webhook clear attempt: {e}")

    # Wait to ensure Telegram closes old connections
    print("⏳ Waiting for Telegram to release old connections...")
    time.sleep(5)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("habit", cmd_habit))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_chat))
    print("🤖 CoreSix bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
