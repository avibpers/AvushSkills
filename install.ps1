<#
  Installs, updates or removes Avush skills on Windows.

  One line (install everything for the tools found on this PC):
    irm https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.ps1 | iex

  With options (save the script first, or run it from a clone):
    .\install.ps1 -Skills meeting-sum -Targets claude,grok
    .\install.ps1 -Update          # same skills, same places, newest version
    .\install.ps1 -Uninstall       # removes what this script installed
    .\install.ps1 -List            # shows the skills in the repo and what is installed

  Targets: claude (~\.claude\skills), cursor (~\.cursor\skills), grok (~\.grok\skills),
  agents (~\.agents\skills, read by Codex, Grok Build and Cursor).
  Your own files (for example ~\.claude\meeting-templates) are never touched.
#>
param(
  [string[]]$Skills,
  [string[]]$Targets,
  [switch]$Update,
  [switch]$Uninstall,
  [switch]$List,
  [string]$Branch = 'main'
)

$ErrorActionPreference = 'Stop'
# "irm ... | iex" runs the script without parameter defaults.
if (-not $Branch) { $Branch = 'main' }
$Repo = 'avibpers/AvushSkills'
# AVUSH_SKILLS_HOME points the script at another home folder (for testing).
$Home_ = if ($env:AVUSH_SKILLS_HOME) { $env:AVUSH_SKILLS_HOME } else { [Environment]::GetFolderPath('UserProfile') }
$StateDir = Join-Path $Home_ '.avush-skills'
$StateFile = Join-Path $StateDir 'installed.json'
$Dirs = @{
  claude = Join-Path $Home_ '.claude\skills'
  cursor = Join-Path $Home_ '.cursor\skills'
  grok   = Join-Path $Home_ '.grok\skills'
  agents = Join-Path $Home_ '.agents\skills'
}

# Accept "a,b" as well as a, b.
function Split-List($items) { if ($items) { $items | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ } } }
$Skills = @(Split-List $Skills)
$Targets = @(Split-List $Targets)

function Read-State {
  if (Test-Path $StateFile) { return Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json }
  return $null
}

function Write-State($skills, $targets, $commit) {
  New-Item -ItemType Directory -Force $StateDir | Out-Null
  [pscustomobject]@{ repo = $Repo; branch = $Branch; skills = @($skills); targets = @($targets); commit = $commit; updated = (Get-Date).ToString('s') } |
    ConvertTo-Json | Out-File $StateFile -Encoding utf8
}

# The tools found on this PC. Cursor also reads ~\.claude\skills, so it is only
# a default target when Claude Code isn't installed (no duplicate skills).
function Find-Targets {
  $found = @()
  if (Test-Path (Join-Path $Home_ '.claude')) { $found += 'claude' }
  if ((Test-Path (Join-Path $Home_ '.cursor')) -and -not ($found -contains 'claude')) { $found += 'cursor' }
  if (Test-Path (Join-Path $Home_ '.grok')) { $found += 'grok' }
  if ($found.Count -eq 0) { $found = @('claude') }
  return $found
}

# The repo's files: this folder when run from a clone, else a fresh download.
function Get-Source {
  if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'skills')) -and -not $Update) {
    $commit = ''
    try { $commit = (git -C $PSScriptRoot rev-parse --short HEAD) 2>$null } catch {}
    return @{ path = $PSScriptRoot; commit = $commit }
  }
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ('avush-skills-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Force $tmp | Out-Null
  $zip = Join-Path $tmp 'repo.zip'
  Write-Host "Downloading $Repo ($Branch)..."
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip -UseBasicParsing
  Expand-Archive $zip -DestinationPath $tmp -Force
  $root = Get-ChildItem $tmp -Directory | Select-Object -First 1
  $commit = ''
  try { $commit = (Invoke-RestMethod "https://api.github.com/repos/$Repo/commits/$Branch" -UseBasicParsing).sha.Substring(0, 7) } catch {}
  return @{ path = $root.FullName; commit = $commit; temp = $tmp }
}

$state = Read-State

if ($List) {
  $src = Get-Source
  Write-Host 'Skills in the repo:'
  Get-ChildItem (Join-Path $src.path 'skills') -Directory | ForEach-Object { Write-Host "  $($_.Name)" }
  if ($state) { Write-Host "Installed: $($state.skills -join ', ') -> $($state.targets -join ', ') (commit $($state.commit), $($state.updated))" }
  else { Write-Host 'Nothing installed by this script yet.' }
  if ($src.temp) { Remove-Item $src.temp -Recurse -Force }
  return
}

if ($Uninstall) {
  if (-not $Skills.Count -and $state) { $Skills = @($state.skills) }
  if (-not $Targets.Count) { $Targets = if ($state) { @($state.targets) } else { @('claude', 'cursor', 'grok', 'agents') } }
  foreach ($t in $Targets) {
    foreach ($s in $Skills) {
      $dest = Join-Path $Dirs[$t] $s
      if (Test-Path $dest) { Remove-Item $dest -Recurse -Force; Write-Host "Removed $s from $t ($dest)" }
    }
  }
  if (Test-Path $StateFile) { Remove-Item $StateFile -Force }
  Write-Host 'Done. Your own templates and files were kept.'
  return
}

# Install or update.
if ($Update -and $state) {
  if (-not $Skills.Count) { $Skills = @($state.skills) }
  if (-not $Targets.Count) { $Targets = @($state.targets) }
}
if (-not $Targets.Count) { $Targets = Find-Targets }
foreach ($t in $Targets) { if (-not $Dirs.ContainsKey($t)) { throw "Unknown target '$t'. Use: $($Dirs.Keys -join ', ')" } }

$src = Get-Source
$available = Get-ChildItem (Join-Path $src.path 'skills') -Directory | ForEach-Object { $_.Name }
if (-not $Skills.Count) { $Skills = @($available) }
foreach ($s in $Skills) { if ($available -notcontains $s) { throw "No skill '$s'. Available: $($available -join ', ')" } }

foreach ($t in $Targets) {
  New-Item -ItemType Directory -Force $Dirs[$t] | Out-Null
  foreach ($s in $Skills) {
    $dest = Join-Path $Dirs[$t] $s
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
    Copy-Item (Join-Path $src.path "skills\$s") $dest -Recurse
    Get-ChildItem $dest -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
    Write-Host "Installed $s for $t -> $dest"
  }
}
# Remember everything installed so far, so -Update and -Uninstall cover all of it.
$allSkills = @($Skills); $allTargets = @($Targets)
if ($state) {
  $allSkills = @(@($state.skills) + $Skills | Select-Object -Unique)
  $allTargets = @(@($state.targets) + $Targets | Select-Object -Unique)
}
Write-State $allSkills $allTargets $src.commit
if ($src.temp) { Remove-Item $src.temp -Recurse -Force }
Write-Host ''
Write-Host "Done ($($src.commit)). Restart the app or start a new chat to load the skills."
Write-Host 'Update later with:  irm https://raw.githubusercontent.com/avibpers/AvushSkills/main/install.ps1 -OutFile install.ps1; .\install.ps1 -Update'
