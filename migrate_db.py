#!/usr/bin/env python3
import argparse
import sqlite3
from contextlib import closing

DEFAULT_DB = "questoes.db"

STATUS_MAP = {
    "acertada": "acerto",
    "acerto": "acerto",
    "ok": "acerto",
    "correto": "acerto",
    "correta": "acerto",
    "errada": "erro",
    "erro": "erro",
    "incorreto": "erro",
    "incorreta": "erro",
}

ADD_COLUMNS = [
    ("numero", "TEXT"),
    ("tipo", "TEXT"),
]

INDEXES = [
    ("idx_questoes_status", "CREATE INDEX IF NOT EXISTS idx_questoes_status ON questoes(status)"),
    ("idx_questoes_proxrev", "CREATE INDEX IF NOT EXISTS idx_questoes_proxrev ON questoes(proxima_revisao)"),
    ("idx_questoes_disciplina", "CREATE INDEX IF NOT EXISTS idx_questoes_disciplina ON questoes(disciplina)"),
    ("idx_questoes_aula", "CREATE INDEX IF NOT EXISTS idx_questoes_aula ON questoes(aula)"),
]

def connect(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    with conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    with closing(conn.cursor()) as c:
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return c.fetchone() is not None


def get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    with closing(conn.cursor()) as c:
        c.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in c.fetchall()}  # row[1] = name


def add_missing_columns(conn: sqlite3.Connection, table: str, add_cols: list[tuple[str, str]]) -> list[str]:
    existing = get_columns(conn, table)
    added = []
    for col, coltype in add_cols:
        if col not in existing:
            with conn:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
            added.append(col)
    return added


def normalize_status(conn: sqlite3.Connection) -> int:
    changed = 0
    with closing(conn.cursor()) as c:
        for src, dst in STATUS_MAP.items():
            c.execute("UPDATE questoes SET status=? WHERE lower(trim(status))=?", (dst, src))
            changed += c.rowcount or 0
        # Fill empty/NULL statuses
        c.execute("UPDATE questoes SET status='nao_respondida' WHERE status IS NULL OR trim(status)='' ")
        changed += c.rowcount or 0
    conn.commit()
    return changed


def normalize_dates(conn: sqlite3.Connection) -> tuple[int, int]:
    with closing(conn.cursor()) as c:
        c.execute(
            """
            UPDATE questoes
            SET data_resposta = substr(data_resposta,1,10)
            WHERE data_resposta IS NOT NULL AND length(data_resposta) > 10
            """
        )
        changed_dr = c.rowcount or 0
        c.execute(
            """
            UPDATE questoes
            SET proxima_revisao = substr(proxima_revisao,1,10)
            WHERE proxima_revisao IS NOT NULL AND length(proxima_revisao) > 10
            """
        )
        changed_pr = c.rowcount or 0
    conn.commit()
    return changed_dr, changed_pr


def create_indexes(conn: sqlite3.Connection) -> None:
    with conn:
        for name, ddl in INDEXES:
            conn.execute(ddl)


def migrate(db_path: str) -> None:
    conn = connect(db_path)
    try:
        if not table_exists(conn, "questoes"):
            print("Tabela 'questoes' não encontrada. Nada a migrar.")
            return
        # Columns
        added = add_missing_columns(conn, "questoes", ADD_COLUMNS)
        if added:
            print(f"Colunas adicionadas: {', '.join(added)}")
        else:
            print("Nenhuma coluna nova necessária.")
        # Status
        st_changed = normalize_status(conn)
        print(f"Status normalizados/ajustados: {st_changed}")
        # Dates
        dr_changed, pr_changed = normalize_dates(conn)
        print(f"Datas normalizadas: data_resposta={dr_changed}, proxima_revisao={pr_changed}")
        # Indexes
        create_indexes(conn)
        print("Índices garantidos.")
        print("Migração concluída com sucesso.")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrar questoes.db para o esquema unificado do app.")
    parser.add_argument("--db", dest="db_path", default=DEFAULT_DB, help="Caminho para o arquivo SQLite (padrão: questoes.db)")
    args = parser.parse_args()
    migrate(args.db_path)


if __name__ == "__main__":
    main()
