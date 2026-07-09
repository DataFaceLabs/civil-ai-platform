output "data_api_public_ip" {
  value = module.data_api_ec2.public_ip
}

output "data_api_base_url" {
  value = module.data_api_ec2.data_api_base_url_http
}

output "platform_api_endpoint" {
  value = var.create_platform_http_api ? module.api_gateway[0].api_endpoint : null
}

output "cognito_user_pool_id" {
  value = var.create_platform_persistence ? module.cognito[0].user_pool_id : null
}

output "cognito_client_id" {
  value = var.create_platform_persistence ? module.cognito[0].app_client_id : null
}

output "cognito_hosted_ui" {
  value = var.create_platform_persistence ? module.cognito[0].hosted_ui_base_url : null
}

output "dynamodb_table" {
  value = var.create_platform_persistence ? module.dynamodb[0].table_name : null
}

output "data_service_key" {
  value     = module.secrets.data_service_key
  sensitive = true
}

output "amplify_branch_url" {
  value = var.create_amplify_app ? module.amplify[0].branch_url : null
}

output "local_platform_env" {
  value = <<-EOT
    CIVILAI_DATA_API_BASE=${module.data_api_ec2.data_api_base_url_http}
    CIVILAI_DATA_SERVICE_KEY=<run: tofu output -raw data_service_key>
  EOT
}
