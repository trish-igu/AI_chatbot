# GCP Deployment Guide for I Get Happy Chatbot

This guide will help you deploy the chatbot to Google Cloud Platform so users in Texas and California can access it with optimal performance.

## 🌍 **Deployment Architecture**

```
Internet → Cloud Run → Cloud SQL (PostgreSQL) → Secret Manager
    ↓
Cloud Build → Container Registry
```

## 📋 **Prerequisites**

1. **Google Cloud Account** with billing enabled
2. **gcloud CLI** installed and configured
3. **Docker** installed locally
4. **Domain name** (optional, for custom domain)

## 🚀 **Step-by-Step Deployment**

### 1. **Set up GCP Project**

```bash
# Set your project ID
export PROJECT_ID="igethappy-dev"
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

### 2. **Configure Database**

```bash
# Create Cloud SQL instance (if not exists)
gcloud sql instances create igethappy-main-db \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=us-central1 \
    --storage-type=SSD \
    --storage-size=10GB

# Create database
gcloud sql databases create mental_health_app \
    --instance=igethappy-main-db

# Create user
gcloud sql users create postgres \
    --instance=igethappy-main-db \
    --password=your_secure_password
```

### 3. **Set up Secret Manager**

```bash
# Store database URL
echo "postgresql+asyncpg://postgres:your_secure_password@/mental_health_app?host=/cloudsql/igethappy-dev:us-central1:igethappy-main-db" | \
gcloud secrets create database-url --data-file=-

# Store Azure OpenAI API key
echo "your_azure_openai_api_key" | \
gcloud secrets create azure-openai-api-key --data-file=-

# Store Azure OpenAI endpoint
echo "https://your-resource.openai.azure.com/" | \
gcloud secrets create azure-openai-endpoint --data-file=-

# Store Azure OpenAI deployment name
echo "your_deployment_name" | \
gcloud secrets create azure-openai-deployment-name --data-file=-
```

### 4. **Deploy to Cloud Run**

```bash
# Make deploy script executable
chmod +x deploy.sh

# Deploy the application
./deploy.sh
```

### 5. **Configure Custom Domain (Optional)**

```bash
# Map custom domain to Cloud Run service
gcloud run domain-mappings create \
    --service=igethappy-chatbot \
    --domain=your-domain.com \
    --region=asia-south1
```

## 🔧 **Configuration Files**

### **Dockerfile**
- Multi-stage build for optimized container size
- Non-root user for security
- Health check endpoint
- Proper port exposure

### **cloudbuild.yaml**
- Automated build and deployment
- Container registry push
- Cloud Run deployment with proper configuration
- Environment variables and Cloud SQL connection

### **deploy.sh**
- One-command deployment script
- API enablement
- Service configuration
- URL output for testing

## 🌐 **Accessing the Application**

After deployment, you'll get a URL like:
```
https://igethappy-chatbot-xxxxx-uc.a.run.app
```

### **API Endpoints:**
- **Health Check**: `GET /health`
- **Register**: `POST /api/auth/register`
- **Login**: `POST /api/auth/login`
- **Profile**: `GET /api/auth/me`
- **Update Profile**: `PUT /api/auth/profile`
- **Chat**: `POST /api/ai/chat`

## 🔒 **Security Features**

1. **JWT Authentication** - Secure token-based auth
2. **Password Hashing** - bcrypt for password security
3. **CORS Configuration** - Proper cross-origin setup
4. **Secret Management** - GCP Secret Manager integration
5. **HTTPS Only** - Cloud Run enforces HTTPS
6. **Non-root Container** - Security best practices

## 📊 **Monitoring & Logging**

### **Cloud Logging**
```bash
# View application logs
gcloud logging read "resource.type=cloud_run_revision" --limit=50
```

### **Cloud Monitoring**
- Set up alerts for error rates
- Monitor response times
- Track user registrations and logins

## 💰 **Cost Optimization**

### **Cloud Run**
- **Min instances**: 0 (scales to zero when not used)
- **Max instances**: 10 (adjust based on traffic)
- **Memory**: 2GB (sufficient for the application)
- **CPU**: 2 cores

### **Cloud SQL**
- **Instance type**: db-f1-micro (development)
- **Storage**: 10GB SSD
- **Backup**: Automated daily backups

### **Estimated Monthly Cost (US)**
- Cloud Run: ~$5-15 (based on usage)
- Cloud SQL: ~$10-20
- **Total**: ~$15-35/month

## 🚀 **Scaling for Production**

### **High Traffic Setup**
```bash
# Update Cloud Run configuration
gcloud run services update igethappy-chatbot \
    --region=us-central1 \
    --min-instances=1 \
    --max-instances=100 \
    --memory=4Gi \
    --cpu=4
```

### **Database Scaling**
```bash
# Upgrade to higher tier
gcloud sql instances patch igethappy-main-db \
    --tier=db-n1-standard-1
```

## 🔄 **Continuous Deployment**

### **GitHub Actions Integration**
```yaml
# .github/workflows/deploy.yml
name: Deploy to GCP
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: google-github-actions/setup-gcloud@v0
      - run: gcloud builds submit --config cloudbuild.yaml
```

## 🛠️ **Troubleshooting**

### **Common Issues**

1. **Database Connection Issues**
   ```bash
   # Check Cloud SQL instance status
   gcloud sql instances describe igethappy-main-db
   ```

2. **Authentication Errors**
   ```bash
   # Check secret values
   gcloud secrets versions access latest --secret="azure-openai-api-key"
   ```

3. **Container Build Issues**
   ```bash
   # Build locally to test
   docker build -t test-image .
   docker run -p 8000:8000 test-image
   ```

## 📱 **Frontend Deployment**

### **Streamlit Cloud (Recommended)**
1. Push code to GitHub
2. Connect to Streamlit Cloud
3. Update API URL in frontend code
4. Deploy with one click

### **Alternative: Cloud Run Frontend**
```bash
# Deploy frontend as separate service
gcloud run deploy igethappy-frontend \
    --source=frontend/ \
    --region=us-central1 \
    --allow-unauthenticated
```

## 🌍 **Global Access**

The application will be accessible from anywhere in the world, with:
- **Low latency** for users in Texas and California (US-Central1 region)
- **HTTPS encryption** for secure communication
- **Auto-scaling** based on demand
- **99.9% uptime** SLA with Cloud Run

## 📞 **Support**

For issues or questions:
1. Check Cloud Logging for errors
2. Monitor Cloud Run metrics
3. Verify database connectivity
4. Test API endpoints manually

## 🎯 **Next Steps**

1. **Deploy the application** using the deploy script
2. **Test all endpoints** to ensure functionality
3. **Set up monitoring** and alerts
4. **Configure custom domain** if needed
5. **Set up CI/CD** for automated deployments
6. **Monitor usage** and optimize costs

Your chatbot will be live and accessible to users in Texas, California, and around the world! 🚀
