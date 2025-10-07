# Use lightweight Python 3.10 image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy dependency list first (for layer caching)
COPY requirements.txt .

# Install required tools and Python dependencies
RUN apt-get update && apt-get install -y git curl && \
    pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Hugging Face expects an exposed port even if we don't serve a web app
ENV PORT=7860
EXPOSE 7860

# Run your main script on container start
CMD ["python", "main.py"]
