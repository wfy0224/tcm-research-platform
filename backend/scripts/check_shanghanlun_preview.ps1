param(
    [string]$BaseUrl = 'http://127.0.0.1:5173'
)

$ErrorActionPreference = 'Stop'
$cases = @(
    @{ Query = '太阳病的主要脉象和症状是什么'; Expected = '太陽之為病' },
    @{ Query = '发热出汗怕风脉缓是什么证'; Expected = '名為中風' },
    @{ Query = '恶寒体痛呕逆脉紧称为什么'; Expected = '名為傷寒' },
    @{ Query = '发热口渴但不怕冷属于什么病'; Expected = '為溫病' },
    @{ Query = '太阳病在一天中何时容易缓解'; Expected = '從巳至未上' },
    @{ Query = '头痛发热汗出恶风对应哪种汤'; Expected = '桂枝湯主之' }
)

$failed = 0
foreach ($case in $cases) {
    $query = [uri]::EscapeDataString($case.Query)
    $results = Invoke-RestMethod -Uri "$BaseUrl/api/v1/retrieval/search?query=$query&limit=5" -TimeoutSec 60
    $rank = 0
    for ($index = 0; $index -lt $results.Count; $index++) {
        if ($results[$index].quote_text.Contains($case.Expected)) {
            $rank = $index + 1
            break
        }
    }
    if ($rank -eq 0) { $failed++ }
    $top = if ($results.Count -gt 0) { $results[0] } else { $null }
    if (-not $top -or $null -eq $top.rerank_score -or
        -not ($top.matched_channels -contains 'vector')) { $failed++ }
    $channels = if ($top) { $top.matched_channels -join ',' } else { 'none' }
    $rerank = if ($top) { $top.rerank_score } else { 'none' }
    Write-Output "$($case.Query) | expected_rank=$rank | top_channels=$channels | top_rerank=$rerank"
}
$broad = [uri]::EscapeDataString('太阳病')
$broadResults = Invoke-RestMethod -Uri "$BaseUrl/api/v1/retrieval/search?query=$broad&limit=5" -TimeoutSec 60
if ($broadResults.Count -eq 0 -or $null -eq $broadResults[0].rerank_score -or
    -not ($broadResults[0].matched_channels -contains 'vector')) { $failed++ }
Write-Output "screenshot_query_returned=$($broadResults.Count) real_rerank=$($broadResults[0].rerank_score)"
$negative = [uri]::EscapeDataString('现代胰岛素剂量如何计算')
$negativeResults = Invoke-RestMethod -Uri "$BaseUrl/api/v1/retrieval/search?query=$negative&limit=5" -TimeoutSec 60
Write-Output "unrelated_query_returned=$($negativeResults.Count) (diagnostic only; no relevance cutoff is calibrated)"
Write-Output "positive_checks=$($cases.Count + 1) failed=$failed"
if ($failed -ne 0) { exit 1 }
