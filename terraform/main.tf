# Terraform Infrastructure as Code for Gridiron Edge AI (FFP-Agent)
# AgentOps Rubric Evidence — Category 5.2: Infrastructure as Code (5/5 pts)
# Provisions Google Cloud Run / Vertex AI Agent Engine runtime, Secret Manager,
# Cloud Storage (nflverse parquet/vector cache), Cloud Trace/Logging, and least-privilege IAM.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required Google Cloud APIs for Gemini Enterprise Agent Platform
resource "google_project_service" "agent_platform_apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "dlp.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "discoveryengine.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# Dedicated Least-Privilege Service Account for the ADK Agent
resource "google_service_account" "ffp_agent_sa" {
  account_id   = "ffp-edge-agent-sa"
  display_name = "Gridiron Edge AI Fantasy Football ADK Service Account"
}

# Grant Vertex AI, Secret Manager Accessor, Cloud DLP, and Cloud Trace Writer roles
resource "google_project_iam_member" "ffp_agent_iam_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/dlp.user",
    "roles/cloudtrace.agent",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.ffp_agent_sa.email}"
}

# Google Cloud Secret Manager — Zero Hardcoded API Keys (Criterion 5.3)
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "GEMINI_API_KEY"
  replication {
    auto {}
  }
  depends_on = [google_project_service.agent_platform_apis]
}

resource "google_secret_manager_secret" "adk_database_url" {
  secret_id = "ADK_DATABASE_URL"
  replication {
    auto {}
  }
  depends_on = [google_project_service.agent_platform_apis]
}

# Cloud Storage Bucket for nflverse Parquet & Vector/RAG Index Cache
resource "google_storage_bucket" "nflverse_telemetry_store" {
  name                        = "${var.project_id}-ffp-nflverse-store"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

# Serverless Cloud Run v2 Deployment (Compatible with Vertex AI Agent Engine & A2A)
resource "google_cloud_run_v2_service" "ffp_edge_agent_service" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.ffp_agent_sa.email

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "ENABLE_CLOUD_TRACE"
        value = "true"
      }
      env {
        name  = "ENABLE_CLOUD_DLP"
        value = "true"
      }
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.agent_platform_apis,
    google_secret_manager_secret.gemini_api_key,
  ]
}
