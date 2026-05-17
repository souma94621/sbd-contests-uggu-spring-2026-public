# АБУ (исходная точка src_starting_point)
FROM python:3.12-slim
WORKDIR /app
COPY src_starting_point/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY src_starting_point /app
ENV PYTHONPATH=/app
EXPOSE 8081
CMD ["uvicorn", "abu.app:app", "--host", "0.0.0.0", "--port", "8081"]
