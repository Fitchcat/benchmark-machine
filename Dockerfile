FROM python:3.11-slim

WORKDIR /app

# Upgrade pip and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium and its system dependencies
RUN playwright install chromium && \
    playwright install-deps chromium

# Copy the rest of the application
COPY . .

# Expose port (Render sets $PORT dynamically, but typically uses 10000 for Docker)
EXPOSE 10000

# Command to run the app using gunicorn
CMD gunicorn --bind 0.0.0.0:${PORT:-10000} app:app
