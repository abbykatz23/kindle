import json
import threading
import time
import uuid

from config import Config

_lock = threading.Lock()

# Jobs older than this are dropped the next time a job is created, so jobs.json
# doesn't grow forever. Entries from before created_at existed are dropped too.
MAX_JOB_AGE_S = 24 * 60 * 60


def _path():
    return Config.DATA_DIR / "jobs.json"


def _load() -> dict:
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save(jobs: dict) -> None:
    Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(jobs, indent=2))


def create(week_label: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        jobs = _load()
        cutoff = time.time() - MAX_JOB_AGE_S
        jobs = {jid: job for jid, job in jobs.items() if job.get("created_at", 0) >= cutoff}
        jobs[job_id] = {"status": "running", "week_label": week_label, "error": None,
                        "created_at": time.time()}
        _save(jobs)
    return job_id


def get_job(job_id: str) -> dict | None:
    with _lock:
        return _load().get(job_id)


def mark_done(job_id: str, extra: dict | None = None) -> None:
    with _lock:
        jobs = _load()
        if job_id in jobs:
            jobs[job_id]["status"] = "done"
            if extra:
                jobs[job_id].update(extra)
            _save(jobs)


def mark_progress(job_id: str, message: str) -> None:
    with _lock:
        jobs = _load()
        if job_id in jobs:
            jobs[job_id]["message"] = message
            _save(jobs)


def mark_failed(job_id: str, error: str) -> None:
    with _lock:
        jobs = _load()
        if job_id in jobs:
            jobs[job_id].update({"status": "error", "error": error})
            _save(jobs)
