# Temporary GitHub KPI persistence

The bot can temporarily persist `kpi_data.json` and `uploaded_data/latest_kpi.xlsx` in the configured GitHub repository and restore them before Telegram polling starts.

Configure these Render environment variables:

```text
GITHUB_SYNC_ENABLED=true
GITHUB_SYNC_REPO=rusya-malina/-
GITHUB_SYNC_BRANCH=main
GITHUB_SYNC_TOKEN=<fine-grained token stored only in Render Environment Variables>
```

The token needs repository **Contents: Read and write** permission for the configured repository. It is never written to the repository or logged by the bot.

After the first successful KPI Excel upload, the bot updates both files through the GitHub Contents API. On the next process start, it restores the two files from GitHub before polling begins. The `/healthz` server starts before the restore so Render can continue to probe the service during the network operation.

This is a temporary workaround because the current repository is public. KPI names and metrics committed to a public repository may be readable by third parties. Migrate to private object storage or a database when available, then remove the GitHub token and disable this bridge.
