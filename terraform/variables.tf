variable "project_id" {
  description = "Google Cloud Project ID hosting the Gemini Enterprise Agent Platform deployment"
  type        = string
}

variable "region" {
  description = "Google Cloud Region for Vertex AI Agent Engine and Cloud Run"
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Name of the deployed Gridiron Edge AI agent service"
  type        = string
  default     = "gridiron-edge-ffp-agent"
}

variable "container_image" {
  description = "Artifact Registry container image URI for the ADK agent"
  type        = string
  default     = "us-central1-docker.pkg.dev/my-gcp-project/agents/ffp-edge-agent:latest"
}
