# Operations

## Lifecycle

```sh
# Start

docker compose up -d job-agent

# Inspect status and logs
docker compose ps
docker compose logs --tail=100 job-agent

# Restart without deleting state
docker compose restart job-agent

# Stop while retaining state
docker compose stop job-agent
```

Routine stop/restart operations do not erase configuration, browser state, or job data. Never use `docker compose down -v` unless you intentionally want to delete the named Hermes home.

## Configuration changes

Stop the gateway before rerunning the setup wizard so only one process writes to its Hermes home:

```sh
docker compose stop job-agent
docker compose run --rm --no-deps job-agent setup
docker compose up -d job-agent
```

Do not edit live session databases or copy secrets into the project. Rebuild after changing the Dockerfile, dependency pins, or base-image pin:

```sh
docker compose build --pull job-agent
docker compose up -d --no-deps job-agent
```

## Backup and restore

Back up the named volume while the gateway is stopped. Create a local backup directory first; it is ignored by Git.

```sh
docker compose stop job-agent
mkdir -p backups
docker run --rm \
  -v jobsearch-assistant_job_agent_home:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.22 \
  sh -c 'tar -czf "/backup/job-agent-$(date +%F-%H%M%S).tar.gz" -C /data .'
```

Store backups encrypted and access-restricted because they contain credentials, CVs, sessions, and browser state. For restore, stop the gateway, preserve a copy of the current volume, restore the archive into the named volume using a trusted maintenance container, then verify setup and skill discovery before restarting. Do not restore this volume into the health-assistant project.

## Application safety

The skill currently supports profile review and draft preparation only. Do not submit applications: there is no durable ledger for per-job approval, document hashes, form answers, destination confirmation, or duplicate checks. Stop at CAPTCHA, security checks, legal attestations, unsupported forms, or uncertain work authorization. Do not bypass platform safeguards.
