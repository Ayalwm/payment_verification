FROM python:3.13-slim-buster

WORKDIR /app

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
    pkg-config \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    zlib1g-dev \
    libffi-dev \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Run ldconfig to update the dynamic linker cache after installing new libraries
RUN ldconfig

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
