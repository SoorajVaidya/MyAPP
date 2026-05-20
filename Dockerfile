# Use the official Python image from Docker Hub
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=oohy_product.settings

# Install system and build dependencies
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    gcc \
    build-essential \
    python3-dev \
    python3-wheel \
    default-libmysqlclient-dev \
    pkg-config \
    git \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


# Set working directory
WORKDIR /app

# Copy requirements.txt for dependency installation
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install git+https://github.com/deeplook/svglib.git@main \
    && pip install gunicorn uvicorn[standard] locust

# Copy the rest of the application files
COPY . .

# Create staticfiles directory and set permissions
RUN mkdir -p /app/staticfiles \
    && chmod -R 777 /app/staticfiles \
    && chown -R 1000:1000 /app

# Create a non-root user and switch to it
RUN useradd -m -u 1000 myuser
USER myuser

# Run Django collectstatic
RUN python manage.py collectstatic --noinput

# Expose ports for Django and Locust
EXPOSE 8000 8089

# Default entrypoint runs the API. Worker processes use the same image but
# override the command — for example, in docker-compose or k8s:
#
#   command: ["python", "manage.py", "run_pulse_worker", "signal"]
#   command: ["python", "manage.py", "run_pulse_worker", "report"]
#
# Don't run workers inside the API container — ProcessPool fork() collides
# with Gunicorn's pre-forked workers.
CMD ["gunicorn", "--workers=4", "--threads=2", "--timeout=120", "oohy_product.wsgi:application", "--bind", "0.0.0.0:8000"]


