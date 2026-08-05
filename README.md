# Vivet

Vivet is a self-hosted software licensing and access-management MVP with a premium owner dashboard, license authentication API, HWID controls, real activity metrics, Discord OAuth sign-in, and Discord slash-command access management.

## Local setup (Windows / Git Bash)

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/login`.

Default local owner login:

- Username: `dec`
- Password: `dec11`

Change both the password and `JWT_SECRET` before public deployment.

## Discord setup

1. Rotate any bot token or client secret that has ever been shared publicly.
2. Add the new values only to `.env`; never commit `.env`.
3. In Discord Developer Portal, add this redirect URL:
   `http://127.0.0.1:8000/auth/discord/callback`
4. Invite the bot with the `bot` and `applications.commands` scopes.
5. Enable Server Members Intent if Discord asks for it.
6. Start the web panel, then start the bot in a second terminal:

```bash
source .venv/Scripts/activate
python run_discord_bot.py
```

Commands:

- `/auth add @user admin`
- `/auth add @user developer`
- `/auth add @user reseller`
- `/auth add @user support`
- `/auth add @user viewer`
- `/auth remove @user`
- `/auth permissions @user`
- `/auth list`

Authorized users can use **Continue with Discord** on the login page.

## Important

This is a development MVP. Before exposing it to the internet, add HTTPS, CSRF protection, stronger role enforcement per route, database migrations, encrypted secret storage, rate limiting, secure cookies, 2FA, backups, and production monitoring.
