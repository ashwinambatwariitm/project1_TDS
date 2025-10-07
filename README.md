---
title: Project1 TDS Docker Deployment
emoji: 🐳
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
---

# Project1: Tabular Data Service (TDS) Deployment

This repository contains a Python application designed for a Tabular Data Service (TDS), deployed using a custom Docker container on Hugging Face Spaces.

## Project Structure

* `main.py`: The main application entry point, likely exposing a web service (e.g., using FastAPI or Flask).
* `Dockerfile`: Defines the custom container environment, including the Python base image, dependency installation, and startup command.
* `requirements.txt`: Lists all necessary Python packages.
* `repo_utils.py`: Utility functions for the application.
* `sample_request.json`: An example JSON payload for testing the API endpoint.

## Deployment Details

This application is deployed on Hugging Face Spaces using the **Docker SDK**.

* **SDK:** `docker`
* **Port:** The container is exposed on port `7860`, which is required for Hugging Face Spaces. The internal server must be configured to bind to `0.0.0.0:7860`.

## How to Test

Once the Space is built and running (check the **Logs** tab):

1.  Navigate to the **App** tab on the Hugging Face Space page.
2.  If this is an API, you can access the `/docs` or `/redoc` endpoint (if using FastAPI/Swagger) to interact with the service.
3.  Alternatively, use a tool like cURL or Postman to send requests to the public URL of the Space.
