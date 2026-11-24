# TimeTracker Sync & Analytics Dashboard (com 2FA TOTP)

Serviço em Python para sincronização de apontamentos de horas entre plataformas de *time tracking* e CRM/gestão de projetos, acompanhado de um **Dashboard Web Analítico protegido por autenticação em 2 fatores (TOTP — RFC 6238)**.

## Destaques Técnicos

- **Compensação de Fuso Horário:** converte timestamps heterogêneos (ex.: APIs em `UTC+3` ou `UTC`) para o fuso operacional local (`America/Sao_Paulo`, `UTC-3`) antes de consolidar médias e janelas diárias.
- **Mapeamento Estrito de Usuários (Guardrail):** nunca cria contas órfãs automaticamente; registros de usuários fora do `users_map.json` são registrados em fila de auditoria.
- **Motor de Auditoria:** detecta automaticamente dias com apontamento acima do teto configurável, registros sem descrição ou tarefas sem projeto associado.
- **Autenticação 2FA (TOTP — RFC 6238):** implementação nativa em Python com tolerância de janela (`±30s`), compatível com Google Authenticator, Authy e 1Password.
- **Zero Dependências Pesadas para Demo:** servidor HTTP embutido + SQLite + dashboard responsivo com gráficos interativos (Chart.js).

## Como Executar (Modo Demonstração)

```bash
# 1. Popula o banco SQLite com dados sintéticos de uma equipe fictícia
python -m app.seed_demo

# 2. Inicia o dashboard web na porta 8088 (imprime a senha e o código TOTP demo no terminal)
python -m app.server --demo

# 3. Executa os testes automatizados
pytest -v
```

Acesse `http://127.0.0.1:8088` e entre usando as credenciais de demonstração exibidas no console.

## Estrutura do Projeto

```text
timetracker-crm-dashboard/
├── app/
│   ├── __init__.py
│   ├── database.py     # Camada SQLite e agregações analíticas
│   ├── seed_demo.py    # Gerador de dados 100% sintéticos
│   ├── server.py       # Servidor web com login + 2FA TOTP + gráficos
│   ├── sync_engine.py  # Normalização de timezone, mapeamento estrito e alertas
│   └── totp.py         # Implementação RFC 6238 (TOTP)
├── tests/
│   └── test_timetracker.py
├── .env.example
├── .gitignore
├── users_map.example.json
└── requirements.txt
```
