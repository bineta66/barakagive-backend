FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    proj-bin \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker/entrypoint.sh

CMD ["sh", "docker/entrypoint.sh"]
