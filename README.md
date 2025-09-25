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

3. Inicie o servidor Flask apontando para a fábrica de aplicação. Em ambientes
   onde o comando `flask` não está no `PATH` (como instalações da Microsoft
   Store no Windows), utilize o módulo da biblioteca padrão:

   ```bash
   python -m flask --app webapp.app run
   ```

   Por padrão o sistema ficará disponível em <http://127.0.0.1:5000/>.

3. Acesse o navegador, escolha um dos usuários de demonstração e navegue pelas
   seções de dashboard, itens, categorias, movimentações e auditoria.

## Como executar os testes

```bash
python -m pytest
```
