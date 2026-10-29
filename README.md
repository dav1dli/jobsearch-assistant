# Job Search Assistant

A standalone Hermes instance for employment and job-search tasks. It has its own Docker Compose project, persistent home, Telegram configuration, model credentials, network, and LinkedIn applications skill. It is not connected to the Health Assistant project or its data, networks, credentials, or persistent volumes.

The deployment is intentionally separate. Do not copy medical-agent configuration or reuse its Telegram bot. The job agent currently prepares and reviews drafts only; live application submission is disabled because no durable application ledger and approval workflow exists.

## Start here

1. Read [configuration](docs/CONFIGURATION.md) and [deployment](docs/DEPLOYMENT.md).
2. Configure a dedicated Telegram bot and model credential with the interactive Hermes setup, or follow the manual Telegram procedure in [configuration](docs/CONFIGURATION.md).
3. Start and verify the gateway using the [operations guide](docs/OPERATIONS.md).

## Project contents

- `compose.yaml`: standalone gateway, private named volume, and dedicated egress network.
- `.dockerignore`: excludes local preferences and generated/private data from image builds.
- `Dockerfile`: pinned Hermes base with the CV document-processing dependencies.
- `config/job-search-preferences.example.yaml`: blank template for local, Git-ignored role and location defaults.
- `hermes/instructions/JOB-AGENT.md`: job-only agent policy.
- `skills/linkedin-applications/`: employment workflow, references, importer, and synthetic tests.
- `docs/`: configuration, deployment, and operations instructions.

CV parsing supports DOCX, Markdown/text, and selectable-text PDF. Image-only PDFs require local OCR and human review before import. Provider/model services may process CV contents, so only provide documents after reviewing that disclosure.
