$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$extensionRoot = (Resolve-Path (Join-Path $scriptDirectory "../..")).Path

if (-not (Test-Path (Join-Path $extensionRoot "pyproject.toml"))) {
    [Console]::Error.WriteLine("spec-kit-linear runtime is incomplete: pyproject.toml is missing")
    exit 4
}

$env:PYTHONPATH = "$(Join-Path $extensionRoot 'src')$([IO.Path]::PathSeparator)$env:PYTHONPATH"
& uv run --frozen --offline --project $extensionRoot python -m spec_kit_linear.cli @args
exit $LASTEXITCODE
