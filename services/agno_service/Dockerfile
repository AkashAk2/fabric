FROM python:3.11-slim

# System deps (wheels usually cover lxml/Pillow, but keep minimal build tools handy if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -r requirements.txt

# Add app
COPY app.py /app/app.py
# Copy your .env at runtime via volume or Docker secret; don't bake secrets in images.

# Expose service
EXPOSE 9000

# Uvicorn server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
