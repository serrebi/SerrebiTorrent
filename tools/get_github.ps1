$ErrorActionPreference = "Stop"

$url = git remote get-url origin 2>$null
if ($url -match "github.com[:/](.+?)/(.+?)(\.git)?$") {
    Write-Output ("GITHUB_OWNER={0}" -f $matches[1])
    Write-Output ("GITHUB_REPO={0}" -f $matches[2])
}
