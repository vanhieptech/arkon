variable "aws_region" {
  type        = string
  description = "AWS region (Bedrock model access must exist here)."
  default     = "ap-southeast-1"
}

variable "project_name" {
  type        = string
  description = "Prefix for resource names."
  default     = "arkon"
}

variable "instance_type" {
  type    = string
  default = "t3.xlarge"
}

variable "key_name" {
  type        = string
  description = "Existing EC2 key pair name for SSH."
}

variable "ssh_cidr" {
  type        = string
  description = "CIDR allowed to SSH (your public IP/32 recommended)."
  default     = "0.0.0.0/0"
}

variable "arkon_repo_url" {
  type        = string
  description = "Git URL to clone Arkon on the instance."
  default     = "https://github.com/vanhieptech/arkon.git"
}

variable "arkon_repo_branch" {
  type    = string
  default = "main"
}

variable "admin_email" {
  type    = string
  default = "admin@arkon.local"
}

variable "admin_password" {
  type      = string
  sensitive = true
  default   = null
}

variable "secret_key" {
  type      = string
  sensitive = true
  default   = null
}

variable "mcp_token_pepper" {
  type      = string
  sensitive = true
  default   = null
}

variable "postgres_password" {
  type      = string
  sensitive = true
  default   = null
}

variable "redis_password" {
  type      = string
  sensitive = true
  default   = null
}

variable "poc_configure_bedrock" {
  type        = bool
  description = "Set active LLM/embedding to Bedrock on first boot."
  default     = true
}

variable "poc_llm_spec_id" {
  type    = string
  default = "bedrock/claude-3-5-sonnet"
}

variable "poc_embedding_spec_id" {
  type    = string
  default = "bedrock/titan-embed-v2"
}

variable "root_volume_gb" {
  type    = number
  default = 100
}
