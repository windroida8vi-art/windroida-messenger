FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 CD_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m -u 10001 drive && mkdir /data && chown drive /data
USER drive
EXPOSE 8083
VOLUME /data
HEALTHCHECK CMD python -c "import urllib.request as u;u.urlopen('http://127.0.0.1:8083/api/health')" || exit 1
CMD ["python", "wsgi.py"]
