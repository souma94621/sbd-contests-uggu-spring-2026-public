# Регулятор: REST API сертификации АБУ
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0,<0.116" \
    "uvicorn[standard]>=0.32.0,<0.33" \
    "pydantic>=2.10.0,<3" \
    "httpx>=0.27.0,<0.29" \
    "python-multipart>=0.0.9,<0.1"
COPY external_systems/regulator/regulator /app/regulator
ENV PYTHONPATH=/app
EXPOSE 8082
CMD ["uvicorn", "regulator.main:app", "--host", "0.0.0.0", "--port", "8082"]
