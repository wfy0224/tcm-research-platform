# Safe native storage probe; does not start the known-failing Python runtime.
# Uses a unique disposable target and never reads or overwrites provider keys.
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

public static class TcmCredentialAcceptanceProbe {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct Credential {
        public uint Flags, Type;
        public string TargetName, Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public uint CredentialBlobSize;
        public IntPtr CredentialBlob;
        public uint Persist, AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias, UserName;
    }
    [DllImport("advapi32.dll", EntryPoint="CredReadW", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern bool Read(string target, uint type, uint flags, out IntPtr pointer);
    [DllImport("advapi32.dll", EntryPoint="CredWriteW", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern bool Write(ref Credential credential, uint flags);
    [DllImport("advapi32.dll", EntryPoint="CredDeleteW", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern bool Delete(string target, uint type, uint flags);
    [DllImport("advapi32.dll")] private static extern void CredFree(IntPtr pointer);

    public static bool Run() {
        string target = "tcm-research-platform:acceptance-probe-" + Guid.NewGuid().ToString("N");
        string value = "一次性工程验证-" + Guid.NewGuid().ToString("N");
        IntPtr read;
        if (Read(target, 1, 0, out read)) { CredFree(read); throw new Exception("Probe target exists"); }
        if (Marshal.GetLastWin32Error() != 1168) throw new Win32Exception(Marshal.GetLastWin32Error());
        byte[] bytes = Encoding.Unicode.GetBytes(value);
        IntPtr blob = Marshal.AllocHGlobal(bytes.Length);
        bool written = false;
        try {
            Marshal.Copy(bytes, 0, blob, bytes.Length);
            Credential credential = new Credential { Type=1, TargetName=target,
                CredentialBlobSize=(uint)bytes.Length, CredentialBlob=blob, Persist=2,
                UserName="tcm-research-platform-acceptance" };
            if (!Write(ref credential, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
            written = true;
            if (!Read(target, 1, 0, out read)) throw new Win32Exception(Marshal.GetLastWin32Error());
            try {
                Credential stored = Marshal.PtrToStructure<Credential>(read);
                byte[] restored = new byte[stored.CredentialBlobSize];
                Marshal.Copy(stored.CredentialBlob, restored, 0, restored.Length);
                if (Encoding.Unicode.GetString(restored) != value || stored.Type != 1 || stored.Persist != 2)
                    throw new Exception("Credential round-trip differs");
                Array.Clear(restored, 0, restored.Length);
            } finally { CredFree(read); }
        } finally {
            if (written && !Delete(target, 1, 0)) throw new Win32Exception(Marshal.GetLastWin32Error());
            Marshal.FreeHGlobal(blob);
            Array.Clear(bytes, 0, bytes.Length);
        }
        if (Read(target, 1, 0, out read)) { CredFree(read); throw new Exception("Probe cleanup failed"); }
        if (Marshal.GetLastWin32Error() != 1168) throw new Win32Exception(Marshal.GetLastWin32Error());
        return true;
    }
}
'@
$taskNativePassed = [TcmCredentialAcceptanceProbe]::Run()
[pscustomobject]@{
    passed = $taskNativePassed
    native_api = 'CredReadW/CredWriteW/CredDeleteW/CredFree'
    unicode_roundtrip = $true
    generic_type = 1
    persistence = 2
    temporary_target_deleted = $true
    existing_provider_credentials_touched = $false
    python_adapter_executed = $false
} | ConvertTo-Json
