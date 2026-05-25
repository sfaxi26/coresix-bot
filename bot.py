import os, random, asyncio, json, pytz
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

PILLARS = {
    "fuel":    {"name":"Fuel",    "emoji":"⚡", "desc":"Nutrition"},
    "move":    {"name":"Move",    "emoji":"💪", "desc":"Movement"},
    "rest":    {"name":"Rest",    "emoji":"😴", "desc":"Sleep & Recovery"},
    "calm":    {"name":"Calm",    "emoji":"🧘", "desc":"Stress Management"},
    "connect": {"name":"Connect", "emoji":"🤝", "desc":"Social Connection"},
    "focus":   {"name":"Focus",   "emoji":"🎯", "desc":"Purpose & Mindset"},
}
PIDS = list(PILLARS.keys())

FALLBACK = {
    "fuel":    ["Drink water before coffee","Add one vegetable to your next meal","Eat one meal without your phone"],
    "move":    ["5 push-ups before your shower","Walk around the block after lunch","Stretch 60 seconds now"],
    "rest":    ["Phone charger across the room tonight","4 deep breaths before sleep","Make your bed right after waking"],
    "calm":    ["3 breaths before opening any app","Write one thing you are grateful for","2 minutes silence with your morning drink"],
    "connect": ["One genuine message to a friend","Give someone a real compliment","Phone down during your next conversation"],
    "focus":   ["Write your one priority before email","Read one page before your phone","Notifications off for 30 minutes"],
}

SLOTS = {
    "morning":   {"label":"Morning",   "default":"07:00"},
    "midday":    {"label":"Midday",    "default":"12:00"},
    "afternoon": {"label":"Afternoon", "default":"16:00"},
    "night":     {"label":"Night",     "default":"21:00"},
}

users = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "name":"", "step":"welcome", "scores":{}, "streak":0,
            "today_pillars":[], "today_habits":{}, "checked":{},
            "timezone":"UTC",
            "reminders":{"morning":"07:00","midday":"12:00","afternoon":"16:00","night":"21:00"},
            "reminders_active":False, "setting_slot":None,
            "personal_goals":[], "adding_goal":False,
            "weekly_history":[], "score_history":[], "last_checkin_date":None,
        }
    return users[uid]

# ── GROQ ────────────────────────────────────────────────
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

async def ai_pick_pillars(user):
    scores = user["scores"]
    if not scores:
        return random.sample(PIDS, 3)
    try:
        result = await groq(
            f"Scores (1-5 lower=needs work): {json.dumps(scores)}. Streak: {user['streak']}. Pick best 3 pillar IDs for today. Balance weakness and variety. IDs: {PIDS}. Return ONLY: [\"id1\",\"id2\",\"id3\"]",
            "Habit coach. Return ONLY a JSON array of 3 pillar IDs. No explanation.",
            max_tokens=50
        )
        p = json.loads(result.strip())
        if isinstance(p, list) and len(p)==3 and all(x in PIDS for x in p):
            return p
    except Exception as e:
        print(f"pillar err: {e}")
    return random.sample(sorted(PIDS, key=lambda p: scores.get(p,3))[:4], 3)

async def ai_habits(user, pids):
    hour = datetime.now().hour
    tod = "morning" if hour<12 else "afternoon" if hour<17 else "evening"
    streak = user["streak"]
    level = "beginner" if streak<7 else "intermediate" if streak<21 else "advanced"
    goals = user.get("personal_goals",[])
    goals_str = f" Goals: {', '.join(goals)}." if goals else ""
    info = ", ".join([f"{PILLARS[p]['name']} ({user['scores'].get(p,'?')}/5)" for p in pids])
    try:
        result = await groq(
            f"3 tiny habits for {user['name'] or 'user'}, one per pillar: {info}. Time: {tod}. Level: {level}. Streak: {streak}.{goals_str} Under 2 min each. Weave goals in naturally. Fresh and specific. Return ONLY: {{\"{pids[0]}\":\"habit\",\"{pids[1]}\":\"habit\",\"{pids[2]}\":\"habit\"}}",
            "No-nonsense habit coach. Short punchy habits. Return ONLY valid JSON.",
            max_tokens=200
        )
        h = json.loads(result.strip().replace("```json","").replace("```",""))
        if all(p in h for p in pids):
            return h
    except Exception as e:
        print(f"habit err: {e}")
    return {p: random.choice(FALLBACK.get(p,["Do one small thing"])) for p in pids}

async def ai_msg(user, purpose):
    name = user["name"] or "champ"
    streak = user["streak"]
    done = len(user.get("checked",{}))
    total = len(user.get("today_pillars",[]))
    prompts = {
        "morning":   f"Morning message for {name}. Streak: {streak}. Punchy opener. 1 sentence.",
        "midday":    f"Midday nudge for {name}. Done {done}/{total} habits. 1 punchy sentence.",
        "afternoon": f"Afternoon push for {name}. Done {done}/{total}. 1 sentence.",
        "night":     f"Night wrap for {name}. Done {done}/{total}. Streak {streak}. Honest. 1-2 sentences.",
        "all_done":  f"{name} completed all {total} habits. Streak {streak}. Short celebration. Make it feel earned.",
        "start":     f"{name} just started CoreSix. One punchy welcome. Make them feel ready.",
    }
    try:
        return await groq(prompts.get(purpose, prompts["morning"]), "Direct habit coach. Short punchy texts. Max 2 sentences. No fluff.", max_tokens=80)
    except:
        defaults = {"morning":f"Morning {name}. Let's go.","midday":f"{done}/{total} done. Keep moving.","afternoon":f"Still time. {done}/{total} done.","night":f"Day done. {done}/{total} habits. {streak} streak.","all_done":f"All done. {streak} days straight.","start":f"Welcome {name}. One habit at a time."}
        return defaults.get(purpose,"Keep going.")

# ── WEEKLY REPORT ───────────────────────────────────────
async def weekly_report(user):
    h7 = user.get("weekly_history",[])[-7:]
    days = len(h7)
    total = sum(len(r.get("pillars",[])) for r in h7)
    pc = {}
    dc = {}
    for r in h7:
        for p in r.get("pillars",[]):
            pc[p] = pc.get(p,0)+1
        d = r.get("day_of_week","")
        dc[d] = dc.get(d,0)+1
    top = max(pc, key=pc.get) if pc else None
    best_day = max(dc, key=dc.get) if dc else "N/A"
    scores = user.get("scores",{})
    weak = min(scores, key=scores.get) if scores else None
    goals = user.get("personal_goals",[])
    summary = f"Days: {days}/7. Habits: {total}. Streak: {user['streak']}. Top pillar: {PILLARS[top]['name'] if top else 'N/A'}. Best day: {best_day}. Weakest: {PILLARS[weak]['name']+' '+str(scores[weak])+'/5' if weak else 'N/A'}. Goals: {', '.join(goals) if goals else 'none'}."
    try:
        return await groq(
            f"Weekly CoreSix report for {user['name'] or 'user'}. Data: {summary}. Cover: wins, what needs work, one focus for next week. Be honest and direct. Reference actual data.",
            "Direct honest habit coach writing weekly review. Like a coach debrief. Max 5 sentences. No fluff.",
            max_tokens=250
        )
    except:
        return f"Week done. {days}/7 days. {total} habits. {'Strong week.' if days>=5 else 'Room to grow.'} Keep showing up."

async def send_weekly_report(context):
    for uid, user in users.items():
        if user.get("step")=="active" and user.get("weekly_history"):
            try:
                h7 = user["weekly_history"][-7:]
                days = len(h7)
                total = sum(len(r.get("pillars",[])) for r in h7)
                pc = {}
                for r in h7:
                    for p in r.get("pillars",[]):
                        pc[p] = pc.get(p,0)+1
                breakdown = "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {c}x" for p,c in sorted(pc.items(),key=lambda x:-x[1])])
                report = await weekly_report(user)
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"Weekly CoreSix Report\n{datetime.now().strftime('%B %d, %Y')}\n\nThis week:\n{days}/7 days - {total} habits - {user['streak']} day streak\n\nPillar breakdown:\n{breakdown}\n\nCoach says:\n{report}",
                )
                if user.get("scores"):
                    user["score_history"].append({"date":datetime.now().strftime("%Y-%m-%d"),"scores":dict(user["scores"]),"streak":user["streak"],"days":days})
                    user["score_history"] = user["score_history"][-12:]
            except Exception as e:
                print(f"weekly err {uid}: {e}")

# ── REMINDER JOB ────────────────────────────────────────
async def send_reminder(context):
    uid = context.job.data["uid"]
    purpose = context.job.data["purpose"]
    user = get_user(uid)
    if not user["reminders_active"]:
        return
    if purpose == "morning":
        user["checked"] = {}
        pids = await ai_pick_pillars(user)
        habits = await ai_habits(user, pids)
        user["today_pillars"] = pids
        user["today_habits"] = habits
    msg = await ai_msg(user, purpose)
    icons = {"morning":"Morning","midday":"Midday","afternoon":"Afternoon","night":"Night"}
    try:
        if purpose == "morning" and user["today_pillars"]:
            lines = [f"{icons[purpose]} - {msg}\n"]
            for p in user["today_pillars"]:
                lines.append(f"{PILLARS[p]['emoji']} {PILLARS[p]['name']} - {user['today_habits'].get(p,'')}")
            lines.append("\nTap each when done")
            text = "\n".join(lines)
            kb = habit_kb(user)
        else:
            text = f"{icons[purpose]}: {msg}"
            kb = habit_kb(user) if user["today_pillars"] else None
        await context.bot.send_message(chat_id=uid, text=text, reply_markup=kb)
    except Exception as e:
        print(f"reminder err: {e}")

def schedule_reminders(app, uid):
    user = get_user(uid)
    try:
        tz = pytz.timezone(user.get("timezone","UTC"))
    except:
        tz = pytz.UTC
    for job in app.job_queue.get_jobs_by_name(str(uid)):
        job.schedule_removal()
    if not user["reminders_active"]:
        return
    for slot, info in SLOTS.items():
        t_str = user["reminders"].get(slot, info["default"])
        try:
            h, m = map(int, t_str.split(":"))
            app.job_queue.run_daily(send_reminder, time=time(hour=h, minute=m, tzinfo=tz), name=str(uid), data={"uid":uid,"purpose":slot})
        except Exception as e:
            print(f"schedule err {slot}: {e}")

# ── KEYBOARDS ────────────────────────────────────────────
def habit_kb(user):
    btns = []
    for p in user.get("today_pillars",[]):
        done = p in user.get("checked",{})
        label = f"Done {PILLARS[p]['emoji']} {PILLARS[p]['name']}" if done else f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}"
        btns.append([InlineKeyboardButton(label, callback_data=f"done_{p}")])
    return InlineKeyboardMarkup(btns) if btns else None

def reminders_kb(user):
    btns = [[InlineKeyboardButton(f"{SLOTS[s]['label']} - {user['reminders'].get(s,SLOTS[s]['default'])}", callback_data=f"setslot_{s}")] for s in SLOTS]
    status = "ON" if user["reminders_active"] else "OFF"
    btns.append([InlineKeyboardButton(f"Reminders: {status} - tap to toggle", callback_data="toggle_reminders")])
    btns.append([InlineKeyboardButton("Save and Activate", callback_data="save_reminders")])
    return InlineKeyboardMarkup(btns)

def goals_kb(goals):
    btns = [[InlineKeyboardButton(f"Remove: {g[:35]}", callback_data=f"rmgoal_{i}")] for i,g in enumerate(goals)]
    btns.append([InlineKeyboardButton("Add a goal", callback_data="add_goal")])
    if goals:
        btns.append([InlineKeyboardButton("Clear all goals", callback_data="clear_goals")])
    return InlineKeyboardMarkup(btns)

def score_kb(pid):
    return InlineKeyboardMarkup([[InlineKeyboardButton(str(n), callback_data=f"score_{pid}_{n}") for n in range(1,6)]])

# ── COMMANDS ────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    user["name"] = update.effective_user.first_name or "Hero"
    user["step"] = "welcome"
    msg = await ai_msg(user, "start")
    await update.message.reply_text(
        f"CoreSix - 6 pillars. 3 habits. Every day.\n\n{msg}\n\n"
        "Fuel - Move - Rest - Calm - Connect - Focus\n\n"
        "Add personal goals and I build habits around them.\n"
        "I send reminders 4x a day automatically.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Set My Reminders", callback_data="show_reminders")],
            [InlineKeyboardButton("Add Personal Goals", callback_data="add_goal")],
            [InlineKeyboardButton("Quick Assessment", callback_data="assess")],
            [InlineKeyboardButton("Skip - Start Now", callback_data="skip_assess")],
        ])
    )

async def cmd_habit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    await update.message.reply_text("Picking your habits...")
    user["checked"] = {}
    pids = await ai_pick_pillars(user)
    habits = await ai_habits(user, pids)
    user["today_pillars"] = pids
    user["today_habits"] = habits
    lines = ["Your 3 Habits Today\n"]
    for p in pids:
        lines.append(f"{PILLARS[p]['emoji']} {PILLARS[p]['name']} - {habits.get(p,'')}")
    lines.append("\nTap each when done")
    await update.message.reply_text("\n".join(lines), reply_markup=habit_kb(user))

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    scores = user["scores"]
    sc = "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {scores.get(p,'?')}/5" for p in PIDS]) if scores else "Not assessed - send /assess"
    rem = "\n".join([f"{SLOTS[s]['label']}: {user['reminders'].get(s)}" for s in SLOTS])
    goals = user.get("personal_goals",[])
    gtext = "\n".join([f"- {g}" for g in goals]) if goals else "None set"
    await update.message.reply_text(
        f"CoreSix - {user['name']}\n\n"
        f"Streak: {user['streak']} days\n"
        f"Today: {len(user.get('checked',{}))}/{len(user.get('today_pillars',[]))} done\n\n"
        f"Scores:\n{sc}\n\n"
        f"Goals:\n{gtext}\n\n"
        f"Reminders ({'ON' if user['reminders_active'] else 'OFF'}):\n{rem}"
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
    text = "Your Personal Goals\n\n"
    if goals:
        text += "\n".join([f"{i+1}. {g}" for i,g in enumerate(goals)])
        text += "\n\nAI weaves these into your daily habits."
    else:
        text += "No goals set yet."
    await update.message.reply_text(text, reply_markup=goals_kb(goals))

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user.get("weekly_history"):
        await update.message.reply_text("No data yet. Complete some habits first then come back.")
        return
    await update.message.reply_text("Generating your report...")
    h7 = user["weekly_history"][-7:]
    days = len(h7)
    total = sum(len(r.get("pillars",[])) for r in h7)
    pc = {}
    dc = {}
    for r in h7:
        for p in r.get("pillars",[]):
            pc[p] = pc.get(p,0)+1
        dc[r.get("day_of_week","")] = dc.get(r.get("day_of_week",""),0)+1
    breakdown = "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {c}x" for p,c in sorted(pc.items(),key=lambda x:-x[1])]) or "No data"
    best_day = max(dc, key=dc.get) if dc else "N/A"
    report = await weekly_report(user)
    await update.message.reply_text(
        f"Weekly Report - {datetime.now().strftime('%B %d, %Y')}\n\n"
        f"{days}/7 days - {total} habits - {user['streak']} streak\n"
        f"Best day: {best_day}\n\n"
        f"Pillar breakdown:\n{breakdown}\n\n"
        f"Coach says:\n{report}"
    )

# ── CALLBACKS ────────────────────────────────────────────
async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    data = q.data

    if data == "show_reminders":
        await q.edit_message_text("Set Your Daily Reminders\nTap a time to change it.", reply_markup=reminders_kb(user))

    elif data == "toggle_reminders":
        user["reminders_active"] = not user["reminders_active"]
        await q.edit_message_text("Your Reminder Schedule\nTap a time to change it:", reply_markup=reminders_kb(user))

    elif data == "save_reminders":
        user["reminders_active"] = True
        schedule_reminders(ctx.application, uid)
        lines = "\n".join([f"{SLOTS[s]['label']}: {user['reminders'].get(s)}" for s in SLOTS])
        await q.edit_message_text(f"Reminders activated!\n\n{lines}\n\nI will reach out 4 times a day. Send /habit anytime.")

    elif data.startswith("setslot_"):
        slot = data.replace("setslot_","")
        user["setting_slot"] = slot
        current = user["reminders"].get(slot, SLOTS[slot]["default"])
        await q.edit_message_text(f"Change {SLOTS[slot]['label']} reminder\n\nCurrent: {current}\n\nReply with time in HH:MM format\nExample: 08:30 or 21:00")

    elif data == "add_goal":
        user["adding_goal"] = True
        await q.edit_message_text(
            "Add a Personal Goal\n\n"
            "Tell me what you want to focus on. Examples:\n"
            "- Drink more water\n"
            "- Eat more protein\n"
            "- Sleep before midnight\n"
            "- Reduce screen time\n"
            "- Walk 10000 steps\n"
            "- Eat more fibre\n\n"
            "Just type your goal below"
        )

    elif data.startswith("rmgoal_"):
        idx = int(data.replace("rmgoal_",""))
        goals = user.get("personal_goals",[])
        if 0 <= idx < len(goals):
            removed = goals.pop(idx)
            user["personal_goals"] = goals
            await q.edit_message_text(f"Removed: {removed}\n\nSend /goals to manage your goals.")

    elif data == "clear_goals":
        user["personal_goals"] = []
        await q.edit_message_text("All goals cleared. Send /goals to add new ones.")

    elif data == "assess":
        user["step"] = "assess"
        user["scores"] = {}
        p = PILLARS[PIDS[0]]
        await q.edit_message_text(f"Rate each pillar 1-5.\n1 = struggling - 5 = thriving\n\n{p['emoji']} {p['name']} - {p['desc']}", reply_markup=score_kb(PIDS[0]))

    elif data == "skip_assess":
        user["step"] = "active"
        await q.edit_message_text("Got it. Send /habit to get your 3 habits now. Or send /reminders to set up your schedule.")

    elif data.startswith("score_"):
        _, pid, score = data.split("_")
        user["scores"][pid] = int(score)
        scored = list(user["scores"].keys())
        remaining = [p for p in PIDS if p not in scored]
        if remaining:
            p = PILLARS[remaining[0]]
            await q.edit_message_text(f"{len(scored)}/6 rated\n\n{p['emoji']} {p['name']} - {p['desc']}", reply_markup=score_kb(remaining[0]))
        else:
            user["step"] = "active"
            ranked = sorted(PIDS, key=lambda p: user["scores"].get(p,3))
            lines = [f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {user['scores'][p]}/5" for p in ranked]
            await q.edit_message_text("Assessment done!\n\nYour pillars:\n" + "\n".join(lines) + "\n\nAI picks your best 3 daily. Send /reminders to set up your schedule.")

    elif data.startswith("done_"):
        pid = data.replace("done_","")
        if pid in user["checked"]:
            return
        user["checked"][pid] = True
        done = len(user["checked"])
        total = len(user["today_pillars"])
        if done >= total:
            user["streak"] += 1
            today = datetime.now().strftime("%Y-%m-%d")
            user["last_checkin_date"] = today
            user["weekly_history"].append({
                "date": today,
                "day_of_week": datetime.now().strftime("%A"),
                "pillars": user["today_pillars"],
                "habits": user["today_habits"],
                "streak": user["streak"],
            })
            user["weekly_history"] = user["weekly_history"][-30:]
            msg = await ai_msg(user, "all_done")
            await q.edit_message_text(f"{done}/{total} done - Day {user['streak']} complete!\n\n{msg}")
        else:
            await q.edit_message_text(f"{done}/{total} done - keep going!", reply_markup=habit_kb(user))

# ── CHAT ─────────────────────────────────────────────────
async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    text = update.message.text

    if user.get("setting_slot"):
        slot = user["setting_slot"]
        try:
            h, m = map(int, text.strip().split(":"))
            assert 0 <= h <= 23 and 0 <= m <= 59
            user["reminders"][slot] = f"{h:02d}:{m:02d}"
            user["setting_slot"] = None
            await update.message.reply_text(f"{SLOTS[slot]['label']} set to {user['reminders'][slot]}\n\nSend /reminders to review or activate.")
        except:
            await update.message.reply_text("Invalid format. Please send as HH:MM - example: 08:30")
        return

    if user.get("adding_goal"):
        goal = text.strip()
        if len(goal) > 5:
            goals = user.get("personal_goals",[])
            if len(goals) >= 5:
                await update.message.reply_text("You have 5 goals already. Send /goals to remove one first.")
            else:
                goals.append(goal)
                user["personal_goals"] = goals
                user["adding_goal"] = False
                await update.message.reply_text(f"Goal added: {goal}\n\nYou now have {len(goals)} goal(s). AI will weave this into your daily habits.")
        else:
            await update.message.reply_text("Please describe your goal in a bit more detail.")
        return

    scores_str = ", ".join([f"{PILLARS[k]['name']}:{v}/5" for k,v in user["scores"].items()]) or "not assessed"
    try:
        reply = await groq(
            text,
            f"Direct habit coach for {user['name'] or 'user'}. Streak: {user['streak']}. Scores: {scores_str}. Short punchy texts. Max 2 sentences.",
            max_tokens=100
        )
    except:
        reply = "Keep going. One habit at a time."
    await update.message.reply_text(reply)

# ── MAIN ─────────────────────────────────────────────────
def main():
    import urllib.request, time as _time
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        print("Webhook cleared")
    except Exception as e:
        print(f"Webhook: {e}")
    print("Waiting 5s...")
    _time.sleep(5)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("habit",     cmd_habit))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("assess",    cmd_assess))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("goals",     cmd_goals))
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(CallbackQueryHandler(handle_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_chat))

    # Sunday 8am UTC weekly report
    app.job_queue.run_daily(send_weekly_report, time=time(hour=8, minute=0, tzinfo=pytz.UTC), days=(6,), name="weekly_report")

    print("CoreSix bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
