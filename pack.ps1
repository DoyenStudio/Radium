$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$packRoot = $PSScriptRoot
$packTarget = Join-Path $packRoot 'addon.zip'
if (Test-Path -LiteralPath $packTarget) {
    Remove-Item -LiteralPath $packTarget
}
$packArchive = [IO.Compression.ZipFile]::Open($packTarget, 'Create')
try {
    foreach ($packName in @('behavior_pack', 'resource_pack')) {
        $packFolder = Join-Path $packRoot $packName
        foreach ($packFile in Get-ChildItem -LiteralPath $packFolder -File -Recurse) {
            $packEntry = $packFile.FullName.Substring($packRoot.Length + 1).Replace('\', '/')
            if ($packEntry -match '(^|/)(__pycache__|\.git)(/|$)' -or $packEntry -match '\.py[co]$') {
                continue
            }
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $packArchive, $packFile.FullName, $packEntry, 'Optimal') | Out-Null
        }
    }
} finally {
    $packArchive.Dispose()
}
Write-Output $packTarget
