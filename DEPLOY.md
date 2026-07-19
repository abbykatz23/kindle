# Deploying / transferring this project

This dashboard has two physical dependencies: a host machine that renders the
image and talks to the Kindle over SSH (currently a Windows PC; intended
production host is a Raspberry Pi), and a jailbroken Kindle Paperwhite 1
running FW 5.3.3 in permanent dashboard mode. Either one can die and be
replaced independently — this doc is what you need to rebuild the software
side from scratch.

## Architecture (read this first)

- `web/app.py` runs a Flask app. When it starts, it also starts an
  **in-process APScheduler** that:
  - re-renders + pushes the dashboard every 30 minutes (`trigger_refresh`)
  - runs a daily running-compliance check at 01:05
  - **This is the only scheduling mechanism currently in use.** The dashboard
    only auto-refreshes while this Flask process is alive.
- `cron/crontab.example` and `scheduler/poller.py` are **legacy** — an early
  cron-based refresh loop from before APScheduler was added directly to the
  Flask app (2026-07-02, commit `a4a0fdc`). It was never deleted. Do **not**
  install it alongside the Flask app — you'd get duplicate refreshes/pushes.
  It also references `scheduler/generate_week.py`, which no longer exists, so
  installing it as-is will produce a failing Sunday cron job. Safe to ignore
  or delete; the Flask app is the source of truth for scheduling.
- Kindle-side taps are read by `kindle/tap_listener.sh` (deployed onto the
  Kindle itself) and POSTed to the Flask app's `/tap` endpoint, which calls
  into `utils/tap_handler.py`.
- The web UI (also served by `web/app.py`, port 5000) is how you edit
  birthdays / running plan / interview-prep data. It's reportedly exposed
  externally via a Cloudflare Tunnel — that tunnel's config lives in your
  Cloudflare dashboard, **not in this repo**, so it isn't reproduced by
  cloning. Re-create the tunnel route (→ `localhost:5000`) manually on new
  hardware if you want remote access to the web UI.

## 1. Host machine setup (Pi or otherwise)

```
git clone <this repo>
cd kindle
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:
- `KINDLE_HOST` / `KINDLE_USER` / `KINDLE_PASSWORD` — Kindle SSH access.
  Password auth is a fallback; SSH key auth (below) is preferred and is what
  actually gets used if a key is present.
- `LEETCODE_USERNAME`
- `ANTHROPIC_API_KEY`
- `INTERVALS_API_KEY` / `INTERVALS_ATHLETE_ID`
- `SECRET_KEY` — set to a real random value, not the placeholder, if the web
  UI is exposed beyond localhost.

**Fonts**: `dashboard/assets/fonts/` is empty in git (fonts aren't checked
in). `dashboard/render.py` falls back through a list of system font paths,
including `/usr/share/fonts/truetype/dejavu/DejaVuSans*.ttf` on Linux. A
stock Raspberry Pi OS image does **not** have this installed by default —
run `sudo apt install fonts-dejavu-core` or the dashboard will silently
render with Pillow's built-in bitmap font instead of erroring.

**Python version**: no version is pinned anywhere; developed against a
recent CPython 3.11+ (uses `dict[tuple[int, bool], ...]`-style built-in
generic type hints, which need 3.9+ at minimum).

## 2. SSH trust between host and Kindle

`dashboard/push.py` looks for a key at `~/.ssh/id_ed25519` (falls back to
`KINDLE_PASSWORD` from `.env` if absent). On new hardware:

```
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id root@<KINDLE_HOST>          # or manually append the .pub to
                                          # the Kindle's authorized_keys
```

If the Kindle itself is also being rebuilt (rejailbroken), just make sure
whatever authorized_keys setup you do during the jailbreak includes this
host's new public key.

## 3. Running the app

Dev/manual:
```
python run.py            # Flask dev server, port 5000, starts APScheduler
```

For unattended production use (survives reboot), use the committed systemd
unit at `deploy/kindle-web.service`. It runs `python run.py` directly
(Flask's dev server, not gunicorn — deliberate: it's what's actually been
running reliably in production, and the app is single-user/low-traffic
enough that a production WSGI server hasn't been necessary) with
`Restart=always`, and the app fires an immediate refresh on startup (see
`web/app.py`) so a reboot doesn't wait up to 30 min for the first push. On
the Pi:

```
sudo cp deploy/kindle-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kindle-web.service
```

The committed unit already has this deployment's real `User=`/
`WorkingDirectory=`/`EnvironmentFile=` (`abbykatz` / `/home/abbykatz/kindle`)
— adjust those three lines if the username or clone path differs on new
hardware. Only ever run one copy of the app at a time (this service, or a
manual `python run.py`, never both) — they'll fight over port 5000, since
each instance starts its own copy of the in-process refresh scheduler.

One-off manual render+push (no web app needed): `python main.py`

## 4. Kindle-side setup

Assumes the Kindle is already jailbroken (FW 5.3.3-era jailbreak; out of
scope here — see whatever jailbreak guide you used originally) and has SSH
access as `root`.

Deploy the tap listener:
1. Set `DASHBOARD_HOST_IP` in `.env` to this host's own LAN IP (the address
   the Kindle should POST tap coordinates to — not the Kindle's IP).
2. `sh kindle/deploy_tap_listener.sh` — substitutes that IP into
   `kindle/tap_listener.sh` and SCPs the result to the Kindle. Re-run this
   any time the host's IP changes (new hardware, DHCP lease change) instead
   of hand-editing the script.
3. Run it on the Kindle (as a persistent process — e.g. via whatever
   init/autostart mechanism your jailbreak setup uses, so it survives Kindle
   reboots): `sh /mnt/us/kindle/tap_listener.sh`

## 5. Data

Runtime data (`data/plan.json`, `birthdays.json`, `running_coaching_notes.json`,
etc.) is intentionally gitignored and does not transfer via `git clone` — a
fresh checkout starts with an empty dashboard. Re-enter this through the web
UI, or manually copy the `data/*.json` files over from the old host if you
have access to them before it's decommissioned.

## Known platform gotchas

- No `%-d` strftime on Linux/Windows portability issue: code already handles
  this (see `_format_now` in `main.py`, `_datefmt` in `web/app.py`) — no
  action needed, just don't reintroduce raw `%-d`/`%#d` elsewhere.
- `pip-system-certs` in `requirements.txt` is there for a corporate MITM SSL
  proxy on the original Windows dev machine. Harmless but unnecessary on a
  Pi/Linux host.
