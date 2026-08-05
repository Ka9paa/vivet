# Vivet Discord OAuth Role Access

Register this exact redirect in Discord Developer Portal → OAuth2 → Redirects:

`https://vivet-six.vercel.app/auth/discord/callback`

Add the variables from `.env.example` to Vercel Production Environment Variables, then redeploy.

Role mapping:

- `DISCORD_OWNER_ROLE_ID` → full Owner role
- `DISCORD_AUTH_ROLE_ID` → Auth Access role
- No matching role → access denied

The OAuth request uses `identify guilds.members.read`, validates a one-time state cookie, reads the user's member roles from the configured guild, and creates a secure HTTP-only session.

Important: verify that both configured values are Discord **role IDs**, not user IDs. Reset any client secret or bot token that was previously shared.
