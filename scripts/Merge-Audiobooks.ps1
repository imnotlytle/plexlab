<#
Merge multi-file audiobooks into a single chaptered .m4b.

Runs on the PC (Ryzen 7800X3D) against the NAS over SMB — the NAS's N100 is far too slow
to transcode 121 books.

SAFETY MODEL:
  - Originals are NEVER deleted or modified. Output goes to a separate -OutRoot.
  - Every output is duration-verified against the sum of its sources before being kept.
  - A failed/short conversion is deleted and the book is reported, not silently skipped.

Ordering matches Audiobookshelf: sort by embedded TRACK tag when all files have one,
otherwise natural filename order (so "pt2" sorts before "pt10").

Chapters: one chapter per source file, named from its title tag, else its filename.

AAC sources (.m4b/.m4a) are stream-copied (lossless, seconds per book).
MP3 sources are transcoded to AAC at a bitrate matched to the source.
#>
[CmdletBinding()]
param(
    [string]$SrcRoot = "\\192.168.68.56\Media\Audio\Regular",
    [string]$OutRoot = "\\192.168.68.56\Media\Audio\merged",
    [ValidateSet("aac", "mp3", "all")][string]$Only = "aac",  # which source type to process
    [int]$Limit = 0,                                           # 0 = no limit
    [string]$Match = "",                                       # only books whose path matches
    [switch]$WhatIfOnly                                        # list what would be done
)

$ErrorActionPreference = "Stop"
$ff = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffmpeg.exe"
$fp = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ffprobe.exe"
if (-not (Test-Path $ff)) { $ff = "ffmpeg" ; $fp = "ffprobe" }

function Get-NaturalKey([string]$s) {
    # pad digit runs so pt2 < pt10
    [regex]::Replace($s.ToLower(), '\d+', { $args[0].Value.PadLeft(10, '0') })
}

function Get-AudioInfo([string]$path) {
    $json = & $fp -v quiet -print_format json -show_entries `
        "format=duration:format_tags=track,title:stream=codec_name,bit_rate" -select_streams a:0 -- "$path" 2>$null
    if (-not $json) { return $null }
    try { $d = $json | ConvertFrom-Json } catch { return $null }
    $trk = $null
    if ($d.format.tags) {
        $raw = $d.format.tags.track
        if ($raw -and ($raw -match '^\s*(\d+)')) { $trk = [int]$Matches[1] }
    }
    [pscustomobject]@{
        Path     = $path
        Duration = [double]$d.format.duration
        Track    = $trk
        Title    = if ($d.format.tags) { $d.format.tags.title } else { $null }
        Codec    = $d.streams[0].codec_name
        BitRate  = if ($d.streams[0].bit_rate) { [int]$d.streams[0].bit_rate } else { 0 }
    }
}

# ---- discover books (Author/Title folders with >1 audio file, recursive) ----
$books = @()
foreach ($author in Get-ChildItem -LiteralPath $SrcRoot -Directory) {
    foreach ($title in Get-ChildItem -LiteralPath $author.FullName -Directory) {
        $files = Get-ChildItem -LiteralPath $title.FullName -Recurse -File |
                 Where-Object { $_.Extension -match '^\.(mp3|m4b|m4a)$' }
        if ($files.Count -le 1) { continue }
        $exts = $files | ForEach-Object { $_.Extension.ToLower() } | Sort-Object -Unique
        $kind = if ($exts -contains '.mp3' -and $exts.Count -gt 1) { 'mixed' }
                elseif ($exts -contains '.mp3') { 'mp3' } else { 'aac' }
        $books += [pscustomobject]@{
            Rel = "$($author.Name)\$($title.Name)"; Dir = $title.FullName
            Files = $files; Kind = $kind
        }
    }
}

if ($Match) { $books = $books | Where-Object { $_.Rel -like "*$Match*" } }
if ($Only -ne 'all') { $books = $books | Where-Object { $_.Kind -eq $Only } }
$books = $books | Sort-Object Rel
if ($Limit -gt 0) { $books = $books | Select-Object -First $Limit }

Write-Output "Books to process: $($books.Count)  (Only=$Only)"
if ($WhatIfOnly) {
    $books | ForEach-Object { "  [{0,-5}] {1,4} files  {2}" -f $_.Kind, $_.Files.Count, $_.Rel }
    return
}

$okCount = 0; $failed = @()
foreach ($b in $books) {
    $outDir  = Join-Path $OutRoot $b.Rel
    $outFile = Join-Path $outDir ((Split-Path $b.Rel -Leaf) + ".m4b")
    if (Test-Path -LiteralPath $outFile) { Write-Output "SKIP (exists) $($b.Rel)"; continue }

    Write-Output ""
    Write-Output "=== $($b.Rel)  [$($b.Kind), $($b.Files.Count) files] ==="

    # probe all sources
    $infos = @()
    foreach ($f in $b.Files) { $i = Get-AudioInfo $f.FullName; if ($i) { $infos += $i } }
    if ($infos.Count -lt 2) { $failed += "$($b.Rel) :: probe failed"; continue }

    # order: track tags if complete & unique, else natural filename
    $tracks = $infos | Where-Object { $_.Track -ne $null }
    $useTags = ($tracks.Count -eq $infos.Count) -and
               (($infos.Track | Sort-Object -Unique).Count -eq $infos.Count)
    $ordered = if ($useTags) { $infos | Sort-Object Track }
               else { $infos | Sort-Object { Get-NaturalKey (Split-Path $_.Path -Leaf) } }
    Write-Output ("  order by: " + $(if ($useTags) { "track tags" } else { "filename (natural)" }))

    $srcTotal = ($ordered | Measure-Object Duration -Sum).Sum

    # build concat list + chapter metadata
    $tmp      = Join-Path $env:TEMP ("abmerge_" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    $listFile = Join-Path $tmp "list.txt"
    $metaFile = Join-Path $tmp "meta.txt"

    $sb = New-Object System.Text.StringBuilder
    foreach ($i in $ordered) {
        # ffmpeg concat: wrap in single quotes, escape embedded single quotes
        $p = $i.Path -replace "'", "'\''"
        [void]$sb.AppendLine("file '$p'")
    }
    [IO.File]::WriteAllText($listFile, $sb.ToString(), (New-Object Text.UTF8Encoding $false))

    # Chapter names: prefer whichever source is actually DISTINCT per file. Many rips set
    # every file's title tag to the book name, which would yield 20 identical chapters.
    $titleVals = $ordered | ForEach-Object { $_.Title }
    $nameVals  = $ordered | ForEach-Object { [IO.Path]::GetFileNameWithoutExtension($_.Path) }
    $titlesDistinct = (($titleVals | Where-Object { $_ } | Sort-Object -Unique).Count -eq $ordered.Count)
    $namesDistinct  = (($nameVals  | Sort-Object -Unique).Count -eq $ordered.Count)
    $chapMode = if ($titlesDistinct) { 'title' } elseif ($namesDistinct) { 'filename' } else { 'numbered' }
    Write-Output "  chapters: $chapMode"

    $mb = New-Object System.Text.StringBuilder
    [void]$mb.AppendLine(";FFMETADATA1")
    $startMs = 0
    $n = 1
    foreach ($i in $ordered) {
        $endMs = $startMs + [int][math]::Round($i.Duration * 1000)
        $chapTitle = switch ($chapMode) {
            'title'    { $i.Title }
            'filename' {
                $stem = [IO.Path]::GetFileNameWithoutExtension($i.Path)
                # drop a leading book-title prefix so chapters read "pt03" / "Chapter 4"
                $stem = $stem -replace '^\s*\d{4}\s*-\s*', ''
                if ($stem.Length -gt 60) { "Chapter $n" } else { $stem }
            }
            default    { "Chapter $n" }
        }
        if (-not $chapTitle) { $chapTitle = "Chapter $n" }
        $chapTitle = $chapTitle -replace '[\r\n=;#\\]', ' '
        [void]$mb.AppendLine("[CHAPTER]")
        [void]$mb.AppendLine("TIMEBASE=1/1000")
        [void]$mb.AppendLine("START=$startMs")
        [void]$mb.AppendLine("END=$endMs")
        [void]$mb.AppendLine("title=$chapTitle")
        $startMs = $endMs; $n++
    }
    [IO.File]::WriteAllText($metaFile, $mb.ToString(), (New-Object Text.UTF8Encoding $false))

    New-Item -ItemType Directory -Path $outDir -Force | Out-Null

    # codec decision
    $allAac = -not ($ordered | Where-Object { $_.Codec -ne 'aac' })
    if ($allAac) {
        $codecArgs = @('-c:a', 'copy')
        Write-Output "  encode: stream copy (lossless)"
    } else {
        $srcKbps = [int](($ordered | Where-Object BitRate -gt 0 | Measure-Object BitRate -Average).Average / 1000)
        if ($srcKbps -le 0) { $srcKbps = 64 }
        $target = [math]::Min([math]::Max($srcKbps, 48), 128)
        $codecArgs = @('-c:a', 'aac', '-b:a', "${target}k")
        Write-Output "  encode: mp3 -> aac @ ${target}k"
    }

    # NOTE: no -stats and no 2>&1 — PowerShell 5.1 turns a native exe's stderr into
    # ErrorRecords (NativeCommandError) even on success. Keep ffmpeg quiet instead.
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & $ff -hide_banner -nostats -loglevel fatal `
        -f concat -safe 0 -i $listFile -i $metaFile `
        -map 0:a -map_metadata 1 -map_chapters 1 `
        @codecArgs -vn -movflags +faststart -f mp4 -y -- $outFile
    $sw.Stop()

    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

    if (-not (Test-Path -LiteralPath $outFile)) { $failed += "$($b.Rel) :: no output"; continue }
    $chk = Get-AudioInfo $outFile
    if (-not $chk) { $failed += "$($b.Rel) :: output unreadable"; Remove-Item -LiteralPath $outFile -Force; continue }

    $diff = [math]::Abs($chk.Duration - $srcTotal)
    if ($diff -gt 5) {
        $failed += ("{0} :: duration mismatch (src {1:N0}s vs out {2:N0}s)" -f $b.Rel, $srcTotal, $chk.Duration)
        Remove-Item -LiteralPath $outFile -Force
        Write-Output "  FAILED duration check - output discarded"
        continue
    }
    $okCount++
    Write-Output ("  OK  {0:N1} min, {1:N0} MB, took {2:N0}s  [{3} chapters]" -f `
        ($chk.Duration/60), ((Get-Item -LiteralPath $outFile).Length/1MB), $sw.Elapsed.TotalSeconds, $ordered.Count)
}

Write-Output ""
Write-Output "==== DONE: $okCount converted, $($failed.Count) failed ===="
$failed | ForEach-Object { "  FAIL $_" }
