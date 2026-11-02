# Install uv
FROM python:3.12-slim

# Copy uv binary
COPY --from=ghcr.io/astral-sh/uv:0.7.4 /uv /bin/uv

# Change the working directory to the `app` directory
WORKDIR /app

# Copy the lockfile, `pyproject.toml` and the README into the image
COPY uv.lock /app/uv.lock
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md

# Install dependencies (--no-dev skips local-only tools like streamlit)
RUN uv sync --frozen --no-dev --no-install-project

# Copy the up_api folder into the image
COPY up_api /app/up_api

# Sync the project
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "up_api.main:app", "--host", "0.0.0.0", "--port", "5000"]
