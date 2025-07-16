FROM python:3.13-buster

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    # Re-adding Zbar libraries
    libzbar0 \
    libzbar-dev \
    zbar-tools \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    zlib1g-dev \
    libffi-dev \
    libatlas-base-dev \
    libopencv-dev \
    libnss3 \
    libfontconfig1 \
    libgconf-2-4 \
    libgtk-3-0 \
    libasound2 \
    libatk-bridge2.0-0 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm-dev \
    libxshmfence-dev \
    libglib2.0-0 \
    libdbus-1-3 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxi6 \
    libxtst6 \
    curl \
    dumb-init \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps

COPY . .

EXPOSE 8000

# Healthcheck to tell Docker/Render when the service is ready
HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
    CMD curl --fail http://localhost:$PORT/ || exit 1

# Use dumb-init and a short sleep before starting Uvicorn, explicitly binding to 0.0.0.0
CMD ["dumb-init", "--", "bash", "-c", "sleep 1 && uvicorn main:app --hos