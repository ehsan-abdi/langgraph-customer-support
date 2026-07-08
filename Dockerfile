# Stage 1: Build the React frontend
FROM node:20-slim AS builder
WORKDIR /app/web

# Install dependencies
COPY web/package.json web/package-lock.json* ./
RUN npm install

# Copy source and build
COPY web/ ./
RUN npm run build

# Stage 2: Build the FastAPI backend
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application data and source
COPY src/ ./src/
COPY data/ ./data/
COPY db/ ./db/

# Copy the built frontend from Stage 1
COPY --from=builder /app/web/dist ./web/dist

# Set Python path to ensure module imports work
ENV PYTHONPATH=/app

# Expose the API and UI port
EXPOSE 8000

# Start the FastAPI server
CMD ["python", "src/langgraph_app/api/server.py"]
