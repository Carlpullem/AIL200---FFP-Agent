output "agent_service_url" {
  description = "Public HTTPS endpoint for the Gridiron Edge AI War Room & A2A Server"
  value       = google_cloud_run_v2_service.ffp_edge_agent_service.uri
}

output "agent_service_account_email" {
  description = "Least-privilege IAM service account email for the ADK agent"
  value       = google_service_account.ffp_agent_sa.email
}

output "nflverse_cache_bucket" {
  description = "GCS bucket storing nflverse play-by-play and RAG embeddings"
  value       = google_storage_bucket.nflverse_telemetry_store.url
}
