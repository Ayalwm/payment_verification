FROM python:3.13-buster

WORKDIR /app

# Install system dependencies required for Playwright and zbar
# 'buster' image is fuller, so fewer explicit installs might be needed,
# but we keep essential ones for Playwright and zbar-tools.
RUN apt-get update && apt-get install -y \
    build-essential \
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
    zbar-tools \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# No need for ldconfig or LD_LIBRARY_PATH with a fuller base image, generally.

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
