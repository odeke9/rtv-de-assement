FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV RTV_DATA_DIR=/data RTV_LAKE_DIR=/app/lake
EXPOSE 8501
CMD ["sh", "-c", "python -m pipeline.run && streamlit run dashboards/app.py --server.address 0.0.0.0"]
