#!/bin/sh
set -eu

mkdir -p /opt/data/skills
chown 10000:10000 /opt/data/skills
chmod 0755 /opt/data/skills

exec /opt/hermes/docker/entrypoint-dispatch.sh "$@"