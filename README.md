# Caderno de Questões Inteligente

Aplicação Streamlit para importar questões, responder em modo quiz, revisar erros com espaçamento e visualizar métricas.

### Funcionalidades
- Importar questões via JSON (aba "Importar JSON").
- Quiz por disciplina/aula com agendamento de revisão.
- Caderno de Erros com treino rápido e remoção automática ao acertar.
- Revisão por data de vencimento.
- Banco de questões com filtros e exportações (JSON/CSV/Excel).
- Painel de desempenho com métricas e gráficos.

### Requisitos
- Python 3.11 (fixado em `runtime.txt`).
- Dependências em `requirements.txt` (Streamlit, Pandas, OpenPyXL, Pydantic 1.x).

### Executar localmente
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Ao iniciar, um banco SQLite local `questoes.db` será criado automaticamente.

### Importar dados
- Vá na aba "Importar JSON" e cole uma lista JSON de questões.
- Exemplo mínimo de item:
```json
{
  "numero": "1",
  "tipo": "multipla",
  "disciplina": "Direito Constitucional",
  "aula": "Aula 01",
  "origem_pdf": "simulado_01.pdf",
  "enunciado": "Texto da questão...",
  "alternativas": ["A) ...", "B) ...", "C) ...", "D) ...", "E) ..."],
  "resposta_correta": "B",
  "comentario": "Comentário do professor"
}
```

### Migrações do banco (opcional)
Se você já tem um `questoes.db` antigo, pode normalizar colunas/índices:
```bash
python migrate_db.py --db questoes.db
```

### Deploy no Streamlit Community Cloud
1) Faça push deste diretório para um repositório GitHub.
2) Em https://share.streamlit.io/ crie um "New app" e selecione o repositório/branch.
3) Defina o arquivo principal como `app.py`.
4) O arquivo `runtime.txt` já fixa `python-3.11`.

Observações importantes:
- Armazenamento: no Streamlit Cloud, `questoes.db` é efêmero; ao reiniciar, os dados podem ser perdidos. Use a aba de importação após reinícios a frio ou configure um banco externo para persistência real.
- Persistência externa (Supabase/Postgres): já suportado. Veja abaixo.

### Usar Supabase (Postgres) — persistência real
O app detecta automaticamente um Postgres externo quando a variável/secret `DATABASE_URL` (ou `st.secrets["database"]["url"]) está definida. Caso contrário, usa SQLite local.

1) Crie um projeto no Supabase e obtenha a "Connection string" (URI Postgres).
2) No Streamlit Cloud, abra "Settings → Secrets" e adicione:
   ```toml
   [database]
   url = "postgresql://usuario:senha@host:5432/postgres"
   ```
   Observação: a URL deve aceitar TLS; se não tiver `sslmode`, o app aplica `sslmode=require` automaticamente.
3) Dependências: `psycopg2-binary` já está em `requirements.txt`.
4) Deploy/restart: ao iniciar, o app criará a tabela/índices automaticamente no Postgres (se não existirem).

Esquema criado (Postgres):
```
questoes (
  id SERIAL PRIMARY KEY,
  numero TEXT,
  tipo TEXT,
  disciplina TEXT,
  aula TEXT,
  origem_pdf TEXT,
  enunciado TEXT,
  alternativas TEXT,
  resposta_correta TEXT,
  comentario TEXT,
  status TEXT DEFAULT 'nao_respondida',
  data_resposta TEXT,
  proxima_revisao TEXT
)
```
As comparações de datas usam strings ISO (`YYYY-MM-DD`), o que mantém ordenação correta em operações `<=`.

### Usar Supabase via API key (SDK)
O app também pode usar diretamente a API do Supabase (PostgREST) quando os secrets `supabase.url` e `supabase.service_key` (ou `anon_key`, se você tiver políticas RLS) estiverem definidos. Nesse modo, nenhuma conexão Postgres direta é usada.

Exemplo de secrets (Streamlit → Settings → Secrets):
```toml
[supabase]
url = "https://<project-ref>.supabase.co"
# Prefira a service_key para rodar no servidor com permissões completas
service_key = "<service_role_key>"
# ou, alternativamente, se você tiver RLS configurado para o anon_key:
# anon_key = "<anon_key>"
```

Observações:
- A criação de tabelas/índices não é possível via PostgREST; crie-as pelo SQL Editor do Supabase usando o DDL abaixo (mesmo esquema do Postgres).
- Com `anon_key`, você precisará de políticas RLS permitindo SELECT/INSERT/UPDATE/DELETE na tabela `questoes`.

### Exemplo de secrets
Você pode copiar o arquivo de exemplo e preencher sua URL do Supabase:

```
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Edite o valor `url` em `[database]` com a sua connection string Postgres.

### Migrar SQLite → Supabase
Se você já possui dados no `questoes.db` (local) e quer enviá-los para o Postgres do Supabase, use o script de migração:

```bash
# Opção A: informar a URL pelo argumento
python migrate_to_supabase.py \
  --sqlite questoes.db \
  --pg-url "postgresql://usuario:senha@db.<project-ref>.supabase.co:5432/postgres" \
  --truncate

# Opção B: usar variável de ambiente
export DATABASE_URL="postgresql://usuario:senha@db.<project-ref>.supabase.co:5432/postgres"
python migrate_to_supabase.py --sqlite questoes.db --truncate
```

Notas:
- `--truncate` limpa a tabela de destino antes de migrar e reinicia a sequência do `id`.
- Sem `--truncate`, o script faz upsert por `id` (insere/atualiza registros existentes).
- O script cria a tabela/índices no Postgres se ainda não existirem.

Alternativa com API key (sem connection string Postgres):
```bash
# Via argumentos
python migrate_to_supabase_api.py \
  --sqlite questoes.db \
  --supabase-url "https://<project-ref>.supabase.co" \
  --supabase-key "<service_role_key>" \
  --truncate

# Ou via variáveis de ambiente
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="<service_role_key>"
python migrate_to_supabase_api.py --sqlite questoes.db --truncate
```

Notas (API):
- `--truncate` apaga os registros via DELETE em lotes.
- Este método não cria a tabela; se a `questoes` não existir, o script mostrará o DDL para você criar no SQL Editor.
- Use a `service_role_key` para evitar bloqueios de RLS durante a migração.

### Estrutura
```
app.py              # UI e fluxo das abas
db.py               # Acesso a dados (SQLite por padrão)
models.py           # Modelo Pydantic para importação/validação
migrate_db.py       # Script de migração/normalização
migrate_to_supabase.py # Script para migrar dados do SQLite para Supabase/Postgres
requirements*.txt   # Dependências
runtime.txt         # Versão do Python para o deploy
```

### Licença
Uso interno/projeto pessoal. Adapte conforme necessário.
