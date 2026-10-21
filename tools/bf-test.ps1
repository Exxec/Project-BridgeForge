# BridgeForge offline test helper (2026-09-11).
# Usage (from a PowerShell window):
#   Set-ExecutionPolicy -Scope Process Bypass        # once per window
#   $bf = "C:\Users\exxec\Documents\Project BridgeForge\tools\bf-test.ps1"
#   & $bf help
# Everything writes only into the isolated rig (_rig) or its logs; the real install is only read.

param(
    [Parameter(Position = 0)][string]$Command = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest,
    # ROADMAP 77.21: launch only. Record how the game ended in logs\<TESTID>.exit.json (NATURAL + return code, or KILLED + null).
    [switch]$NaturalExit,
    # ROADMAP-3 79.7: launch through `boot-test` (stop at the main menu) instead of `probe-group live`.
    [switch]$BootOnly,
    [int]$ExitWait = 180
)
$ErrorActionPreference = "Stop"

$Repo = Split-Path $PSScriptRoot -Parent
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
$Rig = Join-Path (Join-Path $Repo "In operation") "_rig"
$Logs = Join-Path $Rig "logs"
$Saves = Join-Path $Rig "saves"
$Core = "C:\Program Files (x86)\Fractal Softworks\Starsector\starsector-core"
$RealMods = "C:\Program Files (x86)\Fractal Softworks\Starsector\mods"
$ProbeId = "bridgeforge_probe"

# Presets: rig mod folder, mods to enable, probe setups, entities to track.
$Presets = @{
    "exigency"     = @{ Folder = "Exigency"; Mods = @("lw_lazylib", "lunalib", "shaderLib", "exigency"); Setups = @("rep:exipirated=FRIENDLY", "credits:500000"); Track = @("exipirated_avesta") }
    "exigency-nex" = @{ Folder = "Exigency"; Mods = @("lw_lazylib", "MagicLib", "lunalib", "shaderLib", "nexerelin", "exigency"); Setups = @("rep:exipirated=FRIENDLY"); Track = @("exipirated_avesta") }
    "yunru-unpack" = @{ Folder = "Yunru-s-Unpack-Blueprints"; Mods = @("lw_lazylib", "lw_console", "unpackblueprints"); Setups = @(); Track = @() }  # Console Commands only to spawn a blueprint package for the test
    "seeker"       = @{ Folder = "SEEKER"; Mods = @("lw_lazylib", "lw_console", "SEEKER"); Setups = @("credits:500000", "ship:ART_dimention_manipulator:1", "spawn-fleet:pirates:120"); Track = @() }
    "seeker-sk13"  = @{ Folder = "SEEKER"; Mods = @("lw_lazylib", "MagicLib", "lunalib", "lw_console", "aitweaks", "SEEKER"); Setups = @("credits:500000", "ship:ART_dimention_manipulator:1", "spawn-fleet:pirates:120"); Track = @() }
    "flux"         = @{ Folder = "Flu-X-0.98a"; Mods = @("lw_lazylib", "MagicLib", "infected"); Setups = @(); Track = @() }
    "arkgneisis"   = @{ Folder = "Legacy-of-Arkgneisis-0.98a"; Mods = @("lw_lazylib", "MagicLib", "lunalib", "shaderLib", "ArkLeg_dev"); Setups = @("credits:500000"); Track = @() }
    "omega"        = @{ Folder = "Omega-Trauma"; Mods = @("lw_lazylib", "MagicLib", "lunalib", "shaderLib", "nexerelin", "Omega_Psychasthenia"); Setups = @(); Track = @() }
    "brokenstar"   = @{ Folder = "Broken-Star"; Mods = @("lw_lazylib", "MagicLib", "broke"); Setups = @(); Track = @() }
    "edmunds"      = @{ Folder = "Edmunds-Church"; Mods = @("lw_lazylib", "a16709513_wkt"); Setups = @(); Track = @() }
    "voidtec"      = @{ Folder = "Void-Tec"; Mods = @("lw_lazylib", "MagicLib", "voidtec"); Setups = @(); Track = @() }
    "flowergod"    = @{ Folder = "FlowerGod"; Mods = @("lw_lazylib", "MagicLib", "lunalib", "shaderLib", "flowergod"); Setups = @(); Track = @() }
}

function Invoke-Bf([string[]]$BfArgs) {
    # Output goes straight to the screen; only the exit code is returned (callers compare it to 0).
    & $Py -m bridgeforge @BfArgs | Out-Host
    return $LASTEXITCODE
}

function Get-NewestSave {
    $save = Get-ChildItem $Saves -Directory | Where-Object { $_.Name -ne "common" -and (Test-Path (Join-Path $_.FullName "campaign.xml")) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $save) { throw "No saves in $Saves yet." }
    return $save
}

function Get-LogPath([string]$TestId) {
    if ($TestId) { return Join-Path $Logs "$TestId.stdout.log" }
    $newest = Get-ChildItem $Logs -Filter "*.stdout.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $newest) { throw "No *.stdout.log in $Logs yet." }
    return $newest.FullName
}

$MainMenuMarker = "Playing music with id [miscallenous_main_menu.ogg]"

function Invoke-Triage([string]$TestId, [string]$Prefix) {
    $log = Get-LogPath $TestId
    $outFile = ($log -replace "\.stdout\.log$", "") + ".triage.txt"
    $extra = @()
    if ($Prefix) { $extra += @("--mod-prefix", $Prefix) }
    $modsDir = Join-Path $Rig "mods"
    $help = & $Py -m bridgeforge log-triage --help 2>&1 | Out-String
    if ($help -match "--mods-dir") { $extra += @("--mods-dir", $modsDir) }   # crash attribution, when available
    & $Py -m bridgeforge log-triage $log @extra | Tee-Object -FilePath $outFile
    Write-Host "Saved: $outFile"
}

function Initialize-WindowTools {
    if ("BfWin2" -as [type]) { return }
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class BfWin2 {
    private delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumProc callback, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int max);
    [DllImport("user32.dll")] private static extern bool EnumChildWindows(IntPtr parent, EnumProc callback, IntPtr lParam);
    // A message box's text sits in child Static controls; Starsector's "Fatal: ..." dialog is one.
    public static string ChildText(long handle) {
        List<string> parts = new List<string>();
        EnumChildWindows(new IntPtr(handle), delegate (IntPtr child, IntPtr lParam) {
            StringBuilder text = new StringBuilder(2048);
            GetWindowText(child, text, 2048);
            string value = text.ToString().Trim();
            if (value.Length > 0 && value != "OK") parts.Add(value);
            return true;
        }, IntPtr.Zero);
        return String.Join(" ", parts.ToArray()).Replace((char)13, (char)32).Replace((char)10, (char)32);
    }
    [StructLayout(LayoutKind.Sequential)] private struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] private struct POINT { public int X, Y; }
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] private static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] private static extern IntPtr ChildWindowFromPointEx(IntPtr parent, POINT pt, uint flags);
    [DllImport("user32.dll")] private static extern bool ScreenToClient(IntPtr hWnd, ref POINT pt);
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] private static extern bool GetCursorPos(out POINT pt);
    [DllImport("user32.dll")] private static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    // Click a point of a window given as fractions of its rectangle (the launcher's Play button sits at 0.50, 0.68 of its
    // 563x352 window, measured from the owner's screenshot 2026-10-11). Posted: window messages to the child under the point,
    // no cursor movement. Physical: move the real cursor, click, put it back; only as a fallback, it needs the window on top.
    public static string ClickWindow(long handle, double fx, double fy, bool physical) {
        IntPtr hWnd = new IntPtr(handle);
        RECT r;
        if (!GetWindowRect(hWnd, out r)) return "no window rectangle";
        int sx = r.Left + (int)((r.Right - r.Left) * fx);
        int sy = r.Top + (int)((r.Bottom - r.Top) * fy);
        if (!physical) {
            POINT p; p.X = sx; p.Y = sy;
            ScreenToClient(hWnd, ref p);
            IntPtr child = ChildWindowFromPointEx(hWnd, p, 0);
            IntPtr target = (child == IntPtr.Zero) ? hWnd : child;
            POINT q; q.X = sx; q.Y = sy;
            ScreenToClient(target, ref q);
            IntPtr lp = new IntPtr((q.Y << 16) | (q.X & 0xFFFF));
            PostMessage(target, 0x0200, IntPtr.Zero, lp);           // WM_MOUSEMOVE
            PostMessage(target, 0x0201, new IntPtr(1), lp);         // WM_LBUTTONDOWN
            PostMessage(target, 0x0202, IntPtr.Zero, lp);           // WM_LBUTTONUP
            return "posted click to " + target.ToInt64() + " at " + sx + "," + sy;
        }
        POINT old; GetCursorPos(out old);
        SetForegroundWindow(hWnd);
        System.Threading.Thread.Sleep(300);
        SetCursorPos(sx, sy);
        System.Threading.Thread.Sleep(150);
        mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero);                 // left down
        mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero);                 // left up
        System.Threading.Thread.Sleep(150);
        SetCursorPos(old.X, old.Y);
        return "physical click at " + sx + "," + sy;
    }
    public static List<string> VisibleWindows(uint pid) {
        List<string> found = new List<string>();
        EnumWindows(delegate (IntPtr hWnd, IntPtr lParam) {
            uint owner;
            GetWindowThreadProcessId(hWnd, out owner);
            if (owner == pid && IsWindowVisible(hWnd)) {
                StringBuilder title = new StringBuilder(512);
                GetWindowText(hWnd, title, 512);
                found.Add(hWnd.ToInt64().ToString() + "|" + title.ToString());
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }
}
"@
}

function Save-Screenshot([string]$Path) {
    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bitmap.Size)
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $graphics.Dispose(); $bitmap.Dispose()
    }
}

function Get-RigJava {
    $rigFull = (Resolve-Path $Rig).Path
    Get-Process -Name java, javaw -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($rigFull, [System.StringComparison]::OrdinalIgnoreCase) }
}

function Resolve-Preset([string]$Name) {
    if (-not $Name) { throw "Give a preset: $(($Presets.Keys | Sort-Object) -join ', ')" }
    if ($Presets.ContainsKey($Name)) { return $Presets[$Name] }
    if (Test-Path (Join-Path $Rig "mods\$Name")) { return @{ Folder = $Name; Mods = @(); Setups = @(); Track = @() } }
    throw "Unknown preset or rig mod folder '$Name'. Presets: $(($Presets.Keys | Sort-Object) -join ', ')"
}

switch ($Command) {
    "doctor" {
        # Pre-flight: rig isolated, no game running, probe installed and current, enabled mods resolve,
        # rig copies match working copies, real-install saves untouched. First run: add -Baseline to record the saves listing.
        $bfArgs = @("rig-doctor", $Rig, "--real-install", (Split-Path $Core -Parent))
        if ($Rest -contains "-Baseline") { $bfArgs += "--write-saves-baseline" }
        Invoke-Bf $bfArgs | Out-Null
    }
    "compat" {
        # One-time: copy the standard compat set (libs + AI Tweaks, Nexerelin, SWP, IndEvo, Unknown Skies, Tahlan) into the rig.
        Invoke-Bf @("compat-set", "install", "standard", "--runtime", $Rig, "--source-mods", $RealMods) | Out-Null
    }
    "probe" {
        # Install the probe, write its config (hulls, tracked entities, setups) and set enabled_mods.json.
        $p = Resolve-Preset $Rest[0]
        $modDir = Join-Path $Rig "mods\$($p.Folder)"
        $bfArgs = @("probe-config", $modDir, "--runtime", $Rig, "--install")
        if ($Rest.Count -gt 1) {
            # Optional setup profile (bundled name or .txt path); it replaces the preset's setups in game.
            $bfArgs += @("--profile", $Rest[1])
        } else {
            foreach ($s in $p.Setups) { $bfArgs += @("--setup", $s) }
        }
        foreach ($t in $p.Track) { $bfArgs += @("--track", $t) }
        if ((Invoke-Bf $bfArgs) -ne 0) { throw "probe-config failed." }
        if ($p.Mods.Count -gt 0) {
            $enabledPath = Join-Path $Rig "mods\enabled_mods.json"
            $backup = "$enabledPath.pre-bftest.bak"
            if (-not (Test-Path $backup)) { Copy-Item $enabledPath $backup }
            $json = '{"enabledMods": [' + ((@($p.Mods) + $ProbeId | ForEach-Object { '"' + $_ + '"' }) -join ", ") + ']}'
            [System.IO.File]::WriteAllText($enabledPath, $json)
            Write-Host "enabled_mods.json -> $json"
        } else {
            Write-Host "No preset mod list: tick the mod, its dependencies and '$ProbeId' in the launcher yourself."
        }
    }
    "launch" {
        # ROADMAP-3 79.7: one launcher path. The game is started, clicked into, watched (launch watchdog LAUNCH_NO_PROCESS), exit-observed
        # and stopped by bridgeforge/launch.py, through `probe-group live` (default) or `boot-test` (-BootOnly); this only runs the
        # pre-flight, passes the parameters on and triages the log. Log: logs\<TESTID>.stdout.log.
        $id = $Rest[0]
        if (-not $id) { throw "Give a test id, e.g. PRB-1" }
        $bat = "run-java25.bat"
        $out = Join-Path $Logs "$id.stdout.log"
        if (Get-RigJava) { throw "A rig game is already running; close it first." }
        # ROADMAP 36.2: pre-flight before every launch (isolation, core integrity against the recorded RC8 baseline,
        # probe, enabled mods, drift). A FAIL stops the run; there is no override: fix the rig, then launch.
        $doctor = Invoke-Bf @("rig-doctor", $Rig, "--real-install", (Split-Path $Core -Parent))
        if ($doctor -ne 0) { throw "rig-doctor failed (see above); launch refused." }
        $started = Get-Date
        Write-Host "Launching; log -> $out."
        if ($BootOnly) {
            $enabled = @((Get-Content (Join-Path $Rig "mods\enabled_mods.json") -Raw | ConvertFrom-Json).enabledMods)
            $bfArgs = @("boot-test", $Rig, "--mods") + $enabled + @("--keep-mods", "--log-name", $id)
            if ($NaturalExit) { $bfArgs += "--natural-exit" }
        } else {
            $bfArgs = @("probe-group", "live", $id, "--rig", $Rig, "--bat", $bat, "--exit-wait", "$ExitWait")
            if ($NaturalExit) { $bfArgs += "--natural-exit" }
        }
        $code = Invoke-Bf $bfArgs
        if ($code -ne 0) { Write-Host "The launch command exited with code $code (see above)." }
        # ROADMAP 36.4: a JVM crash writes hs_err_pid<PID>.log to the game's working directory, not our log. Copy any
        # written during this launch beside the log as hs_err_pid<PID>.<TESTID>.log, which log-triage reads.
        foreach ($dir in @($Rig, $Core)) {
            Get-ChildItem -Path $dir -Filter "hs_err_pid*.log" -File -ErrorAction SilentlyContinue |
                Where-Object { $_.LastWriteTime -ge $started } |
                ForEach-Object {
                    $copy = Join-Path $Logs ($_.BaseName + ".$id.log")
                    Copy-Item -Path $_.FullName -Destination $copy -Force
                    Write-Host "JVM crash log: $($_.Name) -> $copy"
                }
        }
        Write-Host "Game closed. Triage:"
        Invoke-Triage $id ""
    }
    "triage" {
        # Sort a log into FATAL / MOD-ERROR / noise, plus probe results; saved as logs\<name>.triage.txt.
        $prefix = ""
        if ($Rest.Count -gt 1) { $prefix = $Rest[1] }
        Invoke-Triage $Rest[0] $prefix
    }
    "scenario" {
        # Check a scenario's expected results against a log (and the newest save): avesta-near, betelgeuse-damaged, nex-corvus-day1.
        $name = $Rest[0]
        $log = Get-LogPath $(if ($Rest.Count -gt 1) { $Rest[1] } else { "" })
        $save = Get-NewestSave
        $outFile = Join-Path $Logs ("scenario-$name-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".txt")
        & $Py -m bridgeforge scenario check $name $log --save $save.FullName | Tee-Object -FilePath $outFile
        Write-Host "Saved: $outFile"
    }
    "savecheck" {
        # Read-only checks on the newest rig save for a preset's mod: loads? data ids? duplicate scripts? which build?
        $p = Resolve-Preset $Rest[0]
        $modDir = Join-Path $Rig "mods\$($p.Folder)"
        $save = Get-NewestSave
        $outFile = Join-Path $Logs ("savecheck-$($p.Folder)-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".txt")
        & {
            "Save: $($save.Name)  Mod: $($p.Folder)"
            "--- save-compat (classes)";       & $Py -m bridgeforge save-compat $save.FullName $modDir --vanilla-core $Core
            "--- save-content (data ids)";     & $Py -m bridgeforge save-content $save.FullName $modDir --vanilla-core $Core
            "--- save-scripts (duplicates)";   & $Py -m bridgeforge save-scripts $save.FullName $modDir --vanilla-core $Core
            "--- save-provenance (build)";     & $Py -m bridgeforge save-provenance $save.FullName --mod-dir $modDir
            $bak = Join-Path $save.FullName "campaign.xml.bak"
            if (Test-Path $bak) { "--- save-diff vs previous save (tracked counts)"; & $Py -m bridgeforge save-diff (Join-Path $save.FullName "campaign.xml") $bak --mod-dir $modDir }
        } 2>&1 | Tee-Object -FilePath $outFile
        Write-Host "Saved: $outFile"
    }
    "snap" {
        # Keep the newest save as a reusable starting point: & $bf snap exigency-day3
        $tag = $Rest[0]
        if (-not $tag) { throw "Give a tag, e.g. exigency-day3" }
        $save = Get-NewestSave
        Invoke-Bf @("save-snapshot", "tag", $Rig, $save.Name, $tag) | Out-Null
    }
    "restore" {
        $tag = $Rest[0]
        if (-not $tag) { throw "Give a snapshot tag (see: & `$bf snaps)" }
        Invoke-Bf @("save-snapshot", "restore", $Rig, $tag, "--as-name", "restored_$tag") | Out-Null
    }
    "snaps" { Invoke-Bf @("save-snapshot", "list", $Rig) | Out-Null }
    "selftest" {
        # Compiles the window watcher and lists this PowerShell's own windows; launches nothing, saves no screenshot.
        Initialize-WindowTools
        $mine = [BfWin2]::VisibleWindows([uint32]$PID)
        Write-Host "Window watcher OK ($($mine.Count) visible window(s) for this process). Rig java running: $([bool](Get-RigJava))"
    }
    "report" {
        # Bundle today's triage / savecheck / scenario outputs into one file to send back.
        $today = (Get-Date).Date
        $files = Get-ChildItem $Logs -File | Where-Object { $_.LastWriteTime -ge $today -and ($_.Name -like "*.triage.txt" -or $_.Name -like "savecheck-*.txt" -or $_.Name -like "scenario-*.txt") } | Sort-Object LastWriteTime
        $reportPath = Join-Path $Logs ("REPORT-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".txt")
        $parts = foreach ($f in $files) { "===== $($f.Name) ====="; Get-Content $f.FullName; "" }
        [System.IO.File]::WriteAllLines($reportPath, [string[]]$parts)
        Write-Host "Report: $reportPath ($($files.Count) files). Send it back with any Fatal-dialog screenshots."
    }
    default {
        Write-Host @"
BridgeForge offline test helper. Commands:
  doctor [-Baseline]          pre-flight checks (first time: -Baseline records your real saves listing)
  compat                     one-time: install the standard compat set into the rig
  probe <preset|folder> [profile]  install the probe, write its config + setups, set enabled mods
                              profile: exigency-rep | seeker-betelgeuse | flux-basic | path\to\my.txt
                              presets: $(($Presets.Keys | Sort-Object) -join ', ')
  launch <TESTID> [-NaturalExit] [-ExitWait 180] [-BootOnly]
                              start the rig, log to logs\<TESTID>.stdout.log (returns when the game closes).
                              -NaturalExit records the observed exit in logs\<TESTID>.exit.json (NATURAL+code or KILLED+null).
  triage [TESTID] [prefix]    log-triage the log (default: newest) -> logs\<TESTID>.triage.txt
  scenario <name> [TESTID]    scenario check: avesta-near | betelgeuse-damaged | nex-corvus-day1
  savecheck <preset|folder>   read-only checks on the newest save -> logs\savecheck-*.txt
  snap <tag> / snaps / restore <tag>   keep, list, restore save snapshots (rig only)
  report                      bundle today's outputs into logs\REPORT-*.txt to send back
"@
    }
}

