# Overnight runner: finish the lossless AAC merges, then the slower MP3 -> AAC transcodes.
# Non-destructive: writes only to \\NAS\Media\Audio\merged. Originals are never touched.
$root = "C:\Users\Pat\Projects\nas-homelab\scripts"
$list = "$root\absbooks.txt"

Write-Output "########## PHASE 1: AAC (lossless stream copy) ##########"
Write-Output "started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
& powershell -ExecutionPolicy Bypass -File "$root\Merge-Audiobooks.ps1" -Only aac -BookList $list

Write-Output ""
Write-Output "########## PHASE 2: MP3 -> AAC (transcode) ##########"
Write-Output "started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
& powershell -ExecutionPolicy Bypass -File "$root\Merge-Audiobooks.ps1" -Only mp3 -BookList $list

Write-Output ""
Write-Output "########## ALL DONE: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ##########"
