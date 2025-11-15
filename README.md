<<<<<<< HEAD
# caderno_erros
=======
## Caderno de Questões Inteligente

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
O app detecta automaticamente um Postgres externo quando a variável/secret `DATABASE_URL` (ou `st.secrets["database"]["url"]`) está definida. Caso contrário, usa SQLite local.

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

### Estrutura
```
app.py              # UI e fluxo das abas
db.py               # Acesso a dados (SQLite por padrão)
models.py           # Modelo Pydantic para importação/validação
migrate_db.py       # Script de migração/normalização
requirements*.txt   # Dependências
runtime.txt         # Versão do Python para o deploy
```

### Licença
Uso interno/projeto pessoal. Adapte conforme necessário.
>>>>>>> f19deb9 (feat: Implement database management and migration for question tracking)
