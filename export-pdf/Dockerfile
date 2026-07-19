# M1-X2: LibreOffice DOCX→PDF converter (arm64 Lambda container).
# Separate from the zip API Lambda so LO + fonts never hit the 250MB zip limit.
FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm

ENV LAMBDA_TASK_ROOT=/var/task
WORKDIR ${LAMBDA_TASK_ROOT}

# writer-nogui is enough for DOCX→PDF; fontconfig refreshes after we drop Civil1 fonts.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        libreoffice-java-common \
        default-jre-headless \
        fontconfig \
        fonts-liberation \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY fonts/ /usr/share/fonts/truetype/civil1/
RUN fc-cache -f \
    && python -m pip install --no-cache-dir awslambdaric boto3 \
    && mkdir -p /tmp \
    && chmod 1777 /tmp

COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

ENV HOME=/tmp \
    SAL_USE_VCLPLUGIN=svp \
    CIVILAI_SOFFICE=soffice

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.handler"]
