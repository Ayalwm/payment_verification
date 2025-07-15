FROM python:3.13-buster

WORKDIR /app

ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=$PORT

RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
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
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$PORT"]
FROM python:3.13-buster

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
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

# Explicitly pass host and port to Uvicorn in CMD using shell form
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
