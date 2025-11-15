import json
import os
import sqlite3
from datetime import datetime, timedelta

# Optional: Streamlit secrets for external DB (Supabase/Postgres)
try:
    import streamlit as st  # type: ignore
except Exception:  # streamlit not strictly required for local scripts
    st = None  # noqa: N816

DB_NAME = "questoes.db"

# Canonical column order used across backends
COLUMNS = [
    "id",
    "numero",
    "tipo",
    "disciplina",
    "aula",
    "origem_pdf",
    "enunciado",
    "alternativas",
    "resposta_correta",
    "comentario",
    "status",
    "data_resposta",
    "proxima_revisao",
]


def _get_pg_url() -> str | None:
    """Retrieve Postgres connection URL from Streamlit secrets or env.

    Looks for:
    - st.secrets["database"]["url"]
    - st.secrets["supabase"]["url"]
    - env var DATABASE_URL
    Returns full URL string or None if not configured.
    """
    # Prefer Streamlit secrets when available
    try:
        if st is not None and hasattr(st, "secrets"):
            if "database" in st.secrets and st.secrets["database"].get("url"):
                return st.secrets["database"]["url"]
            if "supabase" in st.secrets and st.secrets["supabase"].get("url"):
                return st.secrets["supabase"]["url"]
    except Exception:
        pass
    # Fallback to environment variable
    return os.environ.get("DATABASE_URL")


def _get_supabase_cfg() -> tuple[str | None, str | None]:
    """Return (url, key) from Streamlit secrets for Supabase API if available.

    Looks for:
    - st.secrets["supabase"]["url"], and either service_key (preferred) or anon_key
    Returns (url, key) or (None, None) if not configured.
    """
    try:
        if st is not None and hasattr(st, "secrets") and "supabase" in st.secrets:
            sb = st.secrets["supabase"]
            url = sb.get("url")
            key = sb.get("service_key") or sb.get("anon_key")
            if url and key:
                return str(url), str(key)
    except Exception:
        pass
    return None, None


def _ensure_sslmode(url: str) -> str:
    # Supabase requires TLS; add sslmode=require if not present
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def _using_postgres() -> bool:
    return bool(_get_pg_url())


def _using_supabase_api() -> bool:
    url, key = _get_supabase_cfg()
    return bool(url and key)


def get_backend_label() -> str:
    if _using_supabase_api():
        return "Supabase API"
    if _using_postgres():
        return "Postgres (Supabase)"
    return "SQLite (local)"

def connect():
    """Open a DB connection for SQL backends (Postgres/SQLite).

    Supabase API mode does not use a SQL connection; functions will call the
    HTTP API via the Supabase Python SDK instead.
    """
    if _using_postgres() and not _using_supabase_api():
        pg_url = _ensure_sslmode(_get_pg_url())
        try:
            import psycopg2  # type: ignore
        except Exception as ex:
            raise RuntimeError("psycopg2 is required for Postgres. Add 'psycopg2-binary' to requirements.txt") from ex
        conn = psycopg2.connect(pg_url)
        return conn
    # SQLite fallback
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    conn.commit()
    return conn


_sb_client = None


def _get_supabase_client():
    global _sb_client
    if _sb_client is not None:
        return _sb_client
    url, key = _get_supabase_cfg()
    if not (url and key):
        return None
    try:
        from supabase import create_client  # type: ignore
    except Exception as ex:
        raise RuntimeError("'supabase' package is required. Add 'supabase' to requirements.txt") from ex
    _sb_client = create_client(url, key)
    return _sb_client


def _adapt_query(query: str) -> str:
    """Adapt placeholder style between SQLite (?) and Postgres (%s)."""
    if _using_postgres():
        # naive but safe for our static queries
        return query.replace("?", "%s")
    return query


def _exec(conn, query: str, params: list | tuple = ()):  # minimal cursor exec helper
    q = _adapt_query(query)
    cur = conn.cursor()
    cur.execute(q, params)
    return cur

def create_table():
    if _using_supabase_api():
        # In API mode we cannot create tables via PostgREST.
        # Try a lightweight probe; if the table is missing, inform the user with SQL.
        sb = _get_supabase_client()
        try:
            sb.table("questoes").select("id").limit(1).execute()
        except Exception as ex:
            if st is not None:
                st.warning(
                    "Tabela 'questoes' não encontrada no Supabase. Crie-a no SQL Editor com o DDL mostrado no README (ou me peça que eu cole aqui)."
                )
            # Do not raise to allow UI to load; operations will fail gracefully if attempted.
        return
    # SQL backends
    conn = connect()
    try:
        if _using_postgres():
            _exec(
                conn,
                """
                CREATE TABLE IF NOT EXISTS questoes (
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
                """,
            )
            # Indexes
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_questoes_status ON questoes(status)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_questoes_proxrev ON questoes(proxima_revisao)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_questoes_disciplina ON questoes(disciplina)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_questoes_aula ON questoes(aula)")
        else:
            _exec(
                conn,
                """
                CREATE TABLE IF NOT EXISTS questoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                """,
            )
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_questoes_status ON questoes(status)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_questoes_proxrev ON questoes(proxima_revisao)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_questoes_disciplina ON questoes(disciplina)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_questoes_aula ON questoes(aula)")
        conn.commit()
    finally:
        conn.close()

def insert_question(data: dict):
    alternativas_json = json.dumps(data.get("alternativas", []), ensure_ascii=False)
    if _using_supabase_api():
        sb = _get_supabase_client()
        payload = {
            "numero": data.get("numero"),
            "tipo": data.get("tipo"),
            "disciplina": data.get("disciplina"),
            "aula": data.get("aula"),
            "origem_pdf": data.get("origem_pdf"),
            "enunciado": data.get("enunciado"),
            "alternativas": alternativas_json,
            "resposta_correta": data.get("resposta_correta"),
            "comentario": data.get("comentario"),
        }
        sb.table("questoes").insert(payload).execute()
        return
    conn = connect()
    try:
        _exec(
            conn,
            """
            INSERT INTO questoes (numero, tipo, disciplina, aula, origem_pdf, enunciado, alternativas, resposta_correta, comentario)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("numero"),
                data.get("tipo"),
                data.get("disciplina"),
                data.get("aula"),
                data.get("origem_pdf"),
                data.get("enunciado"),
                alternativas_json,
                data.get("resposta_correta"),
                data.get("comentario"),
            ),
        )
        conn.commit()
    finally:
        conn.close()

def _build_filters(filters: dict | None, status: str | None):
    query = "SELECT * FROM questoes"
    params = []
    where = []
    if filters:
        if filters.get("disciplina"):
            where.append("disciplina = ?")
            params.append(filters["disciplina"])
        if filters.get("aula"):
            where.append("aula = ?")
            params.append(filters["aula"])
    if status:
        where.append("status = ?")
        params.append(status)
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY id"
    return query, params

def get_all_questions(filters: dict | None = None, status: str | None = None):
    if _using_supabase_api():
        sb = _get_supabase_client()
        q = sb.table("questoes").select("*")
        if filters:
            if filters.get("disciplina"):
                q = q.eq("disciplina", filters["disciplina"])
            if filters.get("aula"):
                q = q.eq("aula", filters["aula"])
        if status:
            q = q.eq("status", status)
        q = q.order("id")
        res = q.execute()
        data = res.data or []
        rows = [tuple(item.get(col) for col in COLUMNS) for item in data]
        return rows
    conn = connect()
    query, params = _build_filters(filters, status)
    try:
        cur = _exec(conn, query, params)
        rows = cur.fetchall()
    finally:
        conn.close()
    return rows

def today_date_str():
    return datetime.now().date().isoformat()

def schedule_next_date(is_correct: bool, marked_doubt: bool = False):
    today = datetime.now().date()
    if marked_doubt:
        return (today + timedelta(days=1)).isoformat()
    return (today + (timedelta(days=7) if is_correct else timedelta(days=1))).isoformat()

def get_due_for_review(filters: dict | None = None):
    today = today_date_str()
    if _using_supabase_api():
        sb = _get_supabase_client()
        q = sb.table("questoes").select("*").lte("proxima_revisao", today)
        if filters:
            if filters.get("disciplina"):
                q = q.eq("disciplina", filters["disciplina"])
            if filters.get("aula"):
                q = q.eq("aula", filters["aula"])
        q = q.order("proxima_revisao")
        res = q.execute()
        data = res.data or []
        rows = [tuple(item.get(col) for col in COLUMNS) for item in data]
        return rows
    conn = connect()
    query = (
        "SELECT * FROM questoes WHERE proxima_revisao IS NOT NULL AND proxima_revisao <= ?"
    )
    params = [today]
    if filters:
        if filters.get("disciplina"):
            query += " AND disciplina = ?"
            params.append(filters["disciplina"])
        if filters.get("aula"):
            query += " AND aula = ?"
            params.append(filters["aula"])
    query += " ORDER BY proxima_revisao"
    try:
        cur = _exec(conn, query, params)
        rows = cur.fetchall()
    finally:
        conn.close()
    return rows

def update_question_status(qid: int, status: str, proxima_revisao_date: str | None = None):
    data_resp = today_date_str()
    if _using_supabase_api():
        sb = _get_supabase_client()
        sb.table("questoes").update({
            "status": status,
            "data_resposta": data_resp,
            "proxima_revisao": proxima_revisao_date,
        }).eq("id", qid).execute()
        return
    conn = connect()
    try:
        _exec(
            conn,
            """
            UPDATE questoes
            SET status=?, data_resposta=?, proxima_revisao=?
            WHERE id=?
            """,
            (status, data_resp, proxima_revisao_date, qid),
        )
        conn.commit()
    finally:
        conn.close()

_DISTINCT_WHITELIST = {"disciplina", "aula", "status", "origem_pdf", "tipo", "numero"}

def get_distinct(field: str):
    if field not in _DISTINCT_WHITELIST:
        raise ValueError("Campo não permitido para DISTINCT")
    if _using_supabase_api():
        sb = _get_supabase_client()
        res = sb.table("questoes").select(field).execute()
        vals = []
        for item in res.data or []:
            v = item.get(field)
            if v is not None and str(v).strip() != "":
                vals.append(v)
        return sorted(sorted(set(vals)))
    conn = connect()
    try:
        q = f"SELECT DISTINCT {field} FROM questoes WHERE {field} IS NOT NULL AND {field} != ''"
        cur = _exec(conn, q)
        rows = cur.fetchall()
    finally:
        conn.close()
    return sorted([r[0] for r in rows if r[0]])
