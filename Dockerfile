# Use a slim Python image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install dependencies
# We copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the script into the container
COPY script.py .

# Unbuffer output for better logging in Docker
ENV PYTHONUNBUFFERED=1

# Run the script
CMD ["python", "script.py"]
