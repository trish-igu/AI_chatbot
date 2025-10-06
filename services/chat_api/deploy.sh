#!/bin/bash
set -e

PROJECT_ID="igethappy-dev"
SERVICE_NAME="igethappy-chat-api"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "🚀 Deploying $SERVICE_NAME to Cloud Run..."

gcloud services enable cloudbuild.googleapis.com run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com

gcloud builds submit --tag $IMAGE_NAME .

gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8000 \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars "DATABASE_URL=postgresql+asyncpg://postgres:aktmar@/mental_health_app?host=/cloudsql/igethappy-dev:us-central1:igethappy-main-db" \
  --add-cloudsql-instances "igethappy-dev:us-central1:igethappy-main-db"

SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")
echo "✅ Deployment completed successfully!"
echo "🌐 Service URL: $SERVICE_URL"


