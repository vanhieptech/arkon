output "instance_id" {
  value = aws_instance.arkon.id
}

output "public_ip" {
  value = aws_eip.arkon[0].public_ip
}

output "s3_bucket" {
  value = aws_s3_bucket.arkon.bucket
}

output "ui_url" {
  value = "http://${aws_eip.arkon[0].public_ip}:3119"
}

output "api_url" {
  value = "http://${aws_eip.arkon[0].public_ip}:5055"
}

output "ssh_command" {
  value = "ssh -i <your-key.pem> ubuntu@${aws_eip.arkon[0].public_ip}"
}

output "admin_email" {
  value = var.admin_email
}

output "admin_password" {
  value     = local.admin_password
  sensitive = true
}

output "bootstrap_log" {
  value = "ssh ubuntu@${aws_eip.arkon[0].public_ip} 'sudo tail -f /var/log/arkon-bootstrap.log'"
}
