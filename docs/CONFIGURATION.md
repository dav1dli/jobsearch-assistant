# Configuration
## initial configuration
```
docker compose run --rm --no-deps job-agent setup
```
Options:
* Full setup
* Provider: Azure Foundry
  * API Endpoint: https://***.services.ai.azure.com/anthropic
  * Key: F2G2NK***
  * default model: claude-opus-5-5
  * Reasoning: medium
* Terminal backend: local
* Egress firewall: No
* Message platforms: Telegram: Manual bot
  * Bot: t.me/cemahshabadbot
  * User: 628997725
* Search: DuckDuckGo


## Isolation model

This project runs its own Hermes container and named home volume (`jobsearch-assistant_job_agent_home`). The only host-mounted project files are the read-only job policy and LinkedIn skill. Its `job_egress` bridge provides outbound access; it is not a destination allowlist or a complete network sandbox. Docker administrators remain trusted.

The Hermes home at `/opt/data` stores configuration, sessions, memory, browser state, and credentials created by setup. Keep employment data under `/opt/data/job-applications`; do not put CVs or job history in this repository, Telegram groups, or the health assistant.

## Search preferences

Role and location defaults are stored in the Git-ignored local file `private/job-search-preferences.yaml`. Compose mounts it read-only and Docker excludes it from the image build context. Copy `config/job-search-preferences.example.yaml` to that path and edit its `role_families` and `locations` lists:

```sh
mkdir -p private
cp -n config/job-search-preferences.example.yaml private/job-search-preferences.yaml
```

Compose mounts the local file read-only at `/workspace/job-search-preferences.yaml` and sets `JOB_SEARCH_PREFERENCES_FILE` to that path. The `private/` directory is Git-ignored; do not move personal preferences into the example template or skill. For each task, explicit criteria from the user override these defaults. Empty lists require asking the user; stored preferences do not authorize application submission.

## Credentials and Telegram

- Create a new Telegram bot for this agent.
- Use the interactive `hermes setup` wizard to configure the job bot and a separate model/provider credential.
- Restrict Telegram to your numeric user ID. The user allowlist also authorizes that account in groups; it is not a DM-only control. Disable group invitations for the bot in BotFather and do not add it to groups.
- Never put bot tokens, model keys, passwords, or one-time codes in this repository, command arguments, or chat with the agent.
- The model/provider may receive CV contents. Review that disclosure before supplying personal documents.

### Manual Telegram bot configuration

This procedure configures Telegram only. Configure a separate model/provider credential with `hermes setup` if one is not already present.

1. In Telegram, open [@BotFather](https://t.me/BotFather), run `/newbot`, and follow its prompts. Copy the token privately. Then run `/setjoingroups`, select the new bot, and disable group invitations.
2. Obtain your own numeric Telegram user ID from a source you trust. Do not use a bot token or username in place of this ID.
3. Use the manual configuration procedure below to enter the token and numeric ID into the Hermes home volume. The token is prompted without echo and is not placed in a command argument or this repository.
4. Start the gateway and check its status and logs using the [operations guide](OPERATIONS.md). Send the bot a private message from the allowed account to verify access. Do not print or share the contents of `/opt/data/.env`.

If the token is exposed, revoke it through BotFather and replace it in the Hermes home `.env` file. Do not configure `TELEGRAM_ALLOW_ALL_USERS`.

## Bot Screen and Desktop gateway

Bot Screen runs the remote browser/display on the Linux gateway, not on the Mac. This project pins the matching `v0.22.5-desktop` image, which includes the Linux display stack and headed Chromium. The matching non-desktop image does not include all Bot Screen system packages. The Compose service enables Hermes Dashboard on port `9119`; Desktop uses this authenticated dashboard connection, not the OpenAI-compatible API server on port `8642`.

For Bot Screen configuration and the complete nuc2-to-macOS connection procedure, see [Standalone Deployment](DEPLOYMENT.md#hermes-desktop-and-bot-screen).

## Image version

`.env.example` pins Hermes v0.22.5-desktop to the verified multi-architecture image digest. The `-desktop` variant is required for Bot Screen's Linux display packages; keep this suffix when upgrading. Copy the example to `.env` only if you need a local override, and keep `JOB_AGENT_BASE_IMAGE` pointed at the matching desktop variant. Verify the digest and compatibility before rebuilding and operating the gateway.

The derived image installs the pinned Python dependencies in a dedicated virtual environment. Skill code is mounted read-only from this project; private CVs and generated material stay in the named volume.

## Supported document inputs

DOCX, Markdown (`.md`/`.markdown`), plain text, and selectable-text PDF are supported. Image-only PDFs are rejected; OCR must be performed locally and reviewed against the source before importing. Source hashes and paragraph/line/page locators are retained in the parsed profile.
