FROM python:3.12-slim

WORKDIR /workspace/mcp
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .

EXPOSE 8000
CMD ["python", "server.py"]
