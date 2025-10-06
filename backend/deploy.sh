#!/bin/bash

# GCP Deployment Script for I Get Happy Chatbot
# This script deploys the chatbot to Google Cloud Run

set -e

# Configuration
PROJECT_ID="igethappy-dev"
SERVICE_NAME="igethappy-chatbot"
REGION="us-central1"
IMAGE_NAME="us-central1-docker.pkg.dev/$PROJECT_ID/$SERVICE_NAME/$SERVICE_NAME"

echo "🚀 Starting deployment of I Get Happy Chatbot to GCP..."

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed. Please install it first."
    exit 1
fi

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "❌ Not authenticated with gcloud. Please run 'gcloud auth login' first."
    exit 1
fi

# Set the project
echo "📋 Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "🔧 Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com

# Build and push the Docker image
echo "🐳 Building and pushing Docker image..."
gcloud builds submit --tag $IMAGE_NAME .

# Deploy to Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --platform managed \
    --port 8080 \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 0 \
    --max-instances 10 \
    --set-env-vars "DATABASE_URL=postgresql+asyncpg://postgres:aktmar@/mental_health_app?host=/cloudsql/igethappy-dev:us-central1:igethappy-main-db" \
    --set-secrets INTERNAL_API_KEY=internal-api-key:latest \
    --add-cloudsql-instances "igethappy-dev:us-central1:igethappy-main-db"

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")

echo "✅ Deployment completed successfully!"
echo "🌐 Service URL: $SERVICE_URL"
echo ""
echo "📝 Next steps:"
echo "1. Frontend: set PRIMARY_API_BASE to your Node URL, BACKUP_API_BASE to Node Cloud Run."
NODE_SERVICE="iguh-backend"
NODE_URL=$(gcloud run services describe "$NODE_SERVICE" --region=$REGION --format="value(status.url)" 2>/dev/null || true)
if [ -n "$NODE_URL" ]; then
  echo "   Flutter example:"
  echo "   flutter run -d chrome \\\" 
  echo "     --dart-define=PRIMARY_API_BASE=http://localhost:3000 \\\" 
  echo "     --dart-define=BACKUP_API_BASE=$NODE_URL"
else
  echo "   Could not find Node service '$NODE_SERVICE' in $REGION. Configure BACKUP_API_BASE manually."
fi
echo "2. Test the authentication endpoints"
echo "3. Set up a custom domain if needed"
echo ""
echo "🔗 API Endpoints:"
echo "- Health: $SERVICE_URL/health"
echo "- Register: $SERVICE_URL/api/auth/register"
echo "- Login: $SERVICE_URL/api/auth/login"
echo "- Chat: $SERVICE_URL/api/ai/chat"
