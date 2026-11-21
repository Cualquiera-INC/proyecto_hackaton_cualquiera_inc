FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY servicio_pedidos.py /app/servicio_pedidos.py
# Versión del código; scripts/desplegar.py la pasa con --build-arg (misma que app1/app2).
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} PYTHONUNBUFFERED=1 PORT=8081
USER 10001
EXPOSE 8081
CMD ["python", "servicio_pedidos.py"]
