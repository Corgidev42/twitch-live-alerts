# 🔴 Alertes live Twitch → Discord

Toutes les ~5 minutes, GitHub Actions vérifie si la chaîne **[mantate_](https://www.twitch.tv/mantate_)** est en live.
Quand un live démarre, une alerte est postée dans le salon Discord 🔴・en-direct (avec un ping 🔔 Notif Live).
Quand il se termine, l'alerte passe en « Live terminé ».

## Secrets à configurer (Settings → Secrets and variables → Actions)
- `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` : app Twitch (https://dev.twitch.tv/console)
- `DISCORD_WEBHOOK_URL` : webhook du salon

## Tester
Onglet **Actions** → « Alerte live Twitch » → **Run workflow** → cocher *test*.
