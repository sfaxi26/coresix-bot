# CoreSix Telegram Bot

6 weeks. 6 pillars. One tiny habit a day.

## Setup

### 1. Get your bot token
- Open Telegram → search @BotFather
- Send `/newbot`
- Name: `CoreSix`
- Username: `coresix_bot` (or any available name)
- Copy the token you receive

### 2. Deploy to Railway
1. Go to railway.app → sign up free
2. Click "New Project" → "Deploy from GitHub"
   - Or use "Deploy from local" and upload this folder
3. Add environment variable:
   - `BOT_TOKEN` = your token from BotFather
4. Deploy — bot goes live in ~2 minutes!

### 3. Test your bot
- Open Telegram → search your bot username
- Send `/start`
- Follow the journey!

## Commands
- `/start` — Begin or restart the journey
- `/habit` — Get today's 3 habit options
- `/status` — See your roadmap and streak

## How it works
1. User starts → chooses assessment or default order
2. Assessment personalises 6-week pillar order (weakest first)
3. Each day: 3 habit options (Easy / Normal / Challenge)
4. User picks one → marks done → streak grows
5. After 7 days → next pillar week unlocks
6. After 6 weeks → journey complete!
