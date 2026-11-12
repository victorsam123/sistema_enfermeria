param([Parameter(Mandatory=$true)][string]$InputPath, [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
$InputPath = [System.IO.Path]::GetFullPath($InputPath.Replace('/', '\'))
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath.Replace('/', '\'))
$application = $null
$document = $null
try {
    $extension = [System.IO.Path]::GetExtension($InputPath).ToLowerInvariant()
    if ($extension -eq '.docx') {
        $application = New-Object -ComObject Word.Application
        $application.Visible = $false
        $application.DisplayAlerts = 0
        $application.AutomationSecurity = 3
        $document = $application.Documents.Open($InputPath, $false, $true, $false)
        $document.ExportAsFixedFormat($OutputPath, 17)
    } elseif ($extension -in @('.xlsx', '.xls')) {
        $application = New-Object -ComObject Excel.Application
        $application.Visible = $false
        $application.DisplayAlerts = $false
        $application.AutomationSecurity = 3
        $document = $application.Workbooks.Open($InputPath, 0, $true)
        $document.ExportAsFixedFormat(0, $OutputPath)
    } else {
        throw 'Formato de documento no permitido.'
    }
    if (-not [System.IO.File]::Exists($OutputPath)) { throw 'No se genero el PDF.' }
} finally {
    if ($null -ne $document) {
        if ($extension -eq '.docx') { $document.Close(0) } else { $document.Close($false) }
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($null -ne $application) {
        $application.Quit()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($application)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
