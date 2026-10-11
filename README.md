# Kindle Dashboard

A personal e-ink dashboard running on a jailbroken Kindle Paperwhite

My Raspberry Pi renders a PNG (running plan w/ AI coaching, upcoming birthdays) and pushes it to the Kindle over SSH every
30 minutes. Tapping the Kindle's touchscreen navigates between views.
It works with just a static image and a raw
touch-event listener. Integrations with external APIs make it extra functional + cool.

## Well... this is what it look like (before + after run)

<img width="707" height="874" alt="image" src="https://github.com/user-attachments/assets/b32e5783-332d-48da-800e-1d43e4b49e71" />
<img width="740" height="880" alt="image" src="https://github.com/user-attachments/assets/430177b5-611f-4472-815c-8e1d17d41a8f" />


## Why

I wanted an always-on screen next to my desk that shows the things
I check every day (today's run, upcoming birthdays, etc.) I was going to buy an
actual e-ink display and use that, but then felt cheap and decided to buy a 10 year old kindle on amazon instead :P

## Features

- **Running plan**: multi-week training plan, generated and edited via
  Claude from a short intake conversation in the UI. A daily job reconciles the planned run vs the actual run (via intervals.icu's API) and Claude writes a short post-run
  coaching note. It also adjusts the following day's assigned run if I was naughty and ran more or less than I was meant to.
- **Birthdays**: upcoming birthdays surfaced on the dashboard.
- **Touch navigation**: tapping a section on the Kindle drills into a more detailed
  view (e.g. tapping the running section shows the full week).
- **Web UI**: a small Flask app (also the thing that renders/pushes the
  dashboard) for entering/editing plan and birthday data
  from a browser. It's also exposed via a Cloudflare Tunnel so I (and only I) can access it when I'm not on my home network.

## Architecture

https://excalidraw.com/#json=8G8CLpjyidtB5qVa8PFEr,Z4pU58nCj_xEU8AoMPspVA

<img width="2736" height="1248" alt="image" src="https://github.com/user-attachments/assets/1661d757-ace3-4f23-929a-c1108d153b4d" />

The Flask app serves the web UI,
runs the in-process scheduler that triggers renders/pushes, and handles
incoming taps from the Kindle. `main.py` is the one-shot render+push path,
runnable standalone (`python main.py`) without the web server.

## Tech stack

- **Backend**: Flask, APScheduler (in-process background jobs), Paramiko
  (SSH/SCP to the Kindle)
- **Rendering**: Pillow (hand-drawn layout onto a 758×1024 canvas — the
  Kindle Paperwhite 1's native portrait resolution)
- **AI**: Anthropic Claude (training plan generation/editing, post-run
  coaching notes)
- **Data**: intervals.icu API (training history), flat JSON files for local state (no database)
- **Kindle side**: POSIX shell script reading raw Linux input events off
  `/dev/input/event0`, `eips` for e-ink refresh

## Setup

See [DEPLOY.md](DEPLOY.md) for the full setup story (host machine, SSH trust
with the Kindle, systemd service, Kindle-side tap listener, Cloudflare
Tunnel). Quick version:

```
git clone <this repo>
cd kindle
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in Kindle host, API keys
python run.py          # Flask dev server on :5000, starts the scheduler
```

`python preview.py` renders the dashboard with mock data to `output/` without
needing a Kindle or any API keys.

## Notes
- Runtime data (`data/*.json`) isn't checked into git, by design — a fresh
  clone starts with an empty dashboard.
