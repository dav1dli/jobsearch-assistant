# Standalone Deployment

This directory is a self-contained Hermes job-search deployment. Its Compose project builds the pinned Hermes v0.22.5-desktop image, mounts only the job policy and LinkedIn applications skill, stores Hermes state and employment documents in its own named volume, and connects the service only to its dedicated egress network. The dashboard is published only on nuc2's loopback interface for SSH-tunnel access; no service port is published to the LAN or internet.

## Build and Setup

Build from this directory:

```sh
docker compose build job-agent
```

For first-time operation, create a dedicated Telegram bot and configure a separate model credential. Use `hermes setup` interactively, or follow the manual Telegram procedure in [configuration](CONFIGURATION.md); do not reuse credentials or Hermes state from another project. Setup state persists in `jobsearch-assistant_job_agent_home`. Keep CVs, parsed profiles, and generated documents under `/opt/data/job-applications` in that volume, not in the repository.

## Verify

The skill is mounted read-only in Hermes's discovery directory. These one-shot commands verify discovery and exercise document handling with synthetic CV data without starting the gateway:

```sh
docker compose run --rm --no-deps job-agent skills list
docker compose run --rm --no-deps \
  --user hermes \
  --entrypoint /opt/job-docs-venv/bin/python job-agent \
  /opt/data/skills/linkedin-applications/scripts/test_application_docs.py
```

Confirm `linkedin-applications` is listed and enabled. For routine gateway lifecycle, backup, and restore procedures, see [operations](OPERATIONS.md).

## Operating Limits

Use the job bot only for career tasks and private chats. The model/provider may process CV contents, so review that disclosure before supplying personal documents. This package supports profile review and draft preparation only; live application submission is disabled because there is no durable job ledger and approval workflow.

The remote browser has its own session and vault; it does not share laptop cookies. Stop at CAPTCHA or identity verification for the user to complete in their own browser. Never use `docker compose down -v` for a routine restart because it removes the named volume. Docker administrators remain trusted; this is project and role separation, not multi-user hosting.

## Hermes Desktop and Bot Screen

Hermes Desktop connects to Hermes Dashboard on port `9119`. Do not use the OpenAI-compatible API server port `8642` for Desktop. Bot Screen's display and Chromium run in the Linux container on the remote host; the client computer is the authenticated viewer/controller. The remote screen is carried over the same authenticated dashboard connection, so do not publish a VNC port or create a separate VNC password.

### Image and resource requirements

The project pins `nousresearch/hermes-agent:v0.22.5-desktop` to its multi-architecture manifest digest in `.env.example`. The `-desktop` image is the same Hermes release as `v0.22.5`, with the Linux Xfce/TigerVNC packages needed by Bot Screen and the distro Chromium fallback preinstalled. Keep the Desktop suffix when changing image versions. If an existing local `.env` overrides `JOB_AGENT_BASE_IMAGE`, update it to the value in `.env.example` before building. The existing named volume retains configuration and credentials when the image is recreated; do not use `docker compose down -v`.

The Compose container limit is 4 GB RAM and 512 PIDs. A Linux host with at least 8 GB RAM is recommended when opening a headed browser during an agent run. Chromium can use substantially more memory than the idle gateway. Confirm available disk space before pulling the larger desktop image.

### Configure the gateway and Bot Screen on remote

Run the following on remote, from this project directory. Back up the Hermes volume before upgrading the image, especially if this deployment has already been used:

```sh
docker compose stop job-agent
mkdir -p backups
docker run --rm \
  -v jobsearch-assistant_job_agent_home:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.22 \
  sh -c 'tar -czf "/backup/job-agent-$(date +%F-%H%M%S).tar.gz" -C /data .'
docker compose build job-agent
docker compose up -d job-agent
```

The Dashboard listener is enabled by `HERMES_DASHBOARD=1` in Compose. It binds inside the container on `0.0.0.0:9119` so Docker can forward it, while the published host port is restricted to `127.0.0.1:9119`. The non-loopback container listener requires an auth provider; the following setup stores a password hash and a stable signing secret in `/opt/data/.env`, inside the persistent named volume.

Run this once on remote. It prompts for the dashboard username and password without echoing the password, creates a random signing secret only if one is not already present, preserves unrelated `.env` settings, and sets file mode `0600`:

```sh
docker compose stop job-agent
docker compose run --rm --no-deps \
  --entrypoint /opt/hermes/.venv/bin/python job-agent -c '
from getpass import getpass
import os
import secrets
from pathlib import Path
from plugins.dashboard_auth.basic import hash_password

username = input("Dashboard username: ").strip()
password = getpass("Dashboard password: ")
if not username or not password:
    raise SystemExit("A username and password are required")

env_file = Path("/opt/data/.env")
lines = env_file.read_text().splitlines() if env_file.exists() else []
keys = {
    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME",
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD",
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH",
    "HERMES_DASHBOARD_BASIC_AUTH_SECRET",
}
existing = {
    line.partition("=")[0].strip(): line.partition("=")[2]
    for line in lines if line.partition("=")[0].strip() in keys
}
lines = [line for line in lines if line.partition("=")[0].strip() not in keys]
values = {
    "HERMES_DASHBOARD_BASIC_AUTH_USERNAME": username,
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH": hash_password(password),
    "HERMES_DASHBOARD_BASIC_AUTH_SECRET": existing.get(
        "HERMES_DASHBOARD_BASIC_AUTH_SECRET", ""
    ) or secrets.token_hex(32),
}
lines.extend(f"{key}={value}" for key, value in values.items())
env_file.write_text("\n".join(lines) + "\n")
os.chmod(env_file, 0o600)
print("Dashboard credentials saved in the Hermes home volume.")
'
docker compose up -d job-agent
```

The stable `HERMES_DASHBOARD_BASIC_AUTH_SECRET` signs Desktop sessions. It is generated on first setup and preserved on subsequent runs of this procedure. Do not rotate or delete it unless you intend to sign out existing Desktop sessions. The password itself is stored as a scrypt hash, not plaintext.

Configure the profile's screen behavior in `/opt/data/config.yaml` through the Hermes Dashboard Config page or an interactive Hermes shell:

```yaml
bot_desktop:
  placement: gateway
  auto_start: false
browser:
  headed: true
  executable_path: /usr/bin/chromium
```

`placement: gateway` keeps the screen in this container because the job agent uses the local terminal backend. `auto_start: false` means no screen starts until you explicitly click Start screen or run the CLI command. `browser.headed: true` makes browser sessions visible on that screen. `browser.executable_path` selects the distro Chromium supplied by the `-desktop` image instead of Hermes' managed Chromium; this is the documented fallback when the managed browser reports `No usable sandbox`. Also ensure Computer Use is enabled for this profile in Hermes Desktop's Capabilities/Tools settings.

If the profile is already configured and the Bot Screen browser logs `zygote_host_impl_linux.cc:130 No usable sandbox`, apply the override on the remote host and restart the screen:

```sh
docker compose exec job-agent hermes config set browser.executable_path /usr/bin/chromium
docker compose exec job-agent hermes computer-use screen stop
docker compose exec job-agent hermes computer-use screen start
docker compose exec job-agent hermes computer-use screen status
```

If `/usr/bin/chromium` is missing, verify the running image is the pinned `v0.22.5-desktop` variant and recreate the service from the updated image. Do not add `--privileged` or weaken Docker's seccomp profile to work around Chromium sandbox startup.

Verify the image version, Dashboard authentication provider, and display packages on the remote:

```sh
docker compose exec job-agent hermes --version
curl -fsS http://127.0.0.1:9119/api/status
docker compose exec job-agent hermes computer-use screen status
```

The status response should report `auth_required: true` and a `basic` auth provider. Screen status should report the display stack as installed. Start the screen from the Desktop Screen pane or with `docker compose exec job-agent hermes computer-use screen start`.

### Connect Hermes Desktop on macOS

Use SSH forwarding so the dashboard is not exposed on the remote LAN interface. From a local client terminal, open a tunnel and leave that terminal running:

```sh
ssh -N -L 19119:127.0.0.1:9119 <linux-user>@remote
```

Replace `<linux-user>` with the SSH account on remote. If `remote` is not resolvable from the local, use its LAN or Tailscale hostname. The SSH account needs normal access to the remote; do not expose port `9119` publicly.

In Hermes Desktop on the Mac:

1. Open **Settings → Gateways** and add a **Remote gateway**.
2. Set the Remote URL to `http://127.0.0.1:19119`.
3. Choose **Sign in**, then enter the dashboard username and password configured above.
4. Save/connect, select the remote profile, and open its Screen pane. Start the screen if it is stopped, then test watch and takeover/hand-back.

The first successful sign-in creates the Desktop session credential automatically. Hermes Desktop stores it in the Mac's secure credential store and reuses it; there is no connection token to create, copy, or put in Compose. The backend signing secret in `/opt/data/.env` allows those signed sessions to remain valid across container restarts. Keep the SSH tunnel open while using the remote gateway and screen. `127.0.0.1` is treated as a secure browser context, which is required for the screen viewer.

### Troubleshooting and safety

- If Desktop reports no sign-in option, inspect `/api/status` and make sure `auth_providers` includes `basic`; confirm the container loaded the `.env` values and restart it after changing them.
- If the screen packages are missing, confirm the running image is `v0.22.5-desktop`, not the unsuffixed image, then rebuild/recreate the service.
- If the session is lost after every restart, ensure `HERMES_DASHBOARD_BASIC_AUTH_SECRET` remains in the persistent Hermes `.env` file.
- If the screen pane is unavailable over plain HTTP, check that Desktop is connected through the `127.0.0.1` SSH tunnel URL and that its local tunnel is still running.
- A headed browser can make a site visible, but it does not bypass Cloudflare, CAPTCHAs, identity checks, or site safeguards. Stop and take over manually where required by the job workflow.
- Never expose the dashboard directly to the public internet with only username/password authentication. For public access, use an approved OAuth/OIDC provider; for this nuc2 homelab, keep access on SSH or a trusted VPN.

#### Browser startup issue
The default browser - chromium - would not start from the desktop menu. Starting it from a terminal produces "No sandbox" error. Prevented by Docker security settings and AppArmor, Chromium cannot use its sandbox feature enabled by default from within the container. All browser based tasks will fail. Solution: use `no-sandbox` option.

For persistance create `config/chromium.d/no-sandbox` with `no-sandbox` and mount it into agent as a volume (update compose.yaml).
Recreate the container so the new mount takes effect: `docker compose up -d --force-recreate job0agent`.

Another issue: the agent uses its own Chromium profile, different from the one used by the browser started interactively. Solution: set on `browser.use_real_profile` option, easiest - in the dashboard.

When the agent initialized the browser session the screen control must be on agent's side.