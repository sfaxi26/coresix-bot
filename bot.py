import os
import random
import asyncio
import json
from datetime import datetime, time
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters, JobQueue
)

# ── CONFIG ──────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ── PILLARS ─────────────────────────────────────────────
PILLARS = {
    "fuel":    {"name": "Fuel",    "emoji": "⚡", "description": "Nutrition"},
    "move":    {"name": "Move",    "emoji": "💪", "description": "Movement"},
    "rest":    {"name": "Rest",    "emoji": "😴", "description": "Sleep & Recovery"},
    "calm":    {"name": "Calm",    "emoji": "🧘", "description": "Stress Management"},
    "connect": {"name": "Connect", "emoji": "🤝", "description": "Social Connection"},
    "focus":   {"name": "Focus",   "emoji": "🎯", "description": "Purpose & Mindset"},
}
PILLAR_IDS = list(PILLARS.keys())

FALLBACK = {
    "fuel":    ["Drink water before coffee", "Add one vegetable to your next meal", "Eat one meal without your phone"],
    "move":    ["5 push-ups before your shower", "Walk around the block after lunch", "Stretch 60 seconds now"],
    "rest":    ["Phone charger across the room tonight", "4 deep breaths before sleep", "Make your bed right after waking"],
    "calm":    ["3 breaths before opening any app", "Write one thing you're grateful for", "2 minutes silence with your morning drink"],
    "connect": ["One genuine message to a friend", "Give someone a real compliment", "Phone down during your next conversation"],
    "focus":   ["Write your one priority before email", "Read one page before your phone", "Notifications off for 30 minutes"],
}

# ── REMINDER SLOTS ──────────────────────────────────────
SLOTS = {
    "morning":   {"label": "🌅 Morning",   "default": "07:00", "purpose": "morning"},
    "midday":    {"label": "☀️ Midday",    "default": "12:00", "purpose": "midday"},
    "afternoon": {"label": "🌆 Afternoon", "default": "16:00", "purpose": "afternoon"},
    "night":     {"label": "🌙 Night",     "default": "21:00", "purpose": "night"},
}

# ── USER STATE ───────────────────────────────────────────
users = {}

def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "name": "",
            "step": "welcome",
            "scores": {},
            "streak": 0,
            "today_pillars": [],
            "today_habits": {},
            "checked": {},
            "timezone": "UTC",
            "reminders": {
                "morning":   "07:00",
                "midday":    "12:00",
                "afternoon": "16:00",
                "night":     "21:00",
            },
            "reminders_active": False,
            "setting_slot": None,
            "personal_goals": [],      # user's custom focus goals
            "adding_goal": False,
            "weekly_history": [],      # list of daily check-in records
            "score_history": [],       # list of weekly score snapshots
            "last_checkin_date": None, # date of last check-in
        }
    return users[user_id]

# ── GROQ AI ──────────────────────────────────────────────
async def groq_async(prompt, system, max_tokens=300):
    import httpx
    if not GROQ_API_KEY:
        return ""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.9,
            },
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

async def ai_pick_pillars(user):
    scores = user["scores"]
    if not scores:
        return random.sample(PILLAR_IDS, 3)
    try:
        system = "You are a smart habit coach. Respond ONLY with a JSON array of exactly 3 pillar IDs. No explanation."
        prompt = (
            f"Scores (1-5, lower=needs work): {json.dumps(scores)}. "
            f"Streak: {user['streak']} days. "
            f"Pick 3 pillars for today. Balance weakness and variety. "
            f"Pillar IDs: {PILLAR_IDS}. "
            f'Return ONLY: ["id1","id2","id3"]'
        )
        result = await groq_async(prompt, system, max_tokens=50)
        pillars = json.loads(result.strip())
        if isinstance(pillars, list) and len(pillars) == 3 and all(p in PILLAR_IDS for p in pillars):
            return pillars
    except Exception as e:
        print(f"AI pillar error: {e}")
    sorted_p = sorted(PILLAR_IDS, key=lambda p: scores.get(p, 3))
    return random.sample(sorted_p[:4], 3)

async def ai_generate_habits(user, pillar_ids):
    hour = datetime.now().hour
    time_of_day = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    streak = user["streak"]
    level = "beginner" if streak < 7 else "intermediate" if streak < 21 else "advanced"
    name = user["name"] or "the user"
    scores = user["scores"]
    pillar_info = ", ".join([f"{PILLARS[p]['name']} (score {scores.get(p,'?')}/5)" for p in pillar_ids])
    goals = user.get("personal_goals", [])
    goals_str = f" Personal goals: {', '.join(goals)}." if goals else ""
    try:
        system = (
            "You are a no-nonsense habit coach. Short, punchy, direct. "
            "Respond ONLY with valid JSON. No markdown."
        )
        prompt = (
            f"Create 3 tiny habits for {name}, one per pillar: {pillar_info}. "
            f"Time: {time_of_day}. Level: {level}. Streak: {streak} days.{goals_str} "
            f"IMPORTANT: Where possible, weave the personal goals into the habits naturally. "
            f"Each habit under 2 minutes, anchored to an existing routine. Fresh and specific. "
            f'Return ONLY: {{"{pillar_ids[0]}":"habit","{pillar_ids[1]}":"habit","{pillar_ids[2]}":"habit"}}'
        )
        result = await groq_async(prompt, system, max_tokens=200)
        clean = result.strip().replace("```json","").replace("```","")
        habits = json.loads(clean)
        if all(p in habits for p in pillar_ids):
            return habits
    except Exception as e:
        print(f"AI habit error: {e}")
    return {p: random.choice(FALLBACK.get(p, ["Do one small thing"])) for p in pillar_ids}

async def ai_reminder_msg(user, purpose):
    name = user["name"] or "champ"
    streak = user["streak"]
    done = len(user.get("checked", {}))
    total = len(user.get("today_pillars", []))
    habits_text = "\n".join([
        f"{PILLARS[p]['emoji']} {user['today_habits'].get(p,'')}"
        for p in user.get("today_pillars", [])
        if p not in user.get("checked", {})
    ])

    prompts = {
        "morning": f"Morning message for {name}. Streak: {streak} days. Send them their habits for the day. Punchy opener then list habits. 2 sentences max intro.",
        "midday":  f"Midday check-in for {name}. Done {done}/{total} habits. {f'Remaining: {habits_text}' if habits_text else 'All done already!'}. Short punchy nudge.",
        "afternoon": f"Afternoon push for {name}. Done {done}/{total} habits. {f'Still need: {habits_text}' if habits_text else 'Already crushed it!'}. One punchy sentence.",
        "night":   f"Night wrap-up for {name}. Done {done}/{total} habits today. Streak: {streak}. Short reflection. Honest. 1-2 sentences.",
    }
    try:
        system = "You are a direct habit coach. Short punchy texts like a real coach. No fluff. Max 2 sentences."
        return await groq_async(prompts.get(purpose, prompts["morning"]), system, max_tokens=80)
    except:
        defaults = {
            "morning":   f"Morning, {name}. Your 3 habits are ready. Let's go.",
            "midday":    f"{done}/{total} done. Keep moving, {name}.",
            "afternoon": f"Afternoon check — {done}/{total} habits done. Still time.",
            "night":     f"Day done. {done}/{total} habits. Streak: {streak} days.",
        }
        return defaults.get(purpose, "Stay on track.")

# ── REMINDER JOB ────────────────────────────────────────
async def send_reminder(context):
    """Scheduled job — sends reminder to one user."""
    user_id = context.job.data["user_id"]
    purpose = context.job.data["purpose"]
    user = get_user(user_id)

    if not user["reminders_active"]:
        return

    # Morning — generate fresh habits
    if purpose == "morning":
        pillars = await ai_pick_pillars(user)
        habits  = await ai_generate_habits(user, pillars)
        user["today_pillars"] = pillars
        user["today_habits"]  = habits
        user["checked"]       = {}

    msg = await ai_reminder_msg(user, purpose)

    icons = {"morning":"🌅","midday":"☀️","afternoon":"🌆","night":"🌙"}
    icon = icons.get(purpose, "⏰")

    # Build habit list for morning
    if purpose == "morning" and user["today_pillars"]:
        lines = [f"{icon} *{msg}*\n"]
        for pid in user["today_pillars"]:
            p = PILLARS[pid]
            h = user["today_habits"].get(pid, "")
            lines.append(f"{p['emoji']} *{p['name']}* — _{h}_")
        lines.append("\nTap to mark done 👇")
        text = "\n".join(lines)
    else:
        text = f"{icon} _{msg}_"

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=habit_select_keyboard(user) if purpose == "morning" else None
        )
    except Exception as e:
        print(f"Reminder send error: {e}")

def schedule_reminders(app, user_id):
    """Schedule all 4 reminders for a user."""
    user = get_user(user_id)
    tz_str = user.get("timezone", "UTC")
    try:
        tz = pytz.timezone(tz_str)
    except:
        tz = pytz.UTC

    # Remove existing jobs for this user
    current_jobs = app.job_queue.get_jobs_by_name(str(user_id))
    for job in current_jobs:
        job.schedule_removal()

    if not user["reminders_active"]:
        return

    for slot, slot_info in SLOTS.items():
        time_str = user["reminders"].get(slot, slot_info["default"])
        try:
            hour, minute = map(int, time_str.split(":"))
            t = time(hour=hour, minute=minute, tzinfo=tz)
            app.job_queue.run_daily(
                send_reminder,
                time=t,
                name=str(user_id),
                data={"user_id": user_id, "purpose": slot}
            )
        except Exception as e:
            print(f"Schedule error for {slot}: {e}")

# ── KEYBOARDS ────────────────────────────────────────────
def habit_select_keyboard(user):
    buttons = []
    for pid in user.get("today_pillars", []):
        p = PILLARS[pid]
        done = pid in user.get("checked", {})
        label = f"✅ {p['emoji']} {p['name']}" if done else f"{p['emoji']} {p['name']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"done_{pid}")])
    return InlineKeyboardMarkup(buttons) if buttons else None

def reminders_keyboard(user):
    buttons = []
    for slot, info in SLOTS.items():
        t = user["reminders"].get(slot, info["default"])
        buttons.append([InlineKeyboardButton(f"{info['label']} — {t}", callback_data=f"setslot_{slot}")])
    status = "🟢 ON" if user["reminders_active"] else "🔴 OFF"
    buttons.append([InlineKeyboardButton(f"Reminders: {status}", callback_data="toggle_reminders")])
    buttons.append([InlineKeyboardButton("✅ Save & Activate", callback_data="save_reminders")])
    return InlineKeyboardMarkup(buttons)

def goals_keyboard(goals):
    buttons = []
    for i, g in enumerate(goals):
        buttons.append([InlineKeyboardButton(f"❌ Remove: {g[:30]}", callback_data=f"remove_goal_{i}")])
    buttons.append([InlineKeyboardButton("➕ Add a goal", callback_data="add_goal")])
    if goals:
        buttons.append([InlineKeyboardButton("🗑 Clear all goals", callback_data="clear_goals")])
    return InlineKeyboardMarkup(buttons)

def score_keyboard(pid):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(str(n), callback_data=f"score_{pid}_{n}")
        for n in range(1, 6)
    ]])

# ── HANDLERS ─────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["name"] = update.effective_user.first_name or "Hero"
    user["step"] = "welcome"

    await update.message.reply_text(
        f"*CoreSix* — 6 pillars. 3 habits. Every day.\n\n"
        f"⚡ Fuel · 💪 Move · 😴 Rest\n"
        f"🧘 Calm · 🤝 Connect · 🎯 Focus\n\n"
        f"I'll send you reminders 4x a day — morning, midday, afternoon and night.\n\n"
        f"Let's set it up 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏰ Set My Reminders", callback_data="show_reminders")],
            [InlineKeyboardButton("🎯 Add Personal Goals", callback_data="add_goal")],
            [InlineKeyboardButton("📋 Quick Assessment", callback_data="assess")],
            [InlineKeyboardButton("⚡ Skip — Start Now", callback_data="skip_assess")],
        ])
    )

async def cmd_reminders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    await update.message.reply_text(
        "⏰ *Your Reminder Schedule*\n\nTap a time to change it:",
        parse_mode="Markdown",
        reply_markup=reminders_keyboard(user)
    )

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    await update.message.reply_text("⚡ Picking your habits...")
    user["checked"] = {}
    pillars = await ai_pick_pillars(user)
    habits  = await ai_generate_habits(user, pillars)
    user["today_pillars"] = pillars
    user["today_habits"]  = habits
    lines = [f"*Your 3 Habits Today*\n"]
    for pid in pillars:
        p = PILLARS[pid]
        lines.append(f"{p['emoji']} *{p['name']}* — _{habits.get(pid,'')}_")
    lines.append("\nTap each when done 👇")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=habit_select_keyboard(user)
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    scores = user["scores"]
    score_lines = "\n".join([
        f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {scores.get(p,'?')}/5"
        for p in PILLAR_IDS
    ]) if scores else "Not assessed yet — send /assess"
    reminder_lines = "\n".join([
        f"{SLOTS[s]['label']}: {user['reminders'].get(s, SLOTS[s]['default'])}"
        for s in SLOTS
    ])
    await update.message.reply_text(
        f"📊 *{user['name']}'s CoreSix*\n\n"
        f"🔥 Streak: {user['streak']} days\n"
        f"✅ Today: {len(user.get('checked',{}))}/{len(user.get('today_pillars',[]))} habits done\n\n"
        f"*Scores:*\n{score_lines}\n\n"
        f"*Reminders ({'ON' if user['reminders_active'] else 'OFF'}):*\n{reminder_lines}",
        parse_mode="Markdown"
    )

async def cmd_assess(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["step"] = "assess"
    user["scores"] = {}
    p = PILLARS[PILLAR_IDS[0]]
    await update.message.reply_text(
        f"Rate each pillar 1–5.\n_1 = struggling · 5 = thriving_\n\n"
        f"{p['emoji']} *{p['name']}* — {p['description']}",
        parse_mode="Markdown",
        reply_markup=score_keyboard(PILLAR_IDS[0])
    )

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    data = query.data

    # ── Show reminders ──
    if data == "show_reminders":
        await query.edit_message_text(
            "⏰ *Set Your Daily Reminders*\n\nTap a time to change it.\nI'll send your habits + nudges automatically.",
            parse_mode="Markdown",
            reply_markup=reminders_keyboard(user)
        )

    # ── Toggle reminders on/off ──
    elif data == "toggle_reminders":
        user["reminders_active"] = not user["reminders_active"]
        await query.edit_message_text(
            "⏰ *Your Reminder Schedule*\n\nTap a time to change it:",
            parse_mode="Markdown",
            reply_markup=reminders_keyboard(user)
        )

    # ── Save & activate reminders ──
    elif data == "save_reminders":
        user["reminders_active"] = True
        schedule_reminders(ctx.application, user_id)
        lines = "\n".join([f"{SLOTS[s]['label']}: {user['reminders'].get(s)}" for s in SLOTS])
        await query.edit_message_text(
            f"✅ *Reminders activated!*\n\n{lines}\n\n"
            f"I'll reach out 4 times a day.\nSend /habit anytime for your habits now.",
            parse_mode="Markdown"
        )

    # ── Set a specific slot time ──
    elif data.startswith("setslot_"):
        slot = data.replace("setslot_", "")
        user["setting_slot"] = slot
        info = SLOTS[slot]
        current = user["reminders"].get(slot, info["default"])
        await query.edit_message_text(
            f"⏰ *Change {info['label']} reminder*\n\n"
            f"Current time: *{current}*\n\n"
            f"Reply with your preferred time in *HH:MM* format\n"
            f"Example: `08:30` or `21:00`\n\n"
            f"_Make sure to use 24-hour format_",
            parse_mode="Markdown"
        )

    # ── Assess ──
    elif data == "assess":
        user["step"] = "assess"
        user["scores"] = {}
        p = PILLARS[PILLAR_IDS[0]]
        await query.edit_message_text(
            f"Rate each pillar 1–5.\n_1 = struggling · 5 = thriving_\n\n"
            f"{p['emoji']} *{p['name']}* — {p['description']}",
            parse_mode="Markdown",
            reply_markup=score_keyboard(PILLAR_IDS[0])
        )

    # ── Skip assess ──
    elif data == "skip_assess":
        user["step"] = "active"
        await query.edit_message_text(
            "Got it. Send /habit to get your 3 habits now.\nOr send /reminders to set up your daily schedule. 💪"
        )

    # ── Score pillar ──
    elif data.startswith("score_"):
        _, pid, score = data.split("_")
        user["scores"][pid] = int(score)
        scored = list(user["scores"].keys())
        remaining = [p for p in PILLAR_IDS if p not in scored]
        if remaining:
            next_p = PILLARS[remaining[0]]
            await query.edit_message_text(
                f"*{len(scored)}/6* ✓\n\n{next_p['emoji']} *{next_p['name']}* — {next_p['description']}",
                parse_mode="Markdown",
                reply_markup=score_keyboard(remaining[0])
            )
        else:
            user["step"] = "active"
            ranked = sorted(PILLAR_IDS, key=lambda p: user["scores"].get(p, 3))
            lines = [f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {user['scores'][p]}/5" for p in ranked]
            await query.edit_message_text(
                f"✅ *Done!*\n\n*Your pillars:*\n" + "\n".join(lines) +
                "\n\nAI picks your best 3 daily.\n\nSend /reminders to set up your schedule! ⏰",
                parse_mode="Markdown"
            )

    # ── Goals ──
    elif data == "add_goal":
        user["adding_goal"] = True
        await query.edit_message_text(
            "🎯 *Add a Personal Goal*

"
            "Tell me what you want to focus on. Examples:

"
            "• Drink more water
"
            "• Eat more protein
"
            "• Sleep before midnight
"
            "• Reduce screen time
"
            "• Walk 10,000 steps
"
            "• Eat more fibre

"
            "Just type your goal 👇",
            parse_mode="Markdown"
        )

    elif data.startswith("remove_goal_"):
        idx = int(data.replace("remove_goal_", ""))
        goals = user.get("personal_goals", [])
        if 0 <= idx < len(goals):
            removed = goals.pop(idx)
            user["personal_goals"] = goals
            await query.edit_message_text(
                f"✅ Removed: _{removed}_

Send /goals to manage your goals.",
                parse_mode="Markdown"
            )

    elif data == "clear_goals":
        user["personal_goals"] = []
        await query.edit_message_text(
            "🗑 All goals cleared.

Send /goals to add new ones.",
            parse_mode="Markdown"
        )

    # ── Mark habit done ──
    elif data.startswith("done_"):
        pid = data.replace("done_", "")
        if pid in user["checked"]:
            return
        user["checked"][pid] = True
        done = len(user["checked"])
        total = len(user["today_pillars"])
        if done >= total:
            user["streak"] += 1
            try:
                msg = await ai_reminder_msg(user, "night")
            except:
                msg = f"All done. {user['streak']} days straight."
            await query.edit_message_text(
                f"🔥 *{done}/{total} — Day {user['streak']} complete!*\n\n_{msg}_",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"✅ *{done}/{total} done* — keep going!",
                parse_mode="Markdown",
                reply_markup=habit_select_keyboard(user)
            )

# ── FREE CHAT ────────────────────────────────────────────
async def generate_weekly_report(user):
    """AI generates a personal Sunday weekly report."""
    history = user.get("weekly_history", [])
    scores = user.get("scores", {})
    streak = user.get("streak", 0)
    name = user.get("name", "friend")
    goals = user.get("personal_goals", [])

    # Last 7 days
    last7 = history[-7:] if len(history) >= 7 else history
    days_checked = len(last7)
    total_habits = sum(len(r.get("pillars", [])) for r in last7)

    # Most done pillar
    pillar_count = {}
    day_count = {}
    for r in last7:
        for p in r.get("pillars", []):
            pillar_count[p] = pillar_count.get(p, 0) + 1
        dow = r.get("day_of_week", "")
        day_count[dow] = day_count.get(dow, 0) + 1

    top_pillar = max(pillar_count, key=pillar_count.get) if pillar_count else None
    best_day = max(day_count, key=day_count.get) if day_count else None
    weakest_pillar = min(scores, key=scores.get) if scores else None

    summary = (
        f"Days checked in: {days_checked}/7. "
        f"Total habits done: {total_habits}. "
        f"Streak: {streak} days. "
        f"Most focused pillar: {PILLARS[top_pillar]['name'] if top_pillar else 'N/A'}. "
        f"Best day: {best_day or 'N/A'}. "
        f"Weakest pillar score: {PILLARS[weakest_pillar]['name'] + ' (' + str(scores[weakest_pillar]) + '/5)' if weakest_pillar else 'N/A'}. "
        f"Personal goals: {', '.join(goals) if goals else 'none set'}."
    )

    try:
        system = (
            "You are a direct, honest habit coach writing a weekly review. "
            "Be personal, specific, and punchy. Like a coach debrief after a week. "
            "No fluff. Celebrate wins. Call out patterns honestly. Max 5 sentences."
        )
        prompt = (
            f"Write {name}'s weekly CoreSix report. Data: {summary}. "
            f"Cover: 1) What they did well 2) What needs work 3) One specific focus for next week. "
            f"Be honest and direct. Reference their actual data."
        )
        return await groq_async(prompt, system, max_tokens=250)
    except:
        return (
            f"Week done, {name}. {days_checked}/7 days checked in. "
            f"{total_habits} habits completed. "
            f"{'Strong week.' if days_checked >= 5 else 'Room to grow next week.'} "
            f"Keep showing up."
        )

async def send_weekly_report(context):
    """Scheduled Sunday job — sends weekly report to all active users."""
    for user_id, user in users.items():
        if user.get("step") == "active" and user.get("weekly_history"):
            try:
                report = await generate_weekly_report(user)
                history = user.get("weekly_history", [])
                last7 = history[-7:]
                days = len(last7)
                total = sum(len(r.get("pillars", [])) for r in last7)

                # Pillar breakdown
                pillar_count = {}
                for r in last7:
                    for p in r.get("pillars", []):
                        pillar_count[p] = pillar_count.get(p, 0) + 1
                pillar_lines = "
".join([
                    f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {c}x"
                    for p, c in sorted(pillar_count.items(), key=lambda x: -x[1])
                ])

                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"📊 *Weekly CoreSix Report*
"
                        f"_{datetime.now().strftime('%B %d, %Y')}_

"
                        f"*This week:*
"
                        f"✅ {days}/7 days · {total} habits done · 🔥 {user['streak']} streak

"
                        f"*Pillar breakdown:*
{pillar_lines}

"
                        f"*Coach says:*
_{report}_"
                    ),
                    parse_mode="Markdown"
                )
                # Save score snapshot
                if user.get("scores"):
                    user["score_history"].append({
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "scores": dict(user["scores"]),
                        "streak": user["streak"],
                        "days_checked": days,
                    })
                    user["score_history"] = user["score_history"][-12:]  # keep 12 weeks
            except Exception as e:
                print(f"Weekly report error for {user_id}: {e}")

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Manual weekly report command."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user.get("weekly_history"):
        await update.message.reply_text(
            "No data yet! Complete some habits first and come back on Sunday. 💪"
        )
        return
    await update.message.reply_text("📊 Generating your report...")
    report = await generate_weekly_report(user)
    history = user.get("weekly_history", [])
    last7 = history[-7:]
    days = len(last7)
    total = sum(len(r.get("pillars", [])) for r in last7)
    pillar_count = {}
    day_count = {}
    for r in last7:
        for p in r.get("pillars", []):
            pillar_count[p] = pillar_count.get(p, 0) + 1
        dow = r.get("day_of_week", "")
        day_count[dow] = day_count.get(dow, 0) + 1
    pillar_lines = "
".join([
        f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {c}x"
        for p, c in sorted(pillar_count.items(), key=lambda x: -x[1])
    ]) or "No data yet"
    best_day = max(day_count, key=day_count.get) if day_count else "N/A"
    await update.message.reply_text(
        f"📊 *Your Weekly Report*
"
        f"_{datetime.now().strftime('%B %d, %Y')}_

"
        f"*This week:*
"
        f"✅ {days}/7 days · {total} habits · 🔥 {user['streak']} streak
"
        f"🏆 Best day: {best_day}

"
        f"*Pillar breakdown:*
{pillar_lines}

"
        f"*Coach says:*
_{report}_",
        parse_mode="Markdown"
    )

async def cmd_goals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    goals = user.get("personal_goals", [])

    if goals:
        lines = "
".join([f"{i+1}. {g}" for i, g in enumerate(goals)])
        text = (
            f"🎯 *Your Personal Goals*

{lines}

"
            f"AI will weave these into your daily habits.

"
        )
    else:
        text = "🎯 *Your Personal Goals*

No goals set yet.

"

    await update.message.reply_text(
        text + "What would you like to do?",
        parse_mode="Markdown",
        reply_markup=goals_keyboard(goals)
    )

async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    # Handle goal adding
    if user.get("adding_goal"):
        goal = update.message.text.strip()
        if len(goal) > 5:
            goals = user.get("personal_goals", [])
            if len(goals) >= 5:
                await update.message.reply_text(
                    "You already have 5 goals. Send /goals to remove one first.",
                    parse_mode="Markdown"
                )
            else:
                goals.append(goal)
                user["personal_goals"] = goals
                user["adding_goal"] = False
                await update.message.reply_text(
                    f"✅ *Goal added:* _{goal}_

"
                    f"You now have {len(goals)} goal(s). AI will weave this into your daily habits.

"
                    f"Send /goals to manage all your goals.",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text("Please describe your goal in a bit more detail.")
        return

    # Handle time setting
    if user.get("setting_slot"):
        slot = user["setting_slot"]
        text = update.message.text.strip()
        try:
            hour, minute = map(int, text.split(":"))
            assert 0 <= hour <= 23 and 0 <= minute <= 59
            user["reminders"][slot] = f"{hour:02d}:{minute:02d}"
            user["setting_slot"] = None
            info = SLOTS[slot]
            await update.message.reply_text(
                f"✅ *{info['label']} set to {user['reminders'][slot]}*\n\n"
                f"Send /reminders to review or activate your schedule.",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text(
                "❌ Invalid format. Please send time as HH:MM\nExample: `08:30` or `21:00`",
                parse_mode="Markdown"
            )
        return

    # Normal chat
    scores_str = ", ".join([f"{PILLARS[k]['name']}:{v}/5" for k,v in user["scores"].items()]) or "not assessed"
    try:
        system = (
            f"You are a direct habit coach for {user['name'] or 'the user'}. "
            f"Streak: {user['streak']} days. Scores: {scores_str}. "
            f"Be short, punchy, personal. Like a coach texting. Max 2 sentences."
        )
        reply = await groq_async(update.message.text, system, max_tokens=100)
    except:
        reply = "Keep going. One habit at a time."
    await update.message.reply_text(f"_{reply}_", parse_mode="Markdown")

# ── MAIN ─────────────────────────────────────────────────
def main():
    import urllib.request, time
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        print("✅ Webhook cleared")
    except Exception as e:
        print(f"Webhook: {e}")
    print("⏳ Waiting 5s...")
    time.sleep(5)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("habit",     cmd_habit))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("assess",    cmd_assess))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("goals",     cmd_goals))
    app.add_handler(CommandHandler("report",    cmd_report))

    # Schedule Sunday 8am UTC weekly report
    app.job_queue.run_daily(
        send_weekly_report,
        time=time(hour=8, minute=0, tzinfo=pytz.UTC),
        days=(6,),  # Sunday
        name="weekly_report"
    )
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_chat))
    print("🤖 CoreSix bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
