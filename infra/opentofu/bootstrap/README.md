# Bootstrap — remote state backend

Run **once** per AWS account before any environment `tofu apply`.

```bash
cd infra/opentofu/bootstrap
tofu init
tofu apply
```

Creates:

- S3 bucket `civilai-tofu-state` (versioned, encrypted)
- DynamoDB table `civilai-tofu-locks` (state locking)

Then configure `environments/uat/backend.tf` (snippet printed by `tofu output backend_config_snippet`)
and run `tofu init -migrate-state` inside the environment directory.
