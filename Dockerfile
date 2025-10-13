# Use lightweight Python 3.10 image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy dependency list first (for layer caching)
COPY requirements.txt .

# Install required tools and Python dependencies
RUN apt-get update && apt-get install -y git curl gnupg lsb-release ca-certificates && \
    # --- START: GitHub CLI (gh) Installation ---
    # Add GitHub CLI GPG key
    mkdir -p -m 755 /etc/apt/keyrings && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null && \
    \
    # Add GitHub CLI repository to APT sources
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    \
    # Install gh and Python requirements
    apt-get update && \
    apt-get install -y gh && \
    # --- END: GitHub CLI (gh) Installation ---
    pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Hugging Face expects an exposed port even if we don't serve a web app
ENV PORT=7860
EXPOSE 7860

# Run your main script on container start
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
