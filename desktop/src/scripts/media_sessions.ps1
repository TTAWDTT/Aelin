param(
  [string]$Preferred = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$managerType = [type]::GetType("Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows, ContentType=WindowsRuntime")
$propsType = [type]::GetType("Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows, ContentType=WindowsRuntime")
$streamType = [type]::GetType("Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows, ContentType=WindowsRuntime")

if ($null -eq $managerType -or $null -eq $propsType) {
  [pscustomobject]@{ ok = $false; reason = "type_not_found"; sessions = @() } | ConvertTo-Json -Compress -Depth 7
  exit 0
}

$asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() |
  Where-Object {
    $_.Name -eq "AsTask" -and
    $_.IsGenericMethod -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -like "IAsyncOperation*"
  } |
  Select-Object -First 1

if ($null -eq $asTaskMethod) {
  [pscustomobject]@{ ok = $false; reason = "astask_not_found"; sessions = @() } | ConvertTo-Json -Compress -Depth 7
  exit 0
}

function Await-WinRt {
  param(
    [Parameter(Mandatory = $true)] $Operation,
    [Parameter(Mandatory = $true)] [Type]$ResultType
  )
  $generic = $asTaskMethod.MakeGenericMethod($ResultType)
  $task = $generic.Invoke($null, @($Operation))
  $task.Wait(-1) | Out-Null
  return $task.Result
}

function Read-ThumbnailData {
  param($ThumbnailRef)
  if ($null -eq $ThumbnailRef -or $null -eq $streamType) {
    return [pscustomobject]@{
      base64 = ""
      mime = ""
    }
  }
  try {
    $stream = Await-WinRt ($ThumbnailRef.OpenReadAsync()) $streamType
    if ($null -eq $stream) {
      return [pscustomobject]@{ base64 = ""; mime = "" }
    }
    $mime = ""
    try {
      $mime = [string]$stream.ContentType
    }
    catch {
      $mime = ""
    }
    $netStream = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
    if ($null -eq $netStream) {
      return [pscustomobject]@{ base64 = ""; mime = "" }
    }
    $memory = New-Object System.IO.MemoryStream
    $netStream.CopyTo($memory)
    $bytes = $memory.ToArray()
    if ($null -eq $bytes -or $bytes.Length -le 0 -or $bytes.Length -gt 838860) {
      return [pscustomobject]@{ base64 = ""; mime = "" }
    }
    return [pscustomobject]@{
      base64 = [System.Convert]::ToBase64String($bytes)
      mime = $mime
    }
  }
  catch {
    return [pscustomobject]@{
      base64 = ""
      mime = ""
    }
  }
}

$preferredTokens = @()
if (-not [string]::IsNullOrWhiteSpace($Preferred)) {
  $preferredTokens = $Preferred.Split(",") |
    ForEach-Object { $_.Trim().ToLower() } |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
}

$manager = Await-WinRt ($managerType::RequestAsync()) $managerType
$sessions = $manager.GetSessions()

if ($null -eq $sessions -or $sessions.Count -eq 0) {
  [pscustomobject]@{ ok = $false; reason = "no_session"; sessions = @() } | ConvertTo-Json -Compress -Depth 7
  exit 0
}

$result = @()
foreach ($session in $sessions) {
  try {
    $props = Await-WinRt ($session.TryGetMediaPropertiesAsync()) $propsType
    $playback = $session.GetPlaybackInfo()
    $controls = $playback.Controls
    $status = [string]$playback.PlaybackStatus
    $app = [string]$session.SourceAppUserModelId
    $appLower = $app.ToLower()
    $isPreferred = $false
    if ($preferredTokens.Count -gt 0) {
      foreach ($token in $preferredTokens) {
        if ($appLower.Contains($token)) {
          $isPreferred = $true
          break
        }
      }
    }

    $cover = Read-ThumbnailData $props.Thumbnail

    $result += [pscustomobject]@{
      title = [string]$props.Title
      artist = [string]$props.Artist
      album = [string]$props.AlbumTitle
      status = $status
      app = $app
      canPlay = [bool]$controls.IsPlayEnabled
      canPause = [bool]$controls.IsPauseEnabled
      canNext = [bool]$controls.IsNextEnabled
      canPrev = [bool]$controls.IsPreviousEnabled
      isPreferred = $isPreferred
      coverBase64 = [string]$cover.base64
      coverMime = [string]$cover.mime
    }
  }
  catch {
    continue
  }
}

[pscustomobject]@{
  ok = $true
  reason = ""
  sessions = $result
} | ConvertTo-Json -Compress -Depth 7
