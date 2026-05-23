import subprocess
import sys
from pathlib import Path

import paramiko

from config import Config

# Kindle setup that runs on every push:
#  - prevent the device from suspending while on AC (so it stays on indefinitely when plugged in)
#  - stop the reader framework so the status bar / "My Kindle" don't overlay our image
#  - flash-refresh the e-ink display with our PNG
_PUSH_CMD = (
    "lipc-set-prop com.lab126.powerd preventSuspendOnAC 1 2>/dev/null; "
    "stop lab126_gui 2>/dev/null; "
    "stop framework 2>/dev/null; "
    f"/usr/sbin/eips -f -g {Config.KINDLE_IMAGE_PATH}"
)


def push_to_kindle(image_path: Path) -> None:
    """SCP the rendered image to the Kindle and trigger an e-ink display refresh."""
    if sys.platform == "win32":
        _push_subprocess(image_path)
    else:
        _push_paramiko(image_path)


def _push_subprocess(image_path: Path) -> None:
    """Windows: delegate to system scp/ssh (paramiko hits socket permission errors on Windows)."""
    host = f"{Config.KINDLE_USER}@{Config.KINDLE_HOST}"
    key = Path.home() / ".ssh" / "id_ed25519"
    opts = ["-o", "StrictHostKeyChecking=no", "-o", "PasswordAuthentication=yes"]
    if key.exists():
        opts += ["-i", str(key)]

    subprocess.run(
        ["scp"] + opts + [str(image_path), f"{host}:{Config.KINDLE_IMAGE_PATH}"],
        check=True,
    )
    subprocess.run(
        ["ssh"] + opts + [host, _PUSH_CMD],
        check=True,
    )


def _push_paramiko(image_path: Path) -> None:
    """Linux/Pi: use paramiko for non-interactive password auth."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=Config.KINDLE_HOST,
            username=Config.KINDLE_USER,
            password=Config.KINDLE_PASSWORD,
        )
        with client.open_sftp() as sftp:
            sftp.put(str(image_path), Config.KINDLE_IMAGE_PATH)
        _exec(client, _PUSH_CMD)
    finally:
        client.close()


def _exec(client: paramiko.SSHClient, cmd: str) -> str:
    _, stdout, stderr = client.exec_command(cmd)
    err = stderr.read().decode().strip()
    if err:
        raise RuntimeError(f"Kindle SSH command failed: {err}")
    return stdout.read().decode()
