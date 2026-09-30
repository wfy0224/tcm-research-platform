# Run only the existing test runtime/database through a temporary internal network.
$ErrorActionPreference = 'Stop'
$taskNetwork = 'tcm-vib48-offline'
$taskRelay = 'tcm-vib48-offline-forward'
$taskBackendPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$taskFrontendCheck = Join-Path $taskBackendPath '../frontend/scripts/check_retrieval_offline_e2e.mjs'
$taskChangedRuntime = $false
$taskAttachedDb = $false
$taskCreatedNetwork = $false
$taskCreatedRelay = $false
try {
    $taskExisting = docker network ls --format '{{.Name}}'
    if ($taskExisting -contains $taskNetwork) { throw 'Acceptance network already exists' }
    docker network create --internal $taskNetwork
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create internal network' }
    $taskCreatedNetwork = $true
    docker network connect --alias retrieval-db $taskNetwork tcm-handoff-test
    if ($LASTEXITCODE -ne 0) { throw 'Cannot attach isolated database' }
    $taskAttachedDb = $true
    docker network connect --alias retrieval-api $taskNetwork tcm-vib54-py
    if ($LASTEXITCODE -ne 0) { throw 'Cannot attach API runtime' }
    docker network disconnect bridge tcm-vib54-py
    if ($LASTEXITCODE -ne 0) { throw 'Cannot isolate runtime' }
    $taskChangedRuntime = $true
    docker run -d --name $taskRelay --network bridge -p 127.0.0.1:18065:18065 --mount "type=bind,source=$taskBackendPath,target=/workspace/backend,readonly" python:3.11-slim python /workspace/backend/scripts/check_retrieval_offline_e2e.py --forward
    if ($LASTEXITCODE -ne 0) { throw 'Cannot start loopback relay' }
    $taskCreatedRelay = $true
    docker network connect $taskNetwork $taskRelay
    if ($LASTEXITCODE -ne 0) { throw 'Cannot connect relay' }
    $taskIsolated = docker inspect tcm-vib54-py | ConvertFrom-Json
    $taskAttachments = @($taskIsolated.NetworkSettings.Networks.PSObject.Properties.Name)
    if ($taskAttachments.Count -ne 1 -or $taskAttachments[0] -ne $taskNetwork) { throw 'API has external attachment' }
    node $taskFrontendCheck
    if ($LASTEXITCODE -ne 0) { throw 'Offline E2E failed' }
} finally {
    if ($taskChangedRuntime) { docker network connect bridge tcm-vib54-py }
    if ($taskCreatedNetwork) { docker network disconnect $taskNetwork tcm-vib54-py }
    if ($taskCreatedRelay) { docker stop $taskRelay | Out-Null; docker rm $taskRelay | Out-Null }
    if ($taskAttachedDb) { docker network disconnect $taskNetwork tcm-handoff-test }
    if ($taskCreatedNetwork) { docker network rm $taskNetwork | Out-Null }
    Write-Output 'Acceptance-only network restored; business/preview containers unchanged.'
}
