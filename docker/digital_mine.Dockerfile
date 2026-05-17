# Цифровой рудник (ЦР)
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0,<0.116" \
    "uvicorn[standard]>=0.32.0,<0.33" \
    "pydantic>=2.10.0,<3" \
    "httpx>=0.27.0,<0.29"
COPY external_systems/digital_mine/digital_mine /app/digital_mine
ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["uvicorn", "digital_mine.main:app", "--host", "0.0.0.0", "--port", "8080"]
