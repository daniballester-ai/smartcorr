if (-not (Test-Path -Path ".venv")) {
    Write-Host "--- Criando ambiente virtual... ---" -ForegroundColor Cyan
    py -m venv .venv
}

Write-Host "--- Ativando ambiente... ---" -ForegroundColor Cyan
# O comando abaixo ativa o venv na sessão atual
. .\.venv\Scripts\Activate.ps1

if (Test-Path -Path "requirements.txt") {
    Write-Host "--- Verificando dependências... ---" -ForegroundColor Cyan
    python -m pip install --upgrade pip
    pip install -r requirements.txt
}

Write-Host "--- AMBIENTE ATIVO. PODE TRABALHAR. ---" -ForegroundColor Green
# Isso mantém o terminal aberto e no contexto do venv

PAUSE