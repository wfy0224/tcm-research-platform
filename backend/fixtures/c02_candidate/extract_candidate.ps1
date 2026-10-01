$ErrorActionPreference = 'Stop'
$bundleRoot = $PSScriptRoot
$utf8 = [System.Text.UTF8Encoding]::new($false)
$revisionUrl = 'https://zh.wikisource.org/w/index.php?title=%E5%82%B7%E5%AF%92%E8%AB%96&oldid=2607901'
$htmlPath = Join-Path $bundleRoot 'upstream_revision_2607901.html'
$html = [System.IO.File]::ReadAllText($htmlPath, $utf8).Replace("`r`n", "`n")
if ($html -notmatch '"wgRevisionId":2607901(?:,|})') { throw 'Archived response does not identify revision 2607901.' }

# A deterministic HTML text-node baseline, not a browser screenshot/OCR.
# Block closing tags and br become LF; all other markup is removed; HTML
# entities are decoded once. Existing text whitespace is retained verbatim.
function Convert-HtmlText([string] $fragment) {
    if ($fragment -match '<(?:script|style)\b') { throw 'Unexpected non-text element in selected region.' }
    $value = [regex]::Replace($fragment, '<br\s*/?>|</(?:p|dt|dd)>', "`n")
    $value = [regex]::Replace($value, '<[^>]+>', '')
    return [System.Net.WebUtility]::HtmlDecode($value).Replace("`r`n", "`n")
}

function Write-Text([string] $name, [string] $value) {
    [System.IO.File]::WriteAllText((Join-Path $bundleRoot $name), $value, $utf8)
}

function Get-CanonicalHash([string] $value) {
    $bytes = $utf8.GetBytes($value.Replace("`r`n", "`n"))
    return [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
}

function Get-CodepointLength([string] $value) {
    $count = 0
    for ($index = 0; $index -lt $value.Length; $index++) {
        if ([char]::IsHighSurrogate($value[$index]) -and $index + 1 -lt $value.Length -and [char]::IsLowSurrogate($value[$index + 1])) { $index++ }
        $count++
    }
    return $count
}

$section = '辨太陽病脈證並治（上）第五'
$sectionStart = $html.IndexOf('<h3 id="' + $section + '"', [StringComparison]::Ordinal)
$contentStart = $html.IndexOf('</div>', $sectionStart, [StringComparison]::Ordinal) + 6
$sectionEnd = $html.IndexOf('<div class="mw-heading mw-heading3"><h3 id="辨太陽病脈證並治（中）第六"', $contentStart, [StringComparison]::Ordinal)
if ($sectionStart -lt 0 -or $contentStart -lt 6 -or $sectionEnd -le $contentStart) { throw 'Expected chapter boundaries absent.' }
$chapterHtml = $html.Substring($contentStart, $sectionEnd - $contentStart)
$chapterText = Convert-HtmlText $chapterHtml
Write-Text 'chapter_visible.txt' $chapterText
$artifacts = @(
    @{ file = 'upstream_revision_2607901.html'; canonicalization = 'CRLF_TO_LF_UTF8'; canonical_sha256 = Get-CanonicalHash $html; role = 'UPSTREAM_TEXT'; content_format = 'text/html'; use = 'raw acquisition evidence, not excerpt offset baseline' },
    @{ file = 'chapter_visible.txt'; canonicalization = 'CRLF_TO_LF_UTF8'; canonical_sha256 = Get-CanonicalHash $chapterText; role = 'UPSTREAM_TEXT'; content_format = 'text/plain'; use = 'excerpt offset baseline' }
)
$excerptRows = @()
foreach ($selection in @(
    @{ title = '桂枝湯方'; file = 'guizhi_tang.txt' },
    @{ title = '桂枝加葛根湯方'; file = 'guizhi_jia_ge_gen_tang.txt' },
    @{ title = '桂枝加附子湯方'; file = 'guizhi_jia_fu_zi_tang.txt' }
)) {
    $pattern = '<dt>' + [regex]::Escape($selection.title) + '</dt>\s*<dd>[^<]*</dd>\s*<dd>[^<]*</dd>'
    $matches = [regex]::Matches($chapterHtml, $pattern)
    if ($matches.Count -ne 1) { throw ('Expected unique complete formula block: ' + $selection.title) }
    $excerptText = Convert-HtmlText $matches[0].Value
    $startUtf16 = $chapterText.IndexOf($excerptText, [StringComparison]::Ordinal)
    if ($startUtf16 -lt 0 -or $chapterText.IndexOf($excerptText, $startUtf16 + 1, [StringComparison]::Ordinal) -ge 0) { throw 'Excerpt is not unique in chapter baseline.' }
    $startCodepoint = Get-CodepointLength $chapterText.Substring(0, $startUtf16)
    Write-Text $selection.file $excerptText
    $hash = Get-CanonicalHash $excerptText
    $artifacts += @{ file = $selection.file; canonicalization = 'CRLF_TO_LF_UTF8'; canonical_sha256 = $hash; role = 'EXCERPT' }
    $excerptRows += @{ file = $selection.file; title = $selection.title; source_file = 'chapter_visible.txt'; source_start = $startCodepoint; source_end = $startCodepoint + (Get-CodepointLength $excerptText); text_sha256 = $hash }
}

$pd = [regex]::Match($html, '<p>此作品在全世界都属于.*?</p>', [Text.RegularExpressions.RegexOptions]::Singleline)
$footer = [regex]::Match($html, '<li id="footer-info-copyright">.*?</li>', [Text.RegularExpressions.RegexOptions]::Singleline)
if (-not $pd.Success -or -not $footer.Success) { throw 'Expected actual upstream rights notices absent.' }
$rightsText = (Convert-HtmlText $pd.Value) + (Convert-HtmlText $footer.Value)
Write-Text 'rights_notice.txt' $rightsText
$artifacts += @{ file = 'rights_notice.txt'; canonicalization = 'CRLF_TO_LF_UTF8'; canonical_sha256 = Get-CanonicalHash $rightsText; role = 'RIGHTS_NOTICE' }
$manifest = [ordered]@{
    schema_version = 'c02-candidate/v1'
    selection_status = 'PROPOSED'
    data_owner_role = '测试人员'
    data_owner_name = $null
    expert_review_status = 'PENDING'
    expert_reviewer = $null
    outbound_authorized = $false
    source_url = 'https://zh.wikisource.org/wiki/%E5%82%B7%E5%AF%92%E8%AB%96'
    revision_url = $revisionUrl
    upstream_revision_id = 2607901
    section = $section
    rights_basis = 'Upstream page labels the ancient work PD-old/public domain; its footer separately states CC BY-SA 4.0 with possible additional terms. These observed notices are evidence for review, not project legal approval.'
    license_notice_url = $revisionUrl
    physical_page_mapping = $null
    offset_semantics = 'zero-based Unicode code points; half-open [source_start, source_end), against chapter_visible.txt after CRLF-to-LF only'
    extraction = [ordered]@{
        method = 'STATIC_HTML_TEXT_NODE_BLOCK_EXTRACTION'
        script = 'extract_candidate.ps1'
        html_archive = 'upstream_revision_2607901.html'
        html_canonical_sha256 = Get-CanonicalHash $html
        revision_evidence = 'Archived HTML RLCONF.wgRevisionId=2607901; requested URL contains oldid=2607901.'
        chapter_boundaries = 'After heading container for 辨太陽病脈證並治（上）第五, before heading container for 辨太陽病脈證並治（中）第六.'
        text_rule = 'Replace br and closing p/dt/dd tags with LF, remove remaining markup, decode HTML entities once; preserve all resulting text characters and whitespace. The chapter baseline contains no script/style. This is text extraction, not rendered-page layout.'
        excerpt_rule = 'Unique dt title followed by two dd nodes: ingredient/dose line and complete preparation/administration paragraph. Each excerpt is an exact substring of chapter_visible.txt.'
        rights_rule = 'Extract actual PD-old notice paragraph and footer-info-copyright element from the same archived HTML using the same text rule.'
    }
    review_cautions = @(
        'Upstream marks the page unproofread and warns that conversion from simplified characters may be inaccurate; no editorial correction was performed.'
        'Formula completeness and transcription are proposed for expert review only; no medical truth labels, benchmark qualification, production corpus import or freeze was performed.'
        'Physical edition/page mapping and a named data owner/expert are still unconfirmed.'
    )
    artifacts = $artifacts
    excerpts = $excerptRows
}
Write-Text 'manifest.json' (($manifest | ConvertTo-Json -Depth 12) + "`n")
Write-Output ('Created PROPOSED package: ' + $excerptRows.Count + ' excerpts; expert review PENDING.')
