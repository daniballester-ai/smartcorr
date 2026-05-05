# Documentação de Deploy e Integração: SmartCorr x DataCore

Este documento descreve o processo de instalação do pipeline preditivo **SmartCorr** no servidor e detalha como a arquitetura foi adaptada para ser orquestrada pelo **DataCore**.

---

## 1. Instalação no Servidor (Setup Inicial)

O projeto foi projetado para rodar de forma isolada, evitando conflitos de dependências com outras aplicações no servidor.

### Passos para Instalação
1. **Clonar/Copiar o Repositório:** 
   Copie a pasta completa `SmartCorr` para o diretório de destino no servidor (ex: `C:\TP_ML\BI_Ferramenta_Correlacao_Inteligente\SmartCorr`).
2. **Executar o Script de Setup:**
   Abra o PowerShell como Administrador e execute o script de provisionamento:
   ```powershell
   cd C:\TP_ML\BI_Ferramenta_Correlacao_Inteligente\SmartCorr
   .\setupVenv.ps1
   ```
   **O que o script faz?**
   - Verifica se a pasta `.venv` existe; se não, cria um ambiente virtual limpo.
   - Ativa o ambiente virtual.
   - Atualiza o `pip` e instala todas as dependências mapeadas no `requirements.txt`.

*Obs: Não é necessário ativar o ambiente virtual manualmente no dia a dia. Os scripts do DataCore farão isso de forma transparente.*

---

## 2. Estrutura Preparada para o DataCore

O DataCore orquestra jobs através de chamadas em linha de comando (CLI) e espera padrões específicos de entrada (parâmetros) e saída (códigos de erro e log via `stdout`). O projeto foi adaptado para atender a 100% desses requisitos.

### 2.1. Arquivos de Entrada (Entrypoints)
Foram criados dois fluxos distintos (dois arquivos `.bat`) que o DataCore chamará, dependendo do tipo de Job:

*   **`run_training.bat`** (Para o Job de Treinamento Noturno/Semanal)
*   **`run_inference.bat`** (Para o Job de Inferência Intraday/A cada X minutos)

Ambos os `.bat` apenas repassam os parâmetros fornecidos pelo DataCore (`%*`) para seus respectivos arquivos `.py` (`run_training.py` e `run_inference.py`).

### 2.2. Adaptação dos Scripts Python (`run_*.py`)
Os arquivos Python foram preparados com as seguintes premissas de integração:

1. **Gestão Transparente do Ambiente Virtual:**
   Eles injetam dinamicamente o diretório `site-packages` do `.venv` no `sys.path`. Isso significa que o DataCore pode simplesmente chamar `py run_inference.py` sem precisar fazer um `activate` prévio no `.bat`.
2. **Recepção de Parâmetros do DataCore:**
   O script utiliza a biblioteca `argparse` para absorver os parâmetros padrão que o DataCore envia:
   - `--InitialDateCtrl`
   - `--FinalDateCtrl`
   - `--ProcessTable`
   - `--ProcessKey`
   - `--connectionString`
3. **Controle de Modos Automático:**
   Para garantir que a pipeline rode no modo correto sem intervenção manual, os scripts editam temporariamente a chave `mode` dentro do arquivo `params.yaml` para `training` ou `inference` antes de iniciar as etapas de ETL.
4. **Retorno Padronizado (Exit Codes):**
   - Em caso de **Sucesso**, o script imprime a quantidade de linhas processadas via `sys.stdout.write()` e encerra com `sys.exit(0x00)`.
   - Em caso de **Falha**, ele captura a exceção, imprime o erro via `stdout` para aparecer no painel do DataCore, e encerra com `sys.exit(0x01)`.

### 2.3. Gestão de Credenciais de Banco de Dados (Fallback Seguro)
A autenticação do SQL Server foi um ponto crítico ajustado no arquivo `src/database.py`:

*   **Execução pelo DataCore (Produção):** O script lê o parâmetro `--connectionString` injetado pelo DataCore, limpa possíveis aspas residuais da linha de comando, e força o driver `pyodbc` a usar exatamente as credenciais (SQL Auth) fornecidas pelo orquestrador.
*   **Execução Local (Desenvolvimento):** Se o script for executado localmente (sem a `--connectionString`), ele entra em modo de **Fallback** seguro, utilizando a Autenticação Integrada do Windows (`Trusted_Connection=yes`) para permitir o debug pelo desenvolvedor.

---

## 3. Configuração no Painel do DataCore

Para configurar o pipeline na interface web do DataCore:

### Job 1: Treinamento (Ex: Execução Semanal ou D-1)
*   **Tipo de Step:** Arquivo Batch / Script
*   **Caminho do Executável:** `C:\TP_ML\BI_Ferramenta_Correlacao_Inteligente\SmartCorr\run_training.bat`
*   **Parâmetros de Conexão:** Certifique-se de que a Connection String fornecida pelo DataCore possua as credenciais de leitura/escrita necessárias no SQL Server (Ex: `UID=user;PWD=pass`).

### Job 2: Inferência (Ex: Execução a cada 30 minutos)
*   **Tipo de Step:** Arquivo Batch / Script
*   **Caminho do Executável:** `C:\TP_ML\BI_Ferramenta_Correlacao_Inteligente\SmartCorr\run_inference.bat`
*   **Parâmetros de Conexão:** Mesma configuração do Job de Treinamento.

---

## 4. Troubleshooting Básico

*   **Erro `ModuleNotFoundError` no DataCore:** Ocorrerá se o `.venv` não foi criado. Acesse o servidor e execute o `setupVenv.ps1`.
*   **Erro de Login no Banco (`untrusted domain`):** Indica que a connection string do DataCore está vazia ou mal formatada. Valide a configuração do processo no painel do DataCore.
*   **Acompanhamento da Execução:** Todos os logs detalhados (ETL, Feature Engineering, Modelagem) são gerados na pasta `logs/` com a data do dia (ex: `smartcorr_pipeline_YYYYMMDD.log`). Se o DataCore apontar erro genérico, esse arquivo local mostrará o stack trace exato.