# TecnologiaIN

Sistema de inventário de T.I construído como prova de conceito em Python.

## Estrutura do Projeto

- `inventory/models.py` — modelos de domínio, papéis de acesso e exceções.
- `inventory/service.py` — regras de negócio para gerenciamento de itens, categorias,
  movimentações, notificações, auditoria e relatórios.
- `inventory/tests/` — testes unitários com `pytest` cobrindo os principais fluxos.
- `webapp/` — aplicação Flask com páginas HTML responsivas conectadas ao serviço de
  inventário.

## Executando a interface web

1. (Opcional, porém recomendado) Crie e ative um ambiente virtual. Exemplos:

   **Windows PowerShell**

   ```powershell
   py -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   **Linux/macOS**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Instale as dependências necessárias utilizando o interpretador em uso:

   ```bash
   python -m pip install -r requirements.txt
   ```

   > 💡 No Windows, execute o comando acima a partir da **raiz do repositório**
   > (a pasta que contém `requirements.txt`). Se preferir, rode o script
   > `scripts/run.ps1`, que automaticamente posiciona o PowerShell no diretório
   > correto antes de instalar os pacotes.

3. Inicie o servidor Flask apontando para a fábrica de aplicação. Em ambientes
   onde o comando `flask` não está no `PATH` (como instalações da Microsoft
   Store no Windows), utilize o módulo da biblioteca padrão:

   ```bash
   python -m flask --app webapp.app run
   ```

   Caso prefira automatizar esse processo, utilize os scripts utilitários:

   - `scripts/run.sh` (Linux/macOS) — aceite opcional `--skip-install` para
     reutilizar dependências já instaladas;
   - `scripts/run.ps1` (Windows PowerShell) — aceite opcional `-SkipInstall`
     para pular a reinstalação.

   Por padrão o sistema ficará disponível em <http://127.0.0.1:5000/>.

3. Acesse o navegador, escolha um dos usuários de demonstração e navegue pelas
   seções de dashboard, itens, categorias, movimentações e auditoria.

### Solução de problemas comuns

- **"Could not open requirements file"**: confirme que você está dentro da
  pasta correta executando `Get-ChildItem requirements.txt` (PowerShell) ou
  `ls requirements.txt` (Linux/macOS). Se o arquivo aparecer, rode o comando de
  instalação novamente; caso contrário, navegue até a pasta que contém o
  repositório extraído (por exemplo `cd TecnologiaIN-codex-create-ti-inventory-system-code`).
- **`pip` ou `pytest` não reconhecidos**: utilize a forma modular do Python,
  como `python -m pip install ...` e `python -m pytest`, que independem da
  variável `PATH`.
- **`flask` não reconhecido no PowerShell**: execute `python -m flask --app webapp.app run`
  em vez de `flask ...`, ou use o script `scripts\run.ps1` que já faz esse
  redirecionamento automaticamente.
- **"Error: Could not import 'webapp.app'"**: verifique se as dependências
  foram instaladas sem erros e se o comando está sendo executado na raiz do
  projeto. Em seguida, tente novamente com `python -m flask --app webapp.app run`.

### Importar ou exportar registros em Excel

- **Exportar**: em Itens, Categorias ou Movimentações clique em “Exportar
  Excel” para baixar um arquivo `.xlsx` com os dados listados.
- **Importar**: utilize o botão “Importar Excel” nas mesmas páginas para enviar
  uma planilha `.xlsx`. As colunas esperadas são exibidas no cabeçalho do
  arquivo exportado e permitem criar novos registros ou atualizar os existentes.
  Apenas usuários com perfil de gestor podem realizar importações ou edições em
  massa.

## Como executar os testes

```bash
python -m pytest
```
