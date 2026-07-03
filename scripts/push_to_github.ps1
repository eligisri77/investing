# Push Trading Pulse to GitHub (private repo recommended).
# Prerequisites: Git + GitHub CLI (gh), logged in: gh auth login
#
# Usage:
#   .\scripts\push_to_github.ps1
#   .\scripts\push_to_github.ps1 -RepoName trading-pulse -Private
#
param(
    [string]$RepoName = "trading-pulse",
    [switch]$Private = $true
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Require-Command($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Error "Missing '$name'. Install Git: https://git-scm.com/download/win and gh: https://cli.github.com/"
    }
}

Require-Command git
Require-Command gh

if (-not (gh auth status 2>$null)) {
    Write-Error "Run 'gh auth login' first."
}

if (-not (Test-Path ".git")) {
    git init
    git branch -M main
}

# Never commit secrets (see .gitignore)
$trackedSecrets = @("instance/.env", "instance/config.json", ".env", "config.json") | Where-Object { git ls-files --error-unmatch $_ 2>$null }
if ($trackedSecrets) {
    Write-Error "Secrets are tracked by git: $($trackedSecrets -join ', '). Run: git rm --cached .env config.json"
}

git add -A
$status = git status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit."
} else {
    git commit -m @"
Initial Trading Pulse snapshot.

Dry-run US stock agent with Telegram, web dashboard, and Windows tray app.
"@
}

$visibility = if ($Private) { "--private" } else { "--public" }
$remote = git remote get-url origin 2>$null
if (-not $remote) {
    gh repo create $RepoName $visibility --source=. --remote=origin --push
    Write-Host "Created and pushed: https://github.com/$(gh api user -q .login)/$RepoName"
} else {
    git push -u origin main
    Write-Host "Pushed to $remote"
}

Write-Host ""
Write-Host "On your other PC:"
Write-Host "  gh repo clone $(gh api user -q .login)/$RepoName"
Write-Host "  copy instance/.env and instance/config.json from this machine (not in git)"
Write-Host "  python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements/requirements.txt"
