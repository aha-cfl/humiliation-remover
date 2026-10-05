#!/usr/bin/env bash
# One-command setup for macOS. Run from the repo root:  ./setup.sh
# Re-run anytime the Paycor login expires; it reuses the existing app.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
CONF=.autopunch.env   # local record of app name/token (gitignored)
[ -f "$CONF" ] && source "$CONF"

say "Checking tools"
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
command -v flyctl >/dev/null || brew install flyctl
command -v python3 >/dev/null || brew install python

say "Installing Python deps (local venv)"
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m playwright install chromium

say "Paycor login: a browser window will open"
echo "Sign in fully (including any MFA code). Tick 'remember this device' if offered."
API_TOKEN=x DATA_DIR=data .venv/bin/python -m autopunch.login
SESSION_B64=$(base64 < data/paycor_session.json | tr -d '\n')

if [ -z "${APP:-}" ]; then
  say "First-time config"
  read -rp "Paycor username/email: " PAYCOR_USER
  read -rsp "Paycor password (stored only as an encrypted Fly secret): " PAYCOR_PASS; echo
  read -rp "Time zone [America/New_York]: " TZ_NAME; TZ_NAME=${TZ_NAME:-America/New_York}
  APP="autopunch-$(openssl rand -hex 4)"
  API_TOKEN=$(openssl rand -hex 24)
  NTFY_TOPIC="autopunch-$(openssl rand -hex 8)"
  printf 'APP=%s\nAPI_TOKEN=%s\nNTFY_TOPIC=%s\n' "$APP" "$API_TOKEN" "$NTFY_TOPIC" > "$CONF"
  chmod 600 "$CONF"

  say "Fly.io account (browser opens if you're not logged in)"
  flyctl auth whoami >/dev/null 2>&1 || flyctl auth login

  say "Creating app $APP"
  flyctl apps create "$APP"
  flyctl volumes create autopunch_data --app "$APP" --region iad --size 1 --yes
  flyctl secrets set --app "$APP" --stage \
    API_TOKEN="$API_TOKEN" PAYCOR_USER="$PAYCOR_USER" PAYCOR_PASS="$PAYCOR_PASS" \
    NTFY_TOPIC="$NTFY_TOPIC" TZ_NAME="$TZ_NAME" PAYCOR_SESSION_B64="$SESSION_B64"
else
  say "Updating Paycor login on existing app $APP"
  flyctl secrets set --app "$APP" --stage PAYCOR_SESSION_B64="$SESSION_B64"
fi

say "Deploying (takes ~3 min the first time)"
flyctl deploy --app "$APP" --ha=false --remote-only

URL="https://$APP.fly.dev"
say "Health check"
for i in 1 2 3 4 5 6; do
  if curl -fsS -H "Authorization: Bearer $API_TOKEN" "$URL/status"; then echo; break; fi
  sleep 10
done

cat <<EOF

$(printf '\033[1m')DONE ON THE COMPUTER. Now on your iPhone:$(printf '\033[0m')

1) App Store -> install "ntfy" -> + -> subscribe to topic:
     $NTFY_TOPIC

2) Shortcuts -> Automation -> + -> Location -> Arrive -> your work address
   (radius ~150 m) -> Run Immediately -> New Blank Automation ->
   add "Get Contents of URL":
     URL:     $URL/event
     Method:  POST
     Headers: Authorization = Bearer $API_TOKEN
     Body:    JSON, key "event" (Text) = arrive

3) Same again with Leave, and "event" = leave.

4) Settings -> Privacy & Security -> Location Services -> Shortcuts -> Always + Precise.

Tomorrow you'll get "Clocked in 8:3x ✓" on ntfy a few minutes after you arrive.
If you ever get a FAILED push about MFA/login, just run ./setup.sh again.
(These values are saved in $CONF.)
EOF
