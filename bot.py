import os, random, asyncio, json, pytz
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
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
        users = {}
    except Exception as e:
        print(f"Load error: {e}")
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
            "personal_goals":[], "adding_goal":False, "onboarding":None,
            "weekly_history":[], "score_history":[], "last_checkin_date":None,
            "mood":None, "mood_date":None, "last_active_date":None,
            "missed_days_alerted":False, "pattern_sent_week":None,
            "profile":{
                "age":None, "sex":None, "fitness":None,
                "conditions":[], "medications":[],
                "sleep_quality":None, "stress_level":None,
            },
            "profile_step":None,
            "macro_log":[],  # list of daily macro entries
        }
    return users[uid]

# ── GROQ AI ──────────────────────────────────────────────
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
            "Habit coach. Return ONLY a JSON array of 3 pillar IDs. No explanation.", max_tokens=50
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
    mood = user.get("mood")
    mood_str = f" Mood today: {mood}." if mood else ""

    # Build health profile context
    profile = user.get("profile", {})
    parts = []
    if profile.get("age"): parts.append(f"Age {profile['age']}")
    if profile.get("sex"): parts.append(f"Sex: {profile['sex']}")
    if profile.get("fitness"): parts.append(f"Fitness: {profile['fitness']}")
    if profile.get("conditions"): parts.append(f"Conditions: {', '.join(profile['conditions'])}")
    if profile.get("medications"): parts.append(f"Medications: {', '.join(profile['medications'])}")
    if profile.get("sleep_quality"): parts.append(f"Sleep: {profile['sleep_quality']}")
    if profile.get("stress_level"): parts.append(f"Stress: {profile['stress_level']}")
    profile_str = f" Health profile: {'. '.join(parts)}." if parts else ""

    try:
        result = await groq(
            f"3 tiny habits for {user['name'] or 'user'}, one per pillar: {info}. "
            f"Time: {tod}. Level: {level}. Streak: {streak}.{goals_str}{mood_str}{profile_str} "
            f"CRITICAL: Adapt every habit to their health profile, age, conditions and medications. "
            f"Under 2 min each. Safe, specific, personalised. "
            f"Return ONLY: {{\"{pids[0]}\":\"habit\",\"{pids[1]}\":\"habit\",\"{pids[2]}\":\"habit\"}}",
            "Evidence-based habit coach. Adapt to age, sex, medical conditions and medications. Safe personalised habits. Return ONLY valid JSON.",
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

# ── WEEKLY REPORT ────────────────────────────────────────
async def weekly_report(user):
    h7 = user.get("weekly_history",[])[-7:]
    days = len(h7)
    total = sum(len(r.get("pillars",[])) for r in h7)
    pc = {}
    dc = {}
    for r in h7:
        for p in r.get("pillars",[]): pc[p] = pc.get(p,0)+1
        dc[r.get("day_of_week","")] = dc.get(r.get("day_of_week",""),0)+1
    top = max(pc, key=pc.get) if pc else None
    best_day = max(dc, key=dc.get) if dc else "N/A"
    scores = user.get("scores",{})
    weak = min(scores, key=scores.get) if scores else None
    goals = user.get("personal_goals",[])
    summary = f"Days: {days}/7. Habits: {total}. Streak: {user['streak']}. Top pillar: {PILLARS[top]['name'] if top else 'N/A'}. Best day: {best_day}. Weakest: {PILLARS[weak]['name']+' '+str(scores[weak])+'/5' if weak else 'N/A'}. Goals: {', '.join(goals) if goals else 'none'}."
    try:
        return await groq(
            f"Weekly CoreSix report for {user['name'] or 'user'}. Data: {summary}. Cover: wins, what needs work, one focus for next week. Honest and direct.",
            "Direct honest habit coach. Weekly review like a coach debrief. Max 5 sentences. No fluff.", max_tokens=250
        )
    except:
        return f"Week done. {days}/7 days. {total} habits. Keep showing up."

async def send_weekly_report(context):
    for uid, user in users.items():
        if user.get("step")!="active" or not user.get("weekly_history"): continue
        try:
            h7 = user["weekly_history"][-7:]
            days = len(h7)
            total = sum(len(r.get("pillars",[])) for r in h7)
            pc = {}
            for r in h7:
                for p in r.get("pillars",[]): pc[p] = pc.get(p,0)+1
            breakdown = "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {c}x" for p,c in sorted(pc.items(),key=lambda x:-x[1])])
            report = await weekly_report(user)
            await context.bot.send_message(chat_id=uid, text=f"Weekly CoreSix Report\n{datetime.now().strftime('%B %d, %Y')}\n\n{days}/7 days - {total} habits - {user['streak']} streak\n\nPillar breakdown:\n{breakdown}\n\nCoach says:\n{report}")
            if user.get("scores"):
                user["score_history"].append({"date":datetime.now().strftime("%Y-%m-%d"),"scores":dict(user["scores"]),"streak":user["streak"],"days":days})
                user["score_history"] = user["score_history"][-12:]
                save_users()
        except Exception as e:
            print(f"weekly err {uid}: {e}")

# ── MOOD CHECK-IN ────────────────────────────────────────
async def send_mood_checkin(context):
    for uid, user in users.items():
        if user.get("step")!="active": continue
        today = datetime.now().strftime("%Y-%m-%d")
        if user.get("mood_date")==today: continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"How are you feeling today, {user['name'] or 'champ'}?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Energised", callback_data="mood_high"), InlineKeyboardButton("Good", callback_data="mood_medium")],
                    [InlineKeyboardButton("Tired", callback_data="mood_low"), InlineKeyboardButton("Struggling", callback_data="mood_very_low")],
                ])
            )
        except Exception as e:
            print(f"mood err {uid}: {e}")

# ── MISSED DAYS ──────────────────────────────────────────
async def check_missed_days(context):
    today_dt = datetime.now()
    for uid, user in users.items():
        if user.get("step")!="active": continue
        last = user.get("last_active_date")
        if not last: continue
        try:
            days_missed = (today_dt - datetime.strptime(last, "%Y-%m-%d")).days
            if days_missed >= 2 and not user.get("missed_days_alerted"):
                user["missed_days_alerted"] = True
                name = user["name"] or "champ"
                try:
                    msg = await groq(f"{name} missed {days_missed} days. Streak was {user['streak']}. Personal direct message to bring them back. Reference their streak. 2 sentences max.", "Direct habit coach. Personal outreach. No guilt. Real talk. Max 2 sentences.")
                except:
                    msg = f"{days_missed} days gone, {name}. Your {user['streak']}-day streak is waiting — one habit today brings it back."
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"{msg}\n\nSend /habit to get back on track.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Get Today's Habits", callback_data="get_habits_now")]])
                )
                save_users()
        except Exception as e:
            print(f"missed days err {uid}: {e}")

# ── PATTERN DETECTION ────────────────────────────────────
async def detect_patterns(context):
    for uid, user in users.items():
        if user.get("step")!="active" or len(user.get("weekly_history",[]))<7: continue
        week_str = datetime.now().strftime("%Y-W%W")
        if user.get("pattern_sent_week")==week_str: continue
        try:
            history = user["weekly_history"][-14:]
            day_count = {}
            pillar_count = {}
            for r in history:
                d = r.get("day_of_week","")
                day_count[d] = day_count.get(d,0)+1
                for p in r.get("pillars",[]): pillar_count[p] = pillar_count.get(p,0)+1
            all_days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            weakest_day = min(all_days, key=lambda d: day_count.get(d,0))
            strongest_day = max(day_count, key=day_count.get) if day_count else "N/A"
            least_pillar = min(pillar_count, key=pillar_count.get) if pillar_count else None
            most_pillar = max(pillar_count, key=pillar_count.get) if pillar_count else None
            summary = f"Weakest day: {weakest_day} ({day_count.get(weakest_day,0)} check-ins). Strongest: {strongest_day}. Most done: {PILLARS[most_pillar]['name'] if most_pillar else 'N/A'}. Least done: {PILLARS[least_pillar]['name'] if least_pillar else 'N/A'}."
            name = user["name"] or "champ"
            try:
                pattern_msg = await groq(f"Pattern analysis for {name}: {summary}. Write 2-3 punchy insights. Tell them WHY they might struggle on {weakest_day} and what to do.", "Direct habit coach spotting patterns. Punchy specific insights. Max 3 sentences.")
            except:
                pattern_msg = f"You show up most on {strongest_day} and least on {weakest_day}. {PILLARS[least_pillar]['name'] if least_pillar else 'One pillar'} keeps getting skipped. Fix: do it first thing on {weakest_day}."
            await context.bot.send_message(chat_id=uid, text=f"Pattern detected, {name}.\n\n{pattern_msg}\n\nSend /status to see your full breakdown.")
            user["pattern_sent_week"] = week_str
            save_users()
        except Exception as e:
            print(f"pattern err {uid}: {e}")

# ── REMINDER JOB ─────────────────────────────────────────
async def send_reminder(context):
    uid = context.job.data["uid"]
    purpose = context.job.data["purpose"]
    user = get_user(uid)
    if not user["reminders_active"]: return
    if purpose=="morning":
        user["checked"] = {}
        pids = await ai_pick_pillars(user)
        habits = await ai_habits(user, pids)
        user["today_pillars"] = pids
        user["today_habits"] = habits
    msg = await ai_msg(user, purpose)
    icons = {"morning":"Morning","midday":"Midday","afternoon":"Afternoon","night":"Night"}
    try:
        if purpose=="morning" and user["today_pillars"]:
            lines = [f"{icons[purpose]} - {msg}\n"]
            for p in user["today_pillars"]:
                lines.append(f"{PILLARS[p]['emoji']} {PILLARS[p]['name']} - {user['today_habits'].get(p,'')}")
            lines.append("\nTap each when done")
            await context.bot.send_message(chat_id=uid, text="\n".join(lines), reply_markup=habit_kb(user))
        else:
            await context.bot.send_message(chat_id=uid, text=f"{icons[purpose]}: {msg}", reply_markup=habit_kb(user) if user["today_pillars"] else None)
    except Exception as e:
        print(f"reminder err: {e}")

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
            print(f"schedule err {slot}: {e}")

# ── KEYBOARDS ────────────────────────────────────────────
def habit_kb(user):
    btns = []
    for p in user.get("today_pillars",[]):
        done = p in user.get("checked",{})
        label = f"Done {PILLARS[p]['emoji']} {PILLARS[p]['name']}" if done else f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}"
        btns.append([InlineKeyboardButton(label, callback_data=f"done_{p}")])
    return InlineKeyboardMarkup(btns) if btns else None

TIMEZONES = {
    # Americas
    "New York (EST)":     "America/New_York",
    "Chicago (CST)":      "America/Chicago",
    "Denver (MST)":       "America/Denver",
    "Los Angeles (PST)":  "America/Los_Angeles",
    "Toronto":            "America/Toronto",
    "Mexico City":        "America/Mexico_City",
    "Sao Paulo":          "America/Sao_Paulo",
    # Europe
    "London (GMT)":       "Europe/London",
    "Paris (CET)":        "Europe/Paris",
    "Berlin":             "Europe/Berlin",
    "Madrid":             "Europe/Madrid",
    "Rome":               "Europe/Rome",
    "Amsterdam":          "Europe/Amsterdam",
    "Stockholm":          "Europe/Stockholm",
    # Middle East & Africa
    "Dubai (GST)":        "Asia/Dubai",
    "Riyadh":             "Asia/Riyadh",
    "Cairo":              "Africa/Cairo",
    "Istanbul":           "Europe/Istanbul",
    "Tel Aviv":           "Asia/Jerusalem",
    "Nairobi":            "Africa/Nairobi",
    # Asia & Pacific
    "Mumbai (IST)":       "Asia/Kolkata",
    "Singapore":          "Asia/Singapore",
    "Hong Kong":          "Asia/Hong_Kong",
    "Tokyo":              "Asia/Tokyo",
    "Sydney":             "Australia/Sydney",
    "Auckland":           "Pacific/Auckland",
}

TZ_REGIONS = {
    "Americas":       ["New York (EST)","Chicago (CST)","Denver (MST)","Los Angeles (PST)","Toronto","Mexico City","Sao Paulo"],
    "Europe":         ["London (GMT)","Paris (CET)","Berlin","Madrid","Rome","Amsterdam","Stockholm"],
    "Middle East":    ["Dubai (GST)","Riyadh","Cairo","Istanbul","Tel Aviv","Nairobi"],
    "Asia & Pacific": ["Mumbai (IST)","Singapore","Hong Kong","Tokyo","Sydney","Auckland"],
}

def tz_region_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(region, callback_data=f"tz_region_{region}")]
        for region in TZ_REGIONS
    ])

def tz_city_kb(region):
    cities = TZ_REGIONS.get(region, [])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(city, callback_data=f"tz_set_{city}")]
        for city in cities
    ])

def reminders_kb(user):
    btns = [[InlineKeyboardButton(f"{SLOTS[s]['label']} - {user['reminders'].get(s,SLOTS[s]['default'])}", callback_data=f"setslot_{s}")] for s in SLOTS]
    status = "ON" if user["reminders_active"] else "OFF"
    btns.append([InlineKeyboardButton(f"Reminders: {status} - tap to toggle", callback_data="toggle_reminders")])
    btns.append([InlineKeyboardButton("Save and Activate", callback_data="save_reminders")])
    return InlineKeyboardMarkup(btns)

def goals_kb(goals):
    btns = [[InlineKeyboardButton(f"Remove: {g[:35]}", callback_data=f"rmgoal_{i}")] for i,g in enumerate(goals)]
    btns.append([InlineKeyboardButton("Add a goal", callback_data="add_goal")])
    if goals: btns.append([InlineKeyboardButton("Clear all goals", callback_data="clear_goals")])
    return InlineKeyboardMarkup(btns)

def score_kb(pid):
    return InlineKeyboardMarkup([[InlineKeyboardButton(str(n), callback_data=f"score_{pid}_{n}") for n in range(1,6)]])

# ── FOOD PHOTO ANALYSIS ─────────────────────────────────
async def analyse_food_photo(image_bytes, mime_type="image/jpeg"):
    """Send food photo to Gemini Vision and get macro breakdown."""
    import httpx, base64
    if not GEMINI_API_KEY:
        return None
    b64 = base64.b64encode(image_bytes).decode()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
                json={
                    "contents": [{
                        "parts": [
                            {"inline_data": {"mime_type": mime_type, "data": b64}},
                            {"text": (
                                "Analyse this food photo and estimate the macronutrients. "
                                "Identify each food item visible. Estimate realistic portion sizes. "
                                "Return ONLY valid JSON, no markdown: "
                                '{"foods":["food1"],"calories":0,"protein_g":0,"carbs_g":0,"fat_g":0,"fibre_g":0,"confidence":"high/medium/low","notes":"notes"}'
                            )}
                        ]
                    }],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500}
                }
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            clean = text.strip().replace("```json","").replace("```","").strip()
            return json.loads(clean)
    except Exception as e:
        print(f"Gemini error: {e}")
        return None

async def handle_food_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages — analyse food and calculate macros."""
    uid = update.effective_user.id
    user = get_user(uid)

    if not GEMINI_API_KEY:
        await update.message.reply_text(
            "Food photo analysis not set up yet.\n\nAdd GEMINI_API_KEY to Railway Variables to enable this feature."
        )
        return

    await update.message.reply_text("Analysing your meal... give me a moment!")

    try:
        # Get the largest photo size
        photo = update.message.photo[-1]
        file = await ctx.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        result = await analyse_food_photo(bytes(image_bytes))

        if not result:
            await update.message.reply_text(
                "Could not analyse this photo. Try a clearer photo with better lighting."
            )
            return

        foods = result.get("foods", [])
        calories = result.get("calories", 0)
        protein = result.get("protein_g", 0)
        carbs = result.get("carbs_g", 0)
        fat = result.get("fat_g", 0)
        fibre = result.get("fibre_g", 0)
        confidence = result.get("confidence", "medium")
        notes = result.get("notes", "")

        # Log to user's macro history
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M"),
            "foods": foods,
            "calories": calories,
            "protein_g": protein,
            "carbs_g": carbs,
            "fat_g": fat,
            "fibre_g": fibre,
        }
        user["macro_log"].append(entry)
        user["macro_log"] = user["macro_log"][-30:]  # keep 30 days
        save_users()

        # Calculate today's totals
        today = datetime.now().strftime("%Y-%m-%d")
        today_entries = [e for e in user["macro_log"] if e["date"] == today]
        total_cal = sum(e["calories"] for e in today_entries)
        total_protein = sum(e["protein_g"] for e in today_entries)
        total_carbs = sum(e["carbs_g"] for e in today_entries)
        total_fat = sum(e["fat_g"] for e in today_entries)
        total_fibre = sum(e["fibre_g"] for e in today_entries)

        conf_emoji = "✅" if confidence=="high" else "⚠️" if confidence=="medium" else "❓"

        msg = (
            f"Meal Analysis {conf_emoji}\n\n"
            f"Foods: {', '.join(foods)}\n\n"
            f"This meal:\n"
            f"Calories: {calories} kcal\n"
            f"Protein: {protein}g\n"
            f"Carbs: {carbs}g\n"
            f"Fat: {fat}g\n"
            f"Fibre: {fibre}g"
        )

        if notes:
            msg += f"\n\nNote: {notes}"

        if len(today_entries) > 1:
            msg += (
                f"\n\nToday total ({len(today_entries)} meals):\n"
                f"Calories: {total_cal} kcal | Protein: {total_protein}g | Carbs: {total_carbs}g | Fat: {total_fat}g"
            )


        # AI coaching tip based on macros and user goals
        goals = user.get("personal_goals", [])
        profile = user.get("profile", {})
        try:
            tip = await groq(
                f"User ate: {', '.join(foods)}. Macros: {protein}g protein, {carbs}g carbs, {fat}g fat, {calories}kcal. "
                f"Their goals: {', '.join(goals) if goals else 'none'}. "
                f"Profile: age {profile.get('age','?')}, conditions: {', '.join(profile.get('conditions',[]))}. "
                f"Give one specific, actionable nutrition tip based on this meal. Max 2 sentences.",
                "Evidence-based nutrition coach. Short punchy advice. Reference actual foods eaten.",
                max_tokens=80
            )
            if tip:
                msg += f"\n\nCoach tip: {tip}"
        except:
            pass

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("View Today's Nutrition", callback_data="view_macros")],
            [InlineKeyboardButton("Log Another Meal", callback_data="prompt_photo")],
        ]))

    except Exception as e:
        print(f"Photo handler error: {e}")
        await update.message.reply_text(
            "Something went wrong analysing the photo. Try again with a clearer image."
        )

# ── COMMANDS ─────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    user["name"] = update.effective_user.first_name or "Hero"
    user["step"] = "welcome"
    user["onboarding"] = "goals"
    user["personal_goals"] = []
    user["adding_goal"] = True
    await update.message.reply_text(
        f"CoreSix - 6 pillars. 3 habits. Every day.\n\nWelcome {user['name']}. Let me set you up.\n\nStep 1 of 4 - Personal Goals\n\nWhat do you want to focus on? Examples:\n- Drink more water\n- Eat more protein\n- Sleep earlier\n- Reduce screen time\n\nType your first goal or tap Skip.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip Goals", callback_data="onboard_skip_goals")]])
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
    user["last_active_date"] = datetime.now().strftime("%Y-%m-%d")
    user["missed_days_alerted"] = False
    save_users()
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
    profile = user.get("profile",{})
    ptext = f"Age: {profile.get('age','?')} | Sex: {profile.get('sex','?')} | Fitness: {profile.get('fitness','?')}"
    await update.message.reply_text(
        f"CoreSix - {user['name']}\n\nStreak: {user['streak']} days\nToday: {len(user.get('checked',{}))}/{len(user.get('today_pillars',[]))} done\n\nScores:\n{sc}\n\nGoals:\n{gtext}\n\nProfile: {ptext}\n\nReminders ({'ON' if user['reminders_active'] else 'OFF'}):\n{rem}"
    )

async def cmd_assess(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    user["step"] = "assess"
    user["scores"] = {}
    p = PILLARS[PIDS[0]]
    await update.message.reply_text(f"Rate each pillar 1-5.\n1 = struggling - 5 = thriving\n\n{p['emoji']} {p['name']} - {p['desc']}", reply_markup=score_kb(PIDS[0]))

async def cmd_timezone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    current = user.get("timezone","UTC")
    await update.message.reply_text(
        f"Your timezone: {current}\n\nChange it by picking your region:",
        reply_markup=tz_region_kb()
    )


async def cmd_reminders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    await update.message.reply_text("Your Reminder Schedule\nTap a time to change it:", reply_markup=reminders_kb(user))

async def cmd_goals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    goals = user.get("personal_goals",[])
    text = "Your Personal Goals\n\n" + ("\n".join([f"{i+1}. {g}" for i,g in enumerate(goals)]) + "\n\nAI weaves these into your daily habits." if goals else "No goals set yet.")
    await update.message.reply_text(text, reply_markup=goals_kb(goals))

async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    profile = user.get("profile",{})
    lines = [
        "Your Health Profile\n",
        f"Age: {profile.get('age') or 'Not set'}",
        f"Sex: {profile.get('sex') or 'Not set'}",
        f"Fitness level: {profile.get('fitness') or 'Not set'}",
        f"Conditions: {', '.join(profile.get('conditions',[])) or 'None'}",
        f"Medications: {', '.join(profile.get('medications',[])) or 'None'}",
        f"Sleep quality: {profile.get('sleep_quality') or 'Not set'}",
        f"Stress level: {profile.get('stress_level') or 'Not set'}",
        "\nAI uses this to personalise every habit for you.",
    ]
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Update Profile", callback_data="profile_start")],
            [InlineKeyboardButton("Clear Profile", callback_data="profile_clear")],
        ])
    )

async def cmd_macros(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show today's macro summary."""
    uid = update.effective_user.id
    user = get_user(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    today_entries = [e for e in user.get("macro_log",[]) if e["date"]==today]

    if not today_entries:
        await update.message.reply_text("No meals logged today. Send a photo of your food to log it!")
        return

    total_cal = sum(e["calories"] for e in today_entries)
    total_protein = sum(e["protein_g"] for e in today_entries)
    total_carbs = sum(e["carbs_g"] for e in today_entries)
    total_fat = sum(e["fat_g"] for e in today_entries)
    total_fibre = sum(e["fibre_g"] for e in today_entries)

    lines = [f"Today's Nutrition - {len(today_entries)} meals\n"]
    for i, e in enumerate(today_entries, 1):
        lines.append(f"{i}. {', '.join(e['foods'])} - {e['calories']}kcal ({e['time']})")

    lines.append("\nTotals:")
    lines.append(f"Calories: {total_cal} kcal")
    lines.append(f"Protein: {total_protein}g")
    lines.append(f"Carbs: {total_carbs}g")
    lines.append(f"Fat: {total_fat}g")
    lines.append(f"Fibre: {total_fibre}g")

    await update.message.reply_text("\n".join(lines))


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
        for p in r.get("pillars",[]): pc[p] = pc.get(p,0)+1
        dc[r.get("day_of_week","")] = dc.get(r.get("day_of_week",""),0)+1
    breakdown = "\n".join([f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {c}x" for p,c in sorted(pc.items(),key=lambda x:-x[1])]) or "No data"
    best_day = max(dc, key=dc.get) if dc else "N/A"
    report = await weekly_report(user)
    await update.message.reply_text(f"Weekly Report - {datetime.now().strftime('%B %d, %Y')}\n\n{days}/7 days - {total} habits - {user['streak']} streak\nBest day: {best_day}\n\nPillar breakdown:\n{breakdown}\n\nCoach says:\n{report}")

# ── CALLBACKS ────────────────────────────────────────────
async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    data = q.data

    # ── Mood ──
    if data.startswith("mood_"):
        mood = data.replace("mood_","")
        mood_labels = {"high":"Energised","medium":"Good","low":"Tired","very_low":"Struggling"}
        user["mood"] = mood_labels.get(mood, mood)
        user["mood_date"] = datetime.now().strftime("%Y-%m-%d")
        user["missed_days_alerted"] = False
        user["last_active_date"] = datetime.now().strftime("%Y-%m-%d")
        mood_responses = {"high":"Full energy today. Let's push.","medium":"Solid. Good day to build.","low":"Tired is fine. Tiny habits exist for days like this.","very_low":"Struggling is honest. One tiny thing is enough today."}
        base = mood_responses.get(mood,"Got it.")
        pids = await ai_pick_pillars(user)
        if mood in ("low","very_low"):
            pids = sorted(PIDS, key=lambda p: -user["scores"].get(p,3))[:3]
        habits = await ai_habits(user, pids)
        user["today_pillars"] = pids
        user["today_habits"] = habits
        user["checked"] = {}
        save_users()
        lines = [f"{base}\n\nYour habits for today:\n"]
        for p in pids:
            lines.append(f"{PILLARS[p]['emoji']} {PILLARS[p]['name']} - {habits.get(p,'')}")
        lines.append("\nTap each when done")
        await q.edit_message_text("\n".join(lines), reply_markup=habit_kb(user))

    elif data == "get_habits_now":
        user["missed_days_alerted"] = False
        user["last_active_date"] = datetime.now().strftime("%Y-%m-%d")
        pids = await ai_pick_pillars(user)
        habits = await ai_habits(user, pids)
        user["today_pillars"] = pids
        user["today_habits"] = habits
        user["checked"] = {}
        save_users()
        lines = ["Back at it. Here are your habits today:\n"]
        for p in pids:
            lines.append(f"{PILLARS[p]['emoji']} {PILLARS[p]['name']} - {habits.get(p,'')}")
        lines.append("\nTap each when done")
        await q.edit_message_text("\n".join(lines), reply_markup=habit_kb(user))

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
            "Health Profile - Step 3 of 7\n\nWhat is your fitness level?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Sedentary - little exercise", callback_data="profile_fitness_sedentary")],
                [InlineKeyboardButton("Lightly active - 1-3x/week", callback_data="profile_fitness_light")],
                [InlineKeyboardButton("Moderately active - 3-5x/week", callback_data="profile_fitness_moderate")],
                [InlineKeyboardButton("Very active - 6-7x/week", callback_data="profile_fitness_active")],
                [InlineKeyboardButton("Athlete - intense daily", callback_data="profile_fitness_athlete")],
            ])
        )

    elif data.startswith("profile_fitness_"):
        user["profile"]["fitness"] = data.replace("profile_fitness_","")
        user["profile_step"] = "conditions"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 4 of 7\n\nAny medical conditions?\nType them separated by commas.\n\nExamples: diabetes, hypertension, anxiety, arthritis\n\nOr tap Skip.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip - No conditions", callback_data="profile_skip_conditions")]])
        )

    elif data == "profile_skip_conditions":
        user["profile"]["conditions"] = []
        user["profile_step"] = "medications"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 5 of 7\n\nAny medications?\nType them separated by commas.\n\nOr tap Skip.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip - No medications", callback_data="profile_skip_medications")]])
        )

    elif data == "profile_skip_medications":
        user["profile"]["medications"] = []
        user["profile_step"] = "sleep"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 6 of 7\n\nHow is your sleep quality?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Poor - under 5 hours", callback_data="profile_sleep_poor")],
                [InlineKeyboardButton("Fair - 5-6 hours", callback_data="profile_sleep_fair")],
                [InlineKeyboardButton("Good - 7-8 hours", callback_data="profile_sleep_good")],
                [InlineKeyboardButton("Excellent - 8+ hours", callback_data="profile_sleep_excellent")],
            ])
        )

    elif data.startswith("profile_sleep_"):
        user["profile"]["sleep_quality"] = data.replace("profile_sleep_","")
        user["profile_step"] = "stress"
        save_users()
        await q.edit_message_text(
            "Health Profile - Step 7 of 7\n\nWhat is your typical stress level?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Low - generally relaxed", callback_data="profile_stress_low")],
                [InlineKeyboardButton("Moderate - some stress", callback_data="profile_stress_moderate")],
                [InlineKeyboardButton("High - frequently stressed", callback_data="profile_stress_high")],
                [InlineKeyboardButton("Very high - overwhelmed", callback_data="profile_stress_very_high")],
            ])
        )

    elif data.startswith("profile_stress_"):
        user["profile"]["stress_level"] = data.replace("profile_stress_","")
        user["profile_step"] = None
        if user.get("onboarding"):
            user["step"] = "active"
            user["onboarding"] = None
        save_users()
        profile = user["profile"]
        await q.edit_message_text(
            f"Profile complete!\n\n"
            f"Age: {profile.get('age')} | Sex: {profile.get('sex')} | Fitness: {profile.get('fitness')}\n"
            f"Conditions: {', '.join(profile.get('conditions',[])  ) or 'None'}\n"
            f"Medications: {', '.join(profile.get('medications',[])  ) or 'None'}\n"
            f"Sleep: {profile.get('sleep_quality')} | Stress: {profile.get('stress_level')}\n\n"
            "All set! Every habit is now personalised for you.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Get My First Habits Now!", callback_data="get_habits_now")],
            ])
        )

    # ── Onboarding ──
    elif data == "onboard_skip_goals":
        user["adding_goal"] = False
        user["onboarding"] = "reminders"
        await q.edit_message_text("Step 2 of 4 - Daily Reminders\n\nI will send you habits and nudges 4 times a day.\nTap each time to change it.", reply_markup=reminders_kb(user))

    elif data == "onboard_done_reminders":
        user["reminders_active"] = True
        schedule_reminders(ctx.application, uid)
        user["onboarding"] = "assess"
        save_users()
        await q.edit_message_text(
            "Step 3 of 4 - Quick Assessment\n\nRate each pillar 1-5 to personalise your habits.\n1 = struggling   5 = thriving",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Start Assessment", callback_data="assess")],
                [InlineKeyboardButton("Skip - Next Step", callback_data="onboard_to_profile")],
            ])
        )

    elif data == "onboard_to_profile":
        user["onboarding"] = "profile"
        user["profile_step"] = "age"
        await q.edit_message_text("Step 4 of 4 - Health Profile\n\nThis helps AI personalise habits to your age, health and fitness.\n\nHow old are you? (e.g. 35)\n\nOr tap Skip to finish setup.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip - Finish Setup", callback_data="onboard_done")]])
        )

    elif data == "onboard_done":
        user["step"] = "active"
        user["onboarding"] = None
        user["profile_step"] = None
        save_users()
        goals = user.get("personal_goals",[])
        goal_text = "\n".join([f"- {g}" for g in goals]) if goals else "None set"
        await q.edit_message_text(
            f"You are all set, {user['name']}!\n\nGoals:\n{goal_text}\n\nTap below to get your first 3 AI-powered habits.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Get My First Habits Now!", callback_data="get_habits_now")],
            ])
        )

    elif data == "start_habits_now":
        user["step"] = "active"
        save_users()
        await q.edit_message_text("Send /habit to get your first 3 habits now.")

    # ── Reminders ──
    elif data == "show_reminders":
        await q.edit_message_text("Set Your Daily Reminders\nTap a time to change it.", reply_markup=reminders_kb(user))

    elif data == "toggle_reminders":
        user["reminders_active"] = not user["reminders_active"]
        save_users()
        await q.edit_message_text("Your Reminder Schedule\nTap a time to change it:", reply_markup=reminders_kb(user))

    elif data == "save_reminders":
        user["reminders_active"] = True
        schedule_reminders(ctx.application, uid)
        save_users()
        lines = "\n".join([f"{SLOTS[s]['label']}: {user['reminders'].get(s)}" for s in SLOTS])
        if user.get("onboarding") == "reminders":
            user["onboarding"] = "assess"
            tz = user.get("timezone","UTC")
            await q.edit_message_text(
                f"Reminders set! ({tz})\n\n{lines}\n\n"
                "Step 4 of 5 - Rate Your Pillars\n\n"
                "How are you doing in each area? 1=struggling  5=thriving\n\n"
                "Takes 60 seconds and personalises your habits.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Start Rating Now", callback_data="assess")],
                    [InlineKeyboardButton("Skip This Step", callback_data="onboard_to_profile")],
                ])
            )
        else:
            await q.edit_message_text(f"Reminders activated!\n\n{lines}\n\nI will reach out 4 times a day. Send /habit anytime.")

    elif data.startswith("setslot_"):
        slot = data.replace("setslot_","")
        user["setting_slot"] = slot
        current = user["reminders"].get(slot, SLOTS[slot]["default"])
        await q.edit_message_text(f"Change {SLOTS[slot]['label']} reminder\n\nCurrent: {current}\n\nReply with time in HH:MM format\nExample: 08:30 or 21:00")

    # ── Goals ──
    elif data == "add_goal":
        user["adding_goal"] = True
        await q.edit_message_text("Add a Personal Goal\n\nType your goal below.\nExamples:\n- Drink more water\n- Eat more protein\n- Sleep before midnight\n- Walk 10000 steps")

    elif data == "add_another_goal":
        user["adding_goal"] = True
        goals = user.get("personal_goals",[])
        await q.edit_message_text(f"You have {len(goals)} goal(s) so far:\n" + "\n".join([f"- {g}" for g in goals]) + "\n\nType your next goal:")

    elif data.startswith("rmgoal_"):
        idx = int(data.replace("rmgoal_",""))
        goals = user.get("personal_goals",[])
        if 0 <= idx < len(goals):
            removed = goals.pop(idx)
            user["personal_goals"] = goals
            save_users()
            await q.edit_message_text(f"Removed: {removed}\n\nSend /goals to manage your goals.")

    elif data == "clear_goals":
        user["personal_goals"] = []
        save_users()
        await q.edit_message_text("All goals cleared. Send /goals to add new ones.")

    # ── Assessment ──
    elif data == "assess":
        user["step"] = "assess"
        user["scores"] = {}
        p = PILLARS[PIDS[0]]
        await q.edit_message_text(f"Rate each pillar 1-5.\n1 = struggling - 5 = thriving\n\n{p['emoji']} {p['name']} - {p['desc']}", reply_markup=score_kb(PIDS[0]))

    elif data == "skip_assess":
        user["step"] = "active"
        await q.edit_message_text("Got it. Send /habit to get your 3 habits now.")

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
            save_users()
            ranked = sorted(PIDS, key=lambda p: user["scores"].get(p,3))
            lines = [f"{PILLARS[p]['emoji']} {PILLARS[p]['name']}: {user['scores'][p]}/5" for p in ranked]
            if user.get("onboarding"):
                await q.edit_message_text(
                    "Assessment done!\n\nYour pillars (weakest first):\n" + "\n".join(lines) +
                    "\n\nLast step! Add your health profile so AI personalises habits to your age, conditions and fitness.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Set Health Profile", callback_data="onboard_to_profile")],
                        [InlineKeyboardButton("Skip - Finish Setup", callback_data="onboard_done")],
                    ])
                )
            else:
                await q.edit_message_text(
                    "Assessment done!\n\nYour pillars:\n" + "\n".join(lines) + "\n\nSend /habit to get your first 3 habits."
                )

    # ── Macros ──
    elif data == "view_macros":
        uid2 = q.from_user.id
        user2 = get_user(uid2)
        today = datetime.now().strftime("%Y-%m-%d")
        entries = [e for e in user2.get("macro_log",[]) if e["date"]==today]
        if not entries:
            await q.edit_message_text("No meals logged today. Send a photo of your food!")
            return
        total_cal = sum(e["calories"] for e in entries)
        total_p = sum(e["protein_g"] for e in entries)
        total_c = sum(e["carbs_g"] for e in entries)
        total_f = sum(e["fat_g"] for e in entries)
        lines = [f"Today - {len(entries)} meals\n"]
        for i,e in enumerate(entries,1):
            lines.append(f"{i}. {', '.join(e['foods'])} ({e['time']}) - {e['calories']}kcal")
        lines.append(f"\nTotal: {total_cal}kcal | P:{total_p}g | C:{total_c}g | F:{total_f}g")
        await q.edit_message_text("\n".join(lines))

    elif data == "prompt_photo":
        await q.edit_message_text("Send a photo of your next meal and I will analyse it!")

    # ── Habit done ──
    elif data.startswith("done_"):
        pid = data.replace("done_","")
        if pid in user["checked"]: return
        user["checked"][pid] = True
        done = len(user["checked"])
        total = len(user["today_pillars"])
        if done >= total:
            user["streak"] += 1
            today = datetime.now().strftime("%Y-%m-%d")
            user["last_checkin_date"] = today
            user["last_active_date"] = today
            user["missed_days_alerted"] = False
            user["weekly_history"].append({"date":today,"day_of_week":datetime.now().strftime("%A"),"pillars":user["today_pillars"],"habits":user["today_habits"],"streak":user["streak"]})
            user["weekly_history"] = user["weekly_history"][-30:]
            save_users()
            msg = await ai_msg(user, "all_done")
            await q.edit_message_text(f"{done}/{total} done - Day {user['streak']} complete!\n\n{msg}")
        else:
            await q.edit_message_text(f"{done}/{total} done - keep going!", reply_markup=habit_kb(user))

# ── CHAT ─────────────────────────────────────────────────
async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    text = update.message.text

    # Profile text inputs
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
                    "Health Profile - Step 2 of 7\n\nWhat is your biological sex?",
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
            conditions = [c.strip() for c in text.split(",") if c.strip()]
            user["profile"]["conditions"] = conditions
            user["profile_step"] = "medications"
            save_users()
            await update.message.reply_text(
                f"Got it: {', '.join(conditions)}\n\nStep 5 of 7 - Any medications?\nType them separated by commas, or tap Skip.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip - No medications", callback_data="profile_skip_medications")]])
            )
            return
        elif step == "medications":
            meds = [m.strip() for m in text.split(",") if m.strip()]
            user["profile"]["medications"] = meds
            user["profile_step"] = "sleep"
            save_users()
            await update.message.reply_text(
                f"Got it: {', '.join(meds)}\n\nStep 6 of 7 - How is your sleep quality?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Poor - under 5 hours", callback_data="profile_sleep_poor")],
                    [InlineKeyboardButton("Fair - 5-6 hours", callback_data="profile_sleep_fair")],
                    [InlineKeyboardButton("Good - 7-8 hours", callback_data="profile_sleep_good")],
                    [InlineKeyboardButton("Excellent - 8+ hours", callback_data="profile_sleep_excellent")],
                ])
            )
            return
        elif step == "stress":
            # If they type during stress step, just prompt them to use buttons
            await update.message.reply_text("Please use the buttons above to select your stress level.")
            return

    # Reminder time input
    if user.get("setting_slot"):
        slot = user["setting_slot"]
        try:
            h, m = map(int, text.strip().split(":"))
            assert 0 <= h <= 23 and 0 <= m <= 59
            user["reminders"][slot] = f"{h:02d}:{m:02d}"
            user["setting_slot"] = None
            save_users()
            # Auto show next step based on context
            if user.get("onboarding") == "reminders":
                await update.message.reply_text(
                    f"{SLOTS[slot]['label']} set to {user['reminders'][slot]}\n\nSet your other reminder times or tap Save when ready.",
                    reply_markup=reminders_kb(user)
                )
            else:
                await update.message.reply_text(
                    f"{SLOTS[slot]['label']} set to {user['reminders'][slot]}\n\nAll your reminders:",
                    reply_markup=reminders_kb(user)
                )
        except:
            await update.message.reply_text("Invalid format. Please send as HH:MM - example: 08:30")
        return

    # Goal input
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
                    btns = [
                        [InlineKeyboardButton("Add Another Goal", callback_data="add_another_goal")],
                        [InlineKeyboardButton("Continue to Reminders →", callback_data="onboard_skip_goals")],
                    ]
                    await update.message.reply_text(
                        f"Goal {len(goals)} added!\n\n" +
                        "\n".join([f"{i+1}. {g}" for i,g in enumerate(goals)]) +
                        ("\n\nAdd more or continue when ready." if len(goals)<5 else "\n\nMaximum 5 goals reached."),
                        reply_markup=InlineKeyboardMarkup(btns)
                    )
                else:
                    await update.message.reply_text(
                        f"Goal added: {goal}\n\nYou now have {len(goals)} goal(s).",
                        reply_markup=goals_kb(goals)
                    )
        else:
            await update.message.reply_text("Please describe your goal in a bit more detail.")
        return

    # AI coach chat
    scores_str = ", ".join([f"{PILLARS[k]['name']}:{v}/5" for k,v in user["scores"].items()]) or "not assessed"
    try:
        reply = await groq(text, f"Direct habit coach for {user['name'] or 'user'}. Streak: {user['streak']}. Scores: {scores_str}. Short punchy texts. Max 2 sentences.", max_tokens=100)
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
    load_users()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("habit",     cmd_habit))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("assess",    cmd_assess))
    app.add_handler(CommandHandler("reminders", cmd_reminders))
    app.add_handler(CommandHandler("timezone",  cmd_timezone))
    app.add_handler(CommandHandler("goals",     cmd_goals))
    app.add_handler(CommandHandler("profile",   cmd_profile))
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(CommandHandler("macros",    cmd_macros))
    app.add_handler(MessageHandler(filters.PHOTO, handle_food_photo))
    app.add_handler(CallbackQueryHandler(handle_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_chat))

    app.job_queue.run_daily(send_weekly_report, time=time(hour=8, minute=0, tzinfo=pytz.UTC), days=(6,), name="weekly_report")
    app.job_queue.run_daily(send_mood_checkin,  time=time(hour=7, minute=0, tzinfo=pytz.UTC), name="mood_checkin")
    app.job_queue.run_daily(check_missed_days,  time=time(hour=10, minute=0, tzinfo=pytz.UTC), name="missed_days")
    app.job_queue.run_daily(detect_patterns,    time=time(hour=9, minute=0, tzinfo=pytz.UTC), days=(5,), name="patterns")

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
