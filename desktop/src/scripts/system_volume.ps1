param(
  [Parameter(Mandatory = $true)]
  [ValidateSet("get", "set", "up", "down")]
  [string]$Action,
  [double]$Value = 0,
  [double]$Step = 4
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -Language CSharp -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace AelinAudio {
  enum EDataFlow {
    eRender,
    eCapture,
    eAll,
    EDataFlow_enum_count
  }

  enum ERole {
    eConsole,
    eMultimedia,
    eCommunications,
    ERole_enum_count
  }

  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator {
    int NotImpl1();
    int GetDefaultAudioEndpoint(EDataFlow dataFlow, ERole role, out IMMDevice ppDevice);
  }

  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice {
    int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, [MarshalAs(UnmanagedType.IUnknown)] out object ppInterface);
  }

  [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioEndpointVolume {
    int RegisterControlChangeNotify(IntPtr pNotify);
    int UnregisterControlChangeNotify(IntPtr pNotify);
    int GetChannelCount(out uint pnChannelCount);
    int SetMasterVolumeLevel(float fLevelDB, Guid pguidEventContext);
    int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
    int GetMasterVolumeLevel(out float pfLevelDB);
    int GetMasterVolumeLevelScalar(out float pfLevel);
    int SetChannelVolumeLevel(uint nChannel, float fLevelDB, Guid pguidEventContext);
    int SetChannelVolumeLevelScalar(uint nChannel, float fLevel, Guid pguidEventContext);
    int GetChannelVolumeLevel(uint nChannel, out float pfLevelDB);
    int GetChannelVolumeLevelScalar(uint nChannel, out float pfLevel);
    int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid pguidEventContext);
    int GetMute(out bool pbMute);
    int GetVolumeStepInfo(out uint pnStep, out uint pnStepCount);
    int VolumeStepUp(Guid pguidEventContext);
    int VolumeStepDown(Guid pguidEventContext);
    int QueryHardwareSupport(out uint pdwHardwareSupportMask);
    int GetVolumeRange(out float pflVolumeMindB, out float pflVolumeMaxdB, out float pflVolumeIncrementdB);
  }

  [Guid("BCDE0395-E52F-467C-8E3D-C4579291692E"), ComImport]
  class MMDeviceEnumeratorComObject {
  }

  public static class EndpointVolume {
    const int CLSCTX_ALL = 23;

    static IAudioEndpointVolume GetVolumeObject() {
      IMMDeviceEnumerator deviceEnumerator = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());
      IMMDevice speakers;
      Marshal.ThrowExceptionForHR(deviceEnumerator.GetDefaultAudioEndpoint(EDataFlow.eRender, ERole.eMultimedia, out speakers));
      object volumeObj;
      Guid iid = typeof(IAudioEndpointVolume).GUID;
      Marshal.ThrowExceptionForHR(speakers.Activate(ref iid, CLSCTX_ALL, IntPtr.Zero, out volumeObj));
      return (IAudioEndpointVolume)volumeObj;
    }

    public static float GetMasterVolume() {
      float level;
      Marshal.ThrowExceptionForHR(GetVolumeObject().GetMasterVolumeLevelScalar(out level));
      return level;
    }

    public static void SetMasterVolume(float level) {
      if (level < 0f) level = 0f;
      if (level > 1f) level = 1f;
      Marshal.ThrowExceptionForHR(GetVolumeObject().SetMasterVolumeLevelScalar(level, Guid.Empty));
    }
  }
}
"@

function Clamp-Percent([double]$number) {
  if ($number -lt 0) { return 0.0 }
  if ($number -gt 100) { return 100.0 }
  return [double]$number
}

try {
  $current = [double]([AelinAudio.EndpointVolume]::GetMasterVolume() * 100.0)
  $stepValue = [Math]::Abs([double]$Step)
  if ($stepValue -lt 0.5) { $stepValue = 4.0 }

  switch ($Action) {
    "get" {
      # no-op
    }
    "set" {
      $target = Clamp-Percent $Value
      [AelinAudio.EndpointVolume]::SetMasterVolume([single]($target / 100.0))
      $current = [double]([AelinAudio.EndpointVolume]::GetMasterVolume() * 100.0)
    }
    "up" {
      $target = Clamp-Percent ($current + $stepValue)
      [AelinAudio.EndpointVolume]::SetMasterVolume([single]($target / 100.0))
      $current = [double]([AelinAudio.EndpointVolume]::GetMasterVolume() * 100.0)
    }
    "down" {
      $target = Clamp-Percent ($current - $stepValue)
      [AelinAudio.EndpointVolume]::SetMasterVolume([single]($target / 100.0))
      $current = [double]([AelinAudio.EndpointVolume]::GetMasterVolume() * 100.0)
    }
  }

  [pscustomobject]@{
    ok = $true
    reason = ""
    volume = [Math]::Round($current)
  } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{
    ok = $false
    reason = $_.Exception.Message
    volume = $null
  } | ConvertTo-Json -Compress
}

