FROM python:3.11-slim

# Install system dependencies including those required by Zendriver/Chromium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    xvfb \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv compiler
RUN pip install uv

# Copy requirements and install via uv to system python
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy backend codebase
COPY . .

# Set necessary environment variables for headless Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/lib/chromium/
ENV PYTHONUNBUFFERED=1

# Default port for FastAPI
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
