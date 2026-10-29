ARG HERMES_BASE_IMAGE=nousresearch/hermes-agent:v0.22.5-desktop@sha256:04f7a36d125bc3ebdef090cd5cf0cccaa74699e5a1a77c2965a4db437f24bf13
FROM ${HERMES_BASE_IMAGE}

EXPOSE 9119

COPY skills/linkedin-applications/scripts/requirements.txt /tmp/job-docs-requirements.txt
COPY scripts/entrypoint.sh /opt/job-agent-entrypoint.sh
RUN /opt/hermes/.venv/bin/python -m venv /opt/job-docs-venv \
    && /opt/job-docs-venv/bin/python -m pip install --no-cache-dir -r /tmp/job-docs-requirements.txt \
    && rm /tmp/job-docs-requirements.txt \
    && chmod 0755 /opt/job-agent-entrypoint.sh

ENV JOB_DOCS_PYTHON=/opt/job-docs-venv/bin/python \
    JOB_DOCS_SCRIPT=/opt/data/skills/linkedin-applications/scripts/application_docs.py \
    JOB_APPLICATION_HOME=/opt/data/job-applications