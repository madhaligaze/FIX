FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY Backend-AI/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY Backend-AI /app/Backend-AI

EXPOSE 8000

WORKDIR /app/Backend-AI

CMD ["python","-m","uvicorn","main:create_app","--factory","--host","0.0.0.0","--port","8000"]
