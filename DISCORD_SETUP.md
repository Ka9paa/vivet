# Vivet Discord setup

## 1. Rotate exposed credentials
Reset the bot token from **Developer Portal → Bot → Reset Token** and regenerate the OAuth2 client secret. Never paste either value into chat or commit them to Git.

## 2. Configure `.env`
Copy `.env.example` to `.env`, then enter the newly rotated values with no spaces around `=`.

```env
DISCORD_BOT_TOKEN=NEW_TOKEN_HERE
DISCORD_APPLICATION_ID=1530814557386178610
DISCORD_PUBLIC_KEY=PUBLIC_KEY_FROM_GENERAL_INFORMATION
DISCORD_CLIENT_SECRET=NEW_CLIENT_SECRET_HERE
DISCORD_GUILD_ID=1256277504566759465
DISCORD_OWNER_USER_ID=1533103551050416410
DISCORD_AUTH_STAFF_ROLE_ID=1495481348058513489
```

The public key is located under **Developer Portal → your application → General Information → Public Key**.

## 3. Discord portal settings
Under **OAuth2 → Redirects**, add:

```text
http://127.0.0.1:8000/auth/discord/callback
```

Under **Bot → Privileged Gateway Intents**, enable **Server Members Intent**. Invite the bot with the `bot` and `applications.commands` scopes.

## 4. Run Vivet
Terminal 1:

```bash
python -m uvicorn app.main:app --reload
```

Terminal 2:

```bash
python run_discord_bot.py
```

Available commands: `/auth add`, `/auth remove`, `/auth permissions`, and `/auth list`.

## Logging channel
Add this to your local `.env` (the update does not modify your `.env`):

```env
DISCORD_LOG_CHANNEL_ID=YOUR_CHANNEL_ID
```

The bot also automatically uses a channel named `#vivet-logs`, `#auth-logs`, or `#logs` when no ID is configured. Give the bot **View Channel**, **Send Messages**, and **Embed Links** permissions.

## Vivet access roles
- **Owner** — full dashboard and Discord command access.
- **Admin** — manages access, applications, and keys; cannot grant Owner.
- **Developer** — manages applications and advanced key actions.
- **Auth Access** — generates, checks, deletes, and resets keys.

## Slash commands
- `/auth add @user role`
- `/auth remove @user`
- `/auth permissions @user`
- `/auth list`
- `/generate application duration quantity note`
- `/delete_key key`
- `/key_info key`
- `/reset_hwid key`
- `/ban_key key banned`
