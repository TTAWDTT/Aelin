param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("play","pause","play_pause","next","previous")]
  [string]$Action
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$managerType = [type]::GetType("Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows, ContentType=WindowsRuntime")
if ($null -eq $managerType) {
  [pscustomobject]@{ ok = $false; reason = "type_not_found" } | ConvertTo-Json -Compress
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
  [pscustomobject]@{ ok = $false; reason = "astask_not_found" } | ConvertTo-Json -Compress
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

$manager = Await-WinRt ($managerType::RequestAsync()) $managerType
$session = $manager.GetCurrentSession()
if ($null -eq $session) {
  [pscustomobject]@{ ok = $false; reason = "no_session" } | ConvertTo-Json -Compress
  exit 0
}

$invokeResult = $false
switch ($Action) {
  "play" { $invokeResult = [bool](Await-WinRt ($session.TryPlayAsync()) ([bool])) }
  "pause" { $invokeResult = [bool](Await-WinRt ($session.TryPauseAsync()) ([bool])) }
  "play_pause" { $invokeResult = [bool](Await-WinRt ($session.TryTogglePlayPauseAsync()) ([bool])) }
  "next" { $invokeResult = [bool](Await-WinRt ($session.TrySkipNextAsync()) ([bool])) }
  "previous" { $invokeResult = [bool](Await-WinRt ($session.TrySkipPreviousAsync()) ([bool])) }
}

[pscustomobject]@{ ok = $invokeResult; reason = "" } | ConvertTo-Json -Compress
