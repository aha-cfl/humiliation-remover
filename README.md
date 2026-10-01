# autopunch

Clocks you in/out of Paycor when your iPhone enters/leaves a geofence around work.

```
iPhone Shortcut (arrive/leave)  ──HTTPS──▶  server (FastAPI)  ──Playwright──▶  Paycor web clock
                                               │
                                               └──▶ ntfy push: "Clocked in 8:41 ✓" / "FAILED"
```

**Prerequisite:** your Paycor account must have the *web* clock (log in on a desktop
browser; you should see a Clock In button). If it doesn't, this cannot work.

Get employer sign-off on automated punches before using this.

## Behavior

| Event | Effect |
|---|---|
| Arrive | Clock in after 3 min dwell (leave within 3 min cancels it) |
| Leave | Clock out after 5 min (re-arrive within 5 min cancels it) |
| Outside 07:45–10:00 (in) / 16:30–19:30 (out), weekends | Ignored — so lunch exits never clock you out |
| Already in / not in | Ignored — no double punches |
| Punch fails twice | High-priority push; screenshot at `/data/last-failure.png` |
| Still clocked in after 19:30 | High-priority push |

All windows/delays are env vars — see `.env.example`.

## Setup (~30 min, once)

### 1. Capture a Paycor session (your computer)
```bash
pip install -r requirements.txt && playwright install chromium
API_TOKEN=x python -m autopunch.login     # log in in the window, tick "remember device", press Enter
```
Produces `data/paycor_session.json`.

### 2. Deploy (Fly.io, ~$2–5/mo)
```bash
brew install flyctl && fly auth signup
# edit app name in fly.toml first
fly launch --copy-config --no-deploy
fly volumes create autopunch_data --size 1
fly secrets set API_TOKEN=$(openssl rand -hex 32) PAYCOR_USER=you@x.com PAYCOR_PASS='...' \
  NTFY_TOPIC=autopunch-$(openssl rand -hex 6) TZ_NAME=America/New_York
fly deploy
fly ssh sftp shell    # then: put data/paycor_session.json /data/paycor_session.json
fly secrets list      # note API_TOKEN; `fly ssh console -C 'printenv API_TOKEN'` to read it
```

### 3. Notifications
Install **ntfy** from the App Store → subscribe to your `NTFY_TOPIC`.

### 4. Test the punch path before trusting it
```bash
URL=https://<app>.fly.dev; T=<API_TOKEN>
curl -H "Authorization: Bearer $T" $URL/status
curl -XPOST -H "Authorization: Bearer $T" $URL/punch/in     # only works inside the clock-in window
```
If it fails: `fly ssh sftp get /data/last-failure.png`, find the button, and set e.g.
`fly secrets set SEL_CLOCK_IN='button:has-text("Start Shift")'`.

### 5. iPhone Shortcuts (two automations)
Shortcuts → **Automation** → **+** → **Arrive** → choose work address, radius ~150 m,
Time: Any Time → **Run Immediately** (turn off "Notify When Run") → Next → **New Blank Automation**:

- Action **Get Contents of URL**
  - URL: `https://<app>.fly.dev/event`
  - Method: **POST**
  - Headers: `Authorization` = `Bearer <API_TOKEN>`
  - Request Body: **JSON**, key `event` (Text) = `arrive`

Repeat with **Leave** and `event` = `leave`.

Settings → Privacy → Location Services → Shortcuts → **Always** + **Precise**.

## Maintenance
- **Session expires** (MFA prompt) → you get a FAILED push → rerun step 1 and re-upload the file.
- **Paycor UI change** → FAILED push → check screenshot, set `SEL_CLOCK_IN/OUT`.
- Tests: `pip install pytest && pytest`.
