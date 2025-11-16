# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy everything into container
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port for Flask
EXPOSE 8000

# Set environment variables (optional defaults)
ENV PYTHONUNBUFFERED=1

# Command to run your app
CMD ["python", "flask_server.py"]
