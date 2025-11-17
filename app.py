# app.py - Caderno de Questões Inteligente
import streamlit as st
import json
from models import Questao
import re
from datetime import datetime, timedelta
import ast
import pandas as pd
import plotly.express as px
import math
from db import (
    create_table,
    insert_question,
    get_all_questions,
    today_date_str,
    schedule_next_date,
    get_due_for_review,
    update_question_status,
    get_distinct,
    get_backend_label,
    compute_next_interval_days,
    migrate_revisado_para_acerto,
    get_revisoes_feitas,
)

# -----------------------
# Utilidades
# -----------------------
def extrair_letra(alt_text):
    if not alt_text or not isinstance(alt_text, str):
        return None
    t = alt_text.strip()
    if len(t) > 0 and t[0].isalpha():
        ch = t[0].upper()
        if ch in "ABCDE":
            return ch
    m = re.search(r'([A-Ea-e])\s*[\)\.\-:]', t)
    if m:
        return m.group(1).upper()
    m2 = re.search(r'\b([A-Ea-e])\b', t)
    if m2:
        candidate = m2.group(1).upper()
        if candidate in "ABCDE":
            return candidate
    return None

def carregar_alternativas(alt_text):
    if not alt_text:
        return []
    try:
        if isinstance(alt_text, list):
            return alt_text
        return json.loads(alt_text)
    except Exception:
        try:
            return ast.literal_eval(alt_text)
        except Exception:
            return [alt_text]

# -----------------------
# UI Init
# -----------------------
st.set_page_config(page_title="Caderno de Questões Inteligente", layout="wide")
st.title("📘 Caderno de Questões Inteligente")
create_table()

# Migração automática de status 'revisado' legado para o novo modelo (acerto + revisões)
if "_migracao_revisado_done" not in st.session_state:
    try:
        migrados = migrate_revisado_para_acerto()
        if migrados:
            st.sidebar.success(f"Migração realizada: {migrados} questões 'revisado' convertidas para 'acerto'.")
    except Exception as ex:
        st.sidebar.warning(f"Falha na migração revisado->acerto: {ex}")
    st.session_state._migracao_revisado_done = True

# session defaults
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "Quiz"  # default tab
if "quiz_idx" not in st.session_state:
    st.session_state.quiz_idx = 0
if "quiz_last_qid" not in st.session_state:
    st.session_state.quiz_last_qid = None
if "err_idx" not in st.session_state:
    st.session_state.err_idx = 0

# Navegação principal — agora com st.tabs
nav_items = [
    ("📥", "Importar JSON"),
    ("🧠", "Quiz"),
    ("📕", "Caderno de Erros"),
    ("⏰", "Revisão"),
    ("🗃️", "Banco"),
    ("📈", "Desempenho"),
]
tab_labels = [f"{icon} {label}" for icon, label in nav_items]

# Estilos rápidos: botão primário mais visível e largura de conteúdo
st.markdown(
    """
    <style>
    .stButton>button {background:#2563eb;color:white;border:0;border-radius:8px;padding:0.55rem 0.9rem}
    .stButton>button:hover {background:#1d4ed8}
    .stDownloadButton>button {border-radius:8px}
    .main .block-container{max-width:1200px}
    </style>
    """,
    unsafe_allow_html=True,
)

# st.tabs retorna uma lista de objetos, cada um para uma aba
tab_objs = st.tabs(tab_labels)

# Mapeia o índice da aba ativa para o nome
tab_names = [label for _, label in nav_items]
tab_idx = 1  # default Quiz
if "current_tab" in st.session_state and st.session_state.current_tab in tab_names:
    tab_idx = tab_names.index(st.session_state.current_tab)
st.session_state.current_tab = tab_names[tab_idx]
tab = st.session_state.current_tab

# -----------------------
# ABA: Importar (colar JSON)
# -----------------------
with tab_objs[0]:
    st.header("📥 Cole o JSON de questões")
    st.write("Cole uma lista JSON de objetos. Exemplo: [ {\"numero\":\"1\",\"tipo\":\"multipla\", ...}, ... ]")
    json_input = st.text_area("Cole aqui o JSON", height=360)
    if st.button("Salvar no banco"):
        try:
            # Sanitização básica: remove BOM e espaços, limita tamanho
            sanitized = json_input.replace('\ufeff', '').strip()
            if len(sanitized) > 100_000:
                st.error("JSON muito grande. Limite 100.000 caracteres.")
                st.stop()
            # Tenta JSON canônico, com fallback seguro para literal de Python
            try:
                raw = json.loads(sanitized)
            except Exception:
                try:
                    raw = ast.literal_eval(sanitized)
                except Exception as ex:
                    st.error(f"Erro ao processar JSON: {ex}")
                    st.stop()
            if isinstance(raw, dict):
                raw = [raw]
            count = 0
            for q in raw:
                try:
                    questao = Questao.parse_obj(q)
                except Exception as ve:
                    st.error(f"Questão inválida: {ve}")
                    continue
                insert_question(questao.dict())
                count += 1
            if count:
                st.success(f"✅ {count} questões importadas.")
            else:
                st.warning("Nenhuma questão válida importada.")
        except Exception as e:
            st.error(f"Erro ao processar JSON: {e}")

# -----------------------
# ABA: Quiz
# -----------------------
with tab_objs[1]:
    st.header("🧠 Quiz — por disciplina / aula")
    # filters
    disciplinas = get_distinct("disciplina")
    disciplina = st.selectbox("Disciplina", ["Todas"] + disciplinas)
    aulas = ["Todas"]
    if disciplina and disciplina != "Todas":
        rows = get_all_questions(filters={"disciplina": disciplina})
        aulas_set = sorted({r[4] for r in rows if r[4]})
        aulas = ["Todas"] + aulas_set
    aula = st.selectbox("Aula (opcional)", aulas)

    filters = {}
    if disciplina and disciplina != "Todas":
        filters["disciplina"] = disciplina
    if aula and aula != "Todas":
        filters["aula"] = aula

    pendentes = get_all_questions(filters=filters, status="nao_respondida")
    total_pend = len(pendentes)
    st.write(f"Questões pendentes: **{total_pend}**")

    if total_pend == 0:
        st.info("Nenhuma questão pendente nesse filtro.")
    else:
        # clamp index
        st.session_state.quiz_idx = max(0, min(st.session_state.quiz_idx, total_pend - 1))
        row = pendentes[st.session_state.quiz_idx]
        qid = row[0]
        numero = row[1]
        tipo = row[2]
        disciplina_q = row[3]
        aula_q = row[4]
        origem = row[5]
        enunciado = row[6]
        alternativas_text = row[7]
        resposta_correta = row[8]
        comentario = row[9]
        status = row[10]

        st.subheader(f"Aula: {aula_q} — {origem}")
        st.write(enunciado)

        alternativas = carregar_alternativas(alternativas_text)
        if not alternativas:
            alternativas = ["Certo", "Errado"]

        already_answered = status != "nao_respondida"

        # clear leftover choice when question changes
        escolha_key = f"quiz_choice_{qid}"
        if st.session_state.get("quiz_last_qid") != qid:
            # clear previous choice for safety
            st.session_state[escolha_key] = None
            st.session_state.quiz_last_qid = qid

        # radio (disabled if already answered)
        choice = st.radio("Escolha uma alternativa:", alternativas, key=escolha_key, disabled=already_answered)
        doubt_key = f"quiz_doubt_{qid}"
        marked_doubt = st.checkbox("Marcar como dúvida", key=doubt_key, disabled=already_answered)

        # responder button (disabled if already answered)
        resp_btn = st.button("Responder", disabled=already_answered, key=f"quiz_responder_btn_{qid}")

        # process only if not already answered and button pressed
        if resp_btn and not already_answered:
            if choice is None or str(choice).strip() == "":
                st.warning("Selecione uma alternativa antes de responder.")
            else:
                resp_certa = (resposta_correta or "").strip()
                if resp_certa.upper() in ["A","B","C","D","E"]:
                    letra = extrair_letra(choice)
                    is_correct = (letra == resp_certa.upper())
                else:
                    correta_bool = str(resp_certa).strip().lower() in ["certo","correta","c","true"]
                    is_correct = str(choice).strip().lower().startswith("certo") == correta_bool

                if is_correct:
                    if marked_doubt:
                        new_status = "duvida"
                        next_date = schedule_next_date(is_correct=True, marked_doubt=True)
                    else:
                        # Inicia/continua SRS: próxima revisão com base nas revisões já feitas
                        new_status = "acerto"
                        revs = get_revisoes_feitas(qid)
                        dias = compute_next_interval_days(revs)
                        next_date = (datetime.now().date() + timedelta(days=dias)).isoformat()
                else:
                    new_status = "erro"
                    next_date = schedule_next_date(is_correct=False)

                # incrementa revisões apenas quando acerto sem dúvida
                if is_correct and not marked_doubt:
                    revs = get_revisoes_feitas(qid)
                    update_question_status(qid, new_status, next_date, revisoes_feitas=revs + 1)
                else:
                    update_question_status(qid, new_status, next_date)

                if is_correct:
                    if not marked_doubt:
                        st.success(f"✅ Resposta correta! Próxima revisão em {dias} dias.")
                    else:
                        st.success("✅ Resposta correta (marcada como dúvida) — revisa em 1 dia.")
                else:
                    if resp_certa.upper() in ["A","B","C","D","E"]:
                        st.error(f"❌ Incorreta. Correta: {resp_certa.upper()}")
                    else:
                        correta_label = "Certo" if str(resp_certa).strip().lower() in ["certo","correta","c","true"] else "Errado"
                        st.error(f"❌ Incorreta. Correta: {correta_label}")
                if comentario:
                    with st.expander("💬 Comentário do professor"):
                        st.write(comentario)

        # Navegação entre questões
        col1, col2 = st.columns([1,1])
        with col1:
            if st.button("⬅️ Anterior") and st.session_state.quiz_idx > 0:
                st.session_state.quiz_idx -= 1
                st.rerun()
        with col2:
            if st.button("Próxima ➡️"):
                # recalc pendentes after possible status change
                new_pend = get_all_questions(filters=filters, status="nao_respondida")
                if not new_pend:
                    st.info("Não há mais questões pendentes neste filtro.")
                else:
                    st.session_state.quiz_idx = min(st.session_state.quiz_idx + 1, max(0, len(new_pend)-1))
                    st.rerun()

# -----------------------
# ABA: Caderno de Erros (1 por vez) — ajustado para alterar status
# -----------------------
with tab_objs[2]:
    st.header("📕 Caderno de Erros")
    disciplinas = get_distinct("disciplina")
    disciplina = st.selectbox("Filtrar disciplina", ["Todas"] + disciplinas, key="err_disc")
    aulas = ["Todas"]
    if disciplina and disciplina != "Todas":
        rows = get_all_questions(filters={"disciplina": disciplina})
        aulas_set = sorted({r[4] for r in rows if r[4]})
        aulas = ["Todas"] + aulas_set
    aula = st.selectbox("Filtrar aula", aulas, key="err_aula")

    filters = {}
    if disciplina and disciplina != "Todas":
        filters["disciplina"] = disciplina
    if aula and aula != "Todas":
        filters["aula"] = aula

    erros = get_all_questions(filters=filters, status="erro")
    st.write(f"Total no caderno de erros: **{len(erros)}**")

    if not erros:
        st.info("Sem questões marcadas como erro nesse filtro.")
    else:
        st.session_state.err_idx = max(0, min(st.session_state.err_idx, len(erros)-1))
        row = erros[st.session_state.err_idx]
        qid = row[0]
        numero = row[1]
        disciplina_q = row[3]
        aula_q = row[4]
        origem = row[5]
        enunciado = row[6]
        alternativas_text = row[7]
        resposta_correta = row[8]
        comentario = row[9]

        st.subheader(f"Questão {numero} — {aula_q} — {origem}")
        st.write(enunciado)
        alternativas = carregar_alternativas(alternativas_text) or ["Certo","Errado"]

        # clear previous choice when qid changes
        choice_key = f"err_choice_{qid}"
        if st.session_state.get("err_last_qid") != qid:
            st.session_state[choice_key] = None
            st.session_state.err_last_qid = qid

        choice = st.radio("Escolha:", alternativas, key=choice_key)

        # responder in caderno: if acertar => vira 'acerto' + proxima 7d (sai do caderno)
        if st.button("Responder", key=f"err_responder_btn_{qid}"):
            if not choice:
                st.warning("Selecione uma alternativa antes de responder.")
            else:
                resp_certa = (resposta_correta or "").strip()
                if resp_certa.upper() in ["A","B","C","D","E"]:
                    letra = extrair_letra(choice)
                    is_correct = (letra == resp_certa.upper())
                else:
                    correta_bool = str(resp_certa).strip().lower() in ["certo","correta","c","true"]
                    is_correct = str(choice).strip().lower().startswith("certo") == correta_bool

                if is_correct:
                    new_status = "acerto"
                    revs = get_revisoes_feitas(qid)
                    dias = compute_next_interval_days(revs)
                    next_date = (datetime.now().date() + timedelta(days=dias)).isoformat()
                    update_question_status(qid, new_status, next_date, revisoes_feitas=revs + 1)
                    st.session_state.show_erro_success = True
                    st.success(f"✅ Acertou — removida do caderno de erros. Próxima revisão em {dias} dias.")
                else:
                    # permanece erro
                    new_status = "erro"
                    next_date = schedule_next_date(is_correct=False)
                    update_question_status(qid, new_status, next_date)
                    st.error("❌ Errado — permanece no caderno de erros para praticar de novo.")
                if comentario:
                    with st.expander("💬 Comentário do professor"):
                        st.write(comentario)

        col1, col2 = st.columns([1,1])
        with col1:
            if st.button("⬅️ Anterior", key=f"err_prev_btn_{st.session_state.err_idx}") and st.session_state.err_idx > 0:
                st.session_state.err_idx -= 1
                st.session_state.current_tab = "Caderno de Erros"
                st.rerun()
        with col2:
            if st.button("Próxima ➡️", key=f"err_next_btn_{st.session_state.err_idx}"):
                st.session_state.err_idx = min(st.session_state.err_idx + 1, max(0, len(erros)-1))
                st.rerun()

# -----------------------
# ABA: Revisão
# -----------------------
with tab_objs[3]:
    st.header("⏰ Revisão ")
    disciplines = get_distinct("disciplina")
    disciplina_filter = st.selectbox("Filtrar disciplina", ["Todas"] + disciplines, key="rev_disc")
    aulas = ["Todas"]
    if disciplina_filter and disciplina_filter != "Todas":
        rows = get_all_questions(filters={"disciplina": disciplina_filter})
        aulas_set = sorted({r[4] for r in rows if r[4]})
        aulas = ["Todas"] + aulas_set
    aula_filter = st.selectbox("Filtrar aula (opcional)", aulas, key="rev_aula")

    filters = {}
    if disciplina_filter and disciplina_filter != "Todas":
        filters["disciplina"] = disciplina_filter
    if aula_filter and aula_filter != "Todas":
        filters["aula"] = aula_filter

    due = get_due_for_review(filters=filters)
    st.write(f"Questões para revisão: **{len(due)}**")
    if "rev_idx" not in st.session_state:
        st.session_state.rev_idx = 0
    if not due:
        st.info("Nenhuma revisão pendente hoje nesse filtro.")
    else:
        # clamp index
        st.session_state.rev_idx = max(0, min(st.session_state.rev_idx, len(due)-1))
        row = due[st.session_state.rev_idx]
        qid = row[0]
        numero = row[1]
        enunciado = row[6]
        alternativas_text = row[7]
        resposta_correta = row[8]
        comentario = row[9]
        status = row[10]
        proxima_revisao = row[12]
        revisoes_feitas = row[13] if len(row) > 13 and row[13] is not None else 0

        st.subheader(f"Aula: {row[4]} — {row[5]}")
        st.write(enunciado)
        alternativas = carregar_alternativas(alternativas_text) or ["Certo","Errado"]
        choice_key = f"rev_choice_{qid}"
        if st.session_state.get("rev_last_qid") != qid:
            st.session_state[choice_key] = None
            st.session_state.rev_last_qid = qid
        choice = st.radio("Escolha:", alternativas, key=choice_key)

        if st.button("Responder", key=f"rev_responder_btn_{qid}"):
            if not choice:
                st.warning("Selecione uma alternativa antes de responder.")
            else:
                resp_certa = (resposta_correta or "").strip()
                if resp_certa.upper() in ["A","B","C","D","E"]:
                    letra = extrair_letra(choice)
                    is_correct = (letra == resp_certa.upper())
                else:
                    correta_bool = str(resp_certa).strip().lower() in ["certo","correta","c","true"]
                    is_correct = str(choice).strip().lower().startswith("certo") == correta_bool
                if is_correct:
                    # Mantém status 'acerto' e incrementa contador de revisões para espaçamento (1,7,15,15,...)
                    dias = compute_next_interval_days(revisoes_feitas)
                    novo_total_revisoes = revisoes_feitas + 1
                    next_date = (datetime.now().date() + timedelta(days=dias)).isoformat()
                    update_question_status(qid, "acerto", next_date, revisoes_feitas=novo_total_revisoes)
                    st.success(f"✅ Acertou! Próxima revisão em {dias} dias (revisões feitas: {novo_total_revisoes}).")
                else:
                    # Volta a ser erro (mantém revisões_feitas) com revisão curta (1 dia)
                    next_date = schedule_next_date(is_correct=False)
                    update_question_status(qid, "erro", next_date, revisoes_feitas=revisoes_feitas)
                    st.error("❌ Incorreto — retornou ao caderno de erros (1 dia).")
                if comentario:
                    with st.expander("💬 Comentário do professor"):
                        st.write(comentario)

        # Informações adicionais de repetição espaçada
        with st.expander("ℹ️ Info de repetição espaçada"):
            if status == "acerto":
                st.write(f"Revisões feitas: {revisoes_feitas}")
                if proxima_revisao:
                    st.write(f"Próxima revisão agendada para: {proxima_revisao}")
                else:
                    st.write("Sem próxima revisão agendada (configure ao responder corretamente).")
            else:
                st.write("Status atual não é 'acerto'; ao acertar aqui inicia/continua espaçamento.")

        # Navegação entre questões de revisão
        col1, col2 = st.columns([1,1])
        with col1:
            if st.button("⬅️ Anterior", key="rev_prev_btn") and st.session_state.rev_idx > 0:
                st.session_state.rev_idx -= 1
                st.rerun()
        with col2:
            if st.button("Próxima ➡️", key="rev_next_btn"):
                st.session_state.rev_idx = min(st.session_state.rev_idx + 1, max(0, len(due)-1))
                st.rerun()

# -----------------------
# ABA: Banco
# -----------------------
with tab_objs[4]:
    st.header("🔍 Banco de Questões — visão avançada")
    rows = get_all_questions()
    if not rows:
        st.info("Banco vazio.")
    else:
        # Estado inicial dos filtros (antes dos widgets)
        if "banco_disc" not in st.session_state:
            st.session_state.banco_disc = []
        if "banco_aula" not in st.session_state:
            st.session_state.banco_aula = []
        if "banco_status" not in st.session_state:
            st.session_state.banco_status = []
        if "banco_termo" not in st.session_state:
            st.session_state.banco_termo = ""
        if "banco_page" not in st.session_state:
            st.session_state.banco_page = 1
        # Base DataFrame completo
        df = pd.DataFrame(rows, columns=[
            "id","numero","tipo","disciplina","aula","origem_pdf","enunciado","alternativas","resposta_correta",
            "comentario","status","data_resposta","proxima_revisao","revisoes_feitas"
        ])

        # ----------------------
        with st.expander("🎯 Filtros", expanded=True):
            # Callback para limpar filtros sem st.rerun explícito
            def _clear_banco_filters():
                st.session_state.banco_disc = []
                st.session_state.banco_aula = []
                st.session_state.banco_status = []
                st.session_state.banco_termo = ""
                st.session_state.banco_page = 1

            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            disciplinas_all = sorted(df["disciplina"].dropna().unique())
            selected_disc = col_f1.multiselect("Disciplina", disciplinas_all, default=[], key="banco_disc")
            aulas_all = sorted(df["aula"].dropna().unique())
            selected_aula = col_f2.multiselect("Aula", aulas_all, default=[], key="banco_aula")
            status_all = sorted(df["status"].dropna().unique())
            selected_status = col_f3.multiselect("Status", status_all, default=[], key="banco_status")
            termo_busca = col_f4.text_input("Buscar texto (enunciado/comentário)", key="banco_termo")

            # Linha de chips + limpar
            col_cf1, col_cf2 = st.columns([3,1])
            with col_cf1:
                chips = []
                if selected_disc:
                    chips.append("Disciplinas: " + ", ".join(selected_disc))
                if selected_aula:
                    chips.append("Aulas: " + ", ".join(selected_aula))
                if selected_status:
                    chips.append("Status: " + ", ".join(selected_status))
                if termo_busca.strip():
                    chips.append(f"Busca: '{termo_busca.strip()}'")
                if chips:
                    st.caption("Filtros:")
                    st.write(" | ".join(chips))
            with col_cf2:
                st.button("Limpar filtros", on_click=_clear_banco_filters)

        mask = pd.Series([True]*len(df))
        if selected_disc:
            mask &= df["disciplina"].isin(selected_disc)
        if selected_aula:
            mask &= df["aula"].isin(selected_aula)
        if selected_status:
            mask &= df["status"].isin(selected_status)
        if termo_busca.strip():
            tb_raw = termo_busca.strip()
            # Normalização leve: lower + remoção de acentos
            def _norm_ser(s):
                return (
                    s.fillna("")
                     .astype(str)
                     .str.normalize("NFKD")
                     .str.encode("ascii", errors="ignore")
                     .str.decode("utf-8")
                     .str.lower()
                )

            tb = (
                pd.Series([tb_raw])
                .str.normalize("NFKD")
                .str.encode("ascii", errors="ignore")
                .str.decode("utf-8")
                .str.lower()
            ).iloc[0]

            search_blob = _norm_ser(df["enunciado"]) + " " + _norm_ser(df["comentario"]) 
            mask &= search_blob.str.contains(tb, na=False)

        # DataFrame filtrado e colunas derivadas
        df_view = df[mask].copy()

        # Pré-visualização das alternativas (primeiras até 3 opções)
        def alt_preview(x):
            try:
                if x:
                    lst = json.loads(x) if isinstance(x, str) else x
                    if isinstance(lst, list):
                        return " | ".join([str(s)[:70] for s in lst[:3]])
            except Exception:
                return str(x)[:70]
            return ""
        df_view["alternativas_preview"] = df_view["alternativas"].apply(alt_preview)

        # ----------------------
        hoje = today_date_str()
        def dias_para_revisao(date_str):
            if not date_str:
                return None
            try:
                dt = datetime.fromisoformat(date_str)
            except ValueError:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    return None
            return (dt.date() - datetime.now().date()).days
        df_view["dias_revisao"] = df_view["proxima_revisao"].apply(dias_para_revisao)
        df_view["revisao_vencida"] = df_view["dias_revisao"].apply(lambda d: d is not None and d <= 0)

        # ----------------------
        # Formatação / Cores por status
        # ----------------------
        status_style = {
            "acerto": "background-color:#d1fae5;color:#065f46;font-weight:600;",
            "erro": "background-color:#fee2e2;color:#991b1b;font-weight:600;",
            "duvida": "background-color:#fef3c7;color:#92400e;font-weight:600;",
            "revisado": "background-color:#e0e7ff;color:#3730a3;font-weight:600;",
            "nao_respondida": "background-color:#f3f4f6;color:#374151;"
        }

        def style_row(row):
            base = ""
            # Coluna pode já ter sido renomeada para "Status"
            st_key = row.get("status") or row.get("Status")
            if st_key in status_style:
                base += status_style[st_key]
            # Detectar revisão vencida: coluna original ou derivar de Dias p/ Revisão
            rev_vencida = row.get("revisao_vencida")
            if rev_vencida is None and ("Dias p/ Revisão" in row.index):
                d = row.get("Dias p/ Revisão")
                try:
                    if d not in (None, "-") and int(d) <= 0:
                        rev_vencida = True
                except Exception:
                    pass
            if rev_vencida:
                base += "border-left:4px solid #dc2626;"
            return [base]*len(row)

        mostrar_enunciado = st.toggle("Mostrar coluna de enunciado completa", value=False)
        mostrar_comentario = st.toggle("Mostrar comentários", value=False)

        cols_base = ["id","disciplina","aula","status","revisoes_feitas","data_resposta","proxima_revisao","dias_revisao","alternativas_preview"]
        if mostrar_enunciado:
            cols_base.insert(3, "enunciado")
        if mostrar_comentario:
            cols_base.append("comentario")

        df_display = df_view[cols_base]

        # Renomear colunas para ficar amigável
        rename_map = {
            "id": "ID",
            "disciplina": "Disciplina",
            "aula": "Aula",
            "status": "Status",
            "revisoes_feitas": "Revisões",
            "data_resposta": "Data Resposta",
            "proxima_revisao": "Próx. Revisão",
            "dias_revisao": "Dias p/ Revisão",
            "alternativas_preview": "Alternativas (preview)",
            "enunciado": "Enunciado",
            "comentario": "Comentário"
        }
        df_display = df_display.rename(columns=rename_map)

        st.subheader(f"Total filtrado: {len(df_display)} / {len(df)}")

        styled = df_display.style.apply(style_row, axis=1)
        # Formatação condicional nos dias para revisão
        if "Dias p/ Revisão" in df_display.columns:
            styled = styled.format({"Dias p/ Revisão": lambda v: "-" if v is None else v})

        # Paginação simples
        total_reg = len(df_display)
        colp1, colp2, colp3 = st.columns([2,1,1])
        with colp1:
            page_size = st.selectbox("Itens por página", [25, 50, 100], index=0)
        total_pages = max(1, math.ceil(total_reg / page_size))
        # Persistência da página
        if "banco_page" not in st.session_state:
            st.session_state.banco_page = 1
        with colp2:
            if st.button("◀️ Página anterior", disabled=st.session_state.banco_page <= 1):
                st.session_state.banco_page = max(1, st.session_state.banco_page - 1)
                st.rerun()
        with colp3:
            if st.button("Próxima página ▶️", disabled=st.session_state.banco_page >= total_pages):
                st.session_state.banco_page = min(total_pages, st.session_state.banco_page + 1)
                st.rerun()

        start = (st.session_state.banco_page - 1) * page_size
        end = start + page_size
        df_page = df_display.iloc[start:end]

        st.caption(f"Página {st.session_state.banco_page} de {total_pages} — exibindo {len(df_page)} de {total_reg}")
        st.dataframe(df_page.style.apply(style_row, axis=1), width="stretch")

        # ----------------------
        # Exportações
        # ----------------------
        st.markdown("### 📤 Exportar")
        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            payload_json = df_view.to_dict(orient="records")
            st.download_button(
                "JSON filtrado",
                json.dumps(payload_json, ensure_ascii=False, indent=2),
                file_name="questoes_filtradas.json",
                mime="application/json"
            )
        with col_e2:
            csv_data = df_view.to_csv(index=False)
            st.download_button(
                "CSV filtrado",
                csv_data,
                file_name="questoes_filtradas.csv",
                mime="text/csv"
            )
        with col_e3:
            # Excel em memória
            try:
                import io
                import openpyxl  # para garantir dependência
                buffer = io.BytesIO()
                df_view.to_excel(buffer, index=False)
                st.download_button(
                    "Excel filtrado",
                    buffer.getvalue(),
                    file_name="questoes_filtradas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as ex:
                st.warning(f"Excel indisponível: {ex}")

        st.caption("Linhas com borda vermelha: revisão vencida ou hoje.")


# -----------------------
# ABA: Desempenho (gráficos)
# -----------------------
# -----------------------
# ABA: Desempenho (gráficos)
# -----------------------
with tab_objs[5]:
    st.header("📈 Desempenho e Progresso")
    rows = get_all_questions()
    if not rows:
        st.info("Nenhum dado para mostrar.")
    else:
        df = pd.DataFrame(rows, columns=[
            "id","numero","tipo","disciplina","aula","origem_pdf","enunciado","alternativas","resposta_correta",
            "comentario","status","data_resposta","proxima_revisao","revisoes_feitas"
        ])

        # Filtros por período
        st.markdown("### Filtros de período")
        # Por padrão, mostrar os últimos 30 dias
        today = datetime.now().date()
        default_start = today - timedelta(days=30)
        default_end = today

        # Datas existentes no dataset (ainda úteis para validações ou futuras melhorias)
        min_date = pd.to_datetime(df["data_resposta"], errors="coerce").min()
        max_date = pd.to_datetime(df["data_resposta"], errors="coerce").max()

        colf1, colf2 = st.columns(2)
        with colf1:
            start_date = st.date_input(
                "Data inicial",
                value=default_start,
                max_value=today,
                key="perf_start_date",
            )
        with colf2:
            end_date = st.date_input(
                "Data final",
                value=default_end,
                max_value=today,
                key="perf_end_date",
            )

        # Validação amigável (sem mexer no session_state neste run)
        info_msgs = []
        if end_date and end_date > today:
            end_date = today
            info_msgs.append("Ajustei a data final para hoje.")
        if start_date and end_date and start_date > end_date:
            start_date = end_date
            info_msgs.append("Ajustei a data inicial para não ficar depois da final.")
        if info_msgs:
            st.warning(" ".join(info_msgs))

        # Filtro por disciplina
        st.markdown("### Filtro por disciplina")
        disciplinas_disp = sorted(df["disciplina"].dropna().unique())
        disciplina_sel = st.multiselect("Disciplina(s)", disciplinas_disp, default=disciplinas_disp)

        # Aplicar filtros
        # Para o total: só filtra por disciplina (não por período, pois questões não respondidas não têm data)
        df_total_filt = df.copy()
        if disciplina_sel:
            df_total_filt = df_total_filt[df_total_filt["disciplina"].isin(disciplina_sel)]
        
        # Para respondidas: filtra por disciplina E período
        df_respondidas_filt = df.copy()
        if start_date:
            df_respondidas_filt = df_respondidas_filt[pd.to_datetime(df_respondidas_filt["data_resposta"], errors="coerce") >= pd.to_datetime(start_date)]
        if end_date:
            df_respondidas_filt = df_respondidas_filt[pd.to_datetime(df_respondidas_filt["data_resposta"], errors="coerce") <= pd.to_datetime(end_date)]
        if disciplina_sel:
            df_respondidas_filt = df_respondidas_filt[df_respondidas_filt["disciplina"].isin(disciplina_sel)]

        # Filtro para respondidas (dentro do filtro de disciplina/período)
        respondidas = df_respondidas_filt[df_respondidas_filt["status"] != "nao_respondida"]
        acertos = respondidas[respondidas["status"] == "acerto"]
        erros = respondidas[respondidas["status"] == "erro"]
        duvidas = respondidas[respondidas["status"] == "duvida"]
        revisados = respondidas[respondidas["status"] == "revisado"]
        total = len(df_total_filt)  # todas as questões filtradas por disciplina (inclusive não respondidas)

        # Progresso percentual
        st.subheader("Progresso geral")
        pct = 100 * len(respondidas) / total if total else 0
        st.progress(pct/100, text=f"{pct:.1f}% das questões já respondidas.")
        
        # Métricas em colunas
        st.markdown("<style>.metric-card {background:#f3f4f6;border-radius:8px;padding:12px 0;margin:4px;text-align:center;box-shadow:0 1px 4px #0001;}</style>", unsafe_allow_html=True)
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.markdown(f'<div class="metric-card"><span style="font-size:2em">📚</span><br><b>Total</b><br>{total}</div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><span style="font-size:2em;color:#2563eb">📝</span><br><b>Respondidas</b><br>{len(respondidas)}</div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><span style="font-size:2em;color:#059669">✅</span><br><b>Acertos</b><br>{len(acertos)}</div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="metric-card"><span style="font-size:2em;color:#dc2626">❌</span><br><b>Erros</b><br>{len(erros)}</div>', unsafe_allow_html=True)
        with col5:
            st.markdown(f'<div class="metric-card"><span style="font-size:2em;color:#f59e42">❓</span><br><b>Dúvidas</b><br>{len(duvidas)}</div>', unsafe_allow_html=True)
        with col6:
            st.markdown(f'<div class="metric-card"><span style="font-size:2em;color:#6366f1">🔄</span><br><b>Revisadas</b><br>{len(revisados)}</div>', unsafe_allow_html=True)

        st.markdown("---")
        # Gráfico de status (Plotly para evitar avisos do Vega-Lite)
        st.subheader("Distribuição de Status")
        status_counts = respondidas["status"].astype(str).str.strip().value_counts()
        if not status_counts.empty:
            status_df = status_counts.reset_index()
            status_df.columns = ["status", "count"]
            status_df["status"] = status_df["status"].astype(str).str.strip()
            # cores fixas (erro vermelho, duvida azul claro) e ordem explícita
            status_color_map = {
                "acerto": "#2563eb",
                "erro": "#ef4444",
                "duvida": "#60a5fa",
                "revisado": "#6366f1",
            }
            status_order = [s for s in ["acerto","erro","duvida","revisado"] if s in status_df["status"].unique()]
            fig_status = px.bar(
                status_df,
                x="status",
                y="count",
                color="status",
                color_discrete_map=status_color_map,
                category_orders={"status": status_order},
                text="count",
                title=None,
            )
            fig_status.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            fig_status.update_traces(textposition="outside")
            st.plotly_chart(fig_status, width="stretch")
            st.caption("Acertos, erros, dúvidas e revisados entre as respondidas.")
        else:
            st.info("Sem dados de status para o filtro atual.")

        # Exportação dos dados do gráfico de status
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            st.download_button(
                "Exportar gráfico de status (CSV)",
                status_counts.to_csv(),
                file_name="grafico_status.csv",
                mime="text/csv"
            )
        with col_exp2:
            st.download_button(
                "Exportar gráfico de status (JSON)",
                status_counts.to_json(),
                file_name="grafico_status.json",
                mime="application/json"
            )

        # Evolução ao longo do tempo (Plotly)
        st.subheader("Evolução diária de respostas")
        df_resp = respondidas.copy()
        evol = pd.DataFrame()
        if not df_resp.empty:
            df_resp["data_resposta"] = pd.to_datetime(df_resp["data_resposta"], errors="coerce")
            df_resp = df_resp[pd.notnull(df_resp["data_resposta"])]
            if not df_resp.empty:
                df_resp["data_dia"] = df_resp["data_resposta"].dt.date
                evol_long = (
                    df_resp.groupby(["data_dia", "status"]).size().reset_index(name="count").sort_values("data_dia")
                )
                evol_long["status"] = evol_long["status"].astype(str).str.strip()
                evol_order = [s for s in ["acerto","erro","duvida","revisado"] if s in evol_long["status"].unique()]
                status_color_map = {
                    "acerto": "#2563eb",
                    "erro": "#ef4444",
                    "duvida": "#60a5fa",
                    "revisado": "#6366f1",
                }
                fig_evol = px.line(
                    evol_long,
                    x="data_dia",
                    y="count",
                    color="status",
                    color_discrete_map=status_color_map,
                    category_orders={"status": evol_order},
                    markers=True,
                    title=None,
                )
                fig_evol.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Data", yaxis_title="Quantidade")
                st.plotly_chart(fig_evol, width="stretch")
                evol = evol_long.pivot(index="data_dia", columns="status", values="count").fillna(0)
                st.caption("Veja como seu ritmo de estudo evolui por dia.")
            else:
                st.info("Sem datas válidas de resposta para plotar.")
        else:
            st.info("Sem evolução para exibir no período selecionado.")

        # Exportação dos dados do gráfico de evolução
        col_exp3, col_exp4 = st.columns(2)
        if not evol.empty:
            with col_exp3:
                st.download_button(
                    "Exportar evolução diária (CSV)",
                    evol.to_csv(),
                    file_name="grafico_evolucao.csv",
                    mime="text/csv"
                )
            with col_exp4:
                st.download_button(
                    "Exportar evolução diária (JSON)",
                    evol.to_json(),
                    file_name="grafico_evolucao.json",
                    mime="application/json"
                )
        else:
            with col_exp3:
                st.caption("Sem dados de evolução para exportar.")

        # Acertos por disciplina (Plotly)
        st.subheader("Acertos por disciplina")
        acertos_disc = acertos["disciplina"].value_counts()
        if not acertos_disc.empty:
            acertos_df = acertos_disc.reset_index()
            acertos_df.columns = ["disciplina", "count"]
            fig_ad = px.bar(acertos_df, x="disciplina", y="count", text="count", title=None)
            fig_ad.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            fig_ad.update_traces(textposition="outside")
            st.plotly_chart(fig_ad, width="stretch")
            st.caption("Disciplinas com mais acertos.")
        else:
            st.info("Sem acertos no filtro atual.")

        # Exportação dos dados de acertos por disciplina
        col_exp5, col_exp6 = st.columns(2)
        with col_exp5:
            st.download_button(
                "Exportar acertos por disciplina (CSV)",
                acertos_disc.to_csv(),
                file_name="grafico_acertos_disciplina.csv",
                mime="text/csv"
            )
        with col_exp6:
            st.download_button(
                "Exportar acertos por disciplina (JSON)",
                acertos_disc.to_json(),
                file_name="grafico_acertos_disciplina.json",
                mime="application/json"
            )

        # Erros por disciplina (Plotly)
        st.subheader("Erros por disciplina")
        erros_disc = erros["disciplina"].value_counts()
        if not erros_disc.empty:
            erros_df = erros_disc.reset_index()
            erros_df.columns = ["disciplina", "count"]
            fig_ed = px.bar(erros_df, x="disciplina", y="count", text="count", title=None)
            fig_ed.update_layout(margin=dict(l=10, r=10, t=10, b=10))
            fig_ed.update_traces(textposition="outside")
            st.plotly_chart(fig_ed, width="stretch")
            st.caption("Disciplinas que merecem revisão extra.")
        else:
            st.info("Sem erros no filtro atual.")

        # Exportação dos dados de erros por disciplina
        col_exp7, col_exp8 = st.columns(2)
        with col_exp7:
            st.download_button(
                "Exportar erros por disciplina (CSV)",
                erros_disc.to_csv(),
                file_name="grafico_erros_disciplina.csv",
                mime="text/csv"
            )
        with col_exp8:
            st.download_button(
                "Exportar erros por disciplina (JSON)",
                erros_disc.to_json(),
                file_name="grafico_erros_disciplina.json",
                mime="application/json"
            )

        # Distribuição de revisões espaçadas
        st.markdown("---")
        st.subheader("Distribuição de Revisões (Spaced Repetition)")
        acertos_rev = acertos.copy()
        if not acertos_rev.empty:
            acertos_rev["revisoes_feitas"] = acertos_rev["revisoes_feitas"].fillna(0).astype(int)
            dist_rev = acertos_rev["revisoes_feitas"].value_counts().sort_index()
            if not dist_rev.empty:
                df_rev = dist_rev.reset_index()
                df_rev.columns = ["Revisões", "Quantidade"]
                fig_rev = px.bar(df_rev, x="Revisões", y="Quantidade", text="Quantidade", title=None)
                fig_rev.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Número de revisões feitas", yaxis_title="Questões")
                fig_rev.update_traces(textposition="outside")
                st.plotly_chart(fig_rev, use_container_width=True)
                st.caption("Mostra quantas questões chegaram a cada nível de revisão.")
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    st.download_button("CSV revisões", dist_rev.to_csv(), file_name="distribuicao_revisoes.csv", mime="text/csv")
                with col_r2:
                    st.download_button("JSON revisões", dist_rev.to_json(), file_name="distribuicao_revisoes.json", mime="application/json")
            else:
                st.info("Ainda sem revisões registrada.")
        else:
            st.info("Nenhum 'acerto' para calcular distribuição de revisões.")

        # Média de revisões por disciplina (considerando apenas acertos)
        st.markdown("---")
        st.subheader("Média de Revisões por Disciplina")
        if not acertos_rev.empty:
            grp = acertos_rev.copy()
            grp["revisoes_feitas"] = grp["revisoes_feitas"].fillna(0).astype(int)
            media_rev = grp.groupby("disciplina")["revisoes_feitas"].mean().sort_values(ascending=False)
            if not media_rev.empty:
                df_media = media_rev.reset_index()
                df_media.columns = ["Disciplina", "Média de Revisões"]
                # Arredondar para uma casa para exibir
                df_media["Média de Revisões"] = df_media["Média de Revisões"].round(1)
                fig_media = px.bar(df_media, x="Disciplina", y="Média de Revisões", text="Média de Revisões", title=None)
                fig_media.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_title="Disciplina", yaxis_title="Média de revisões por questão (acertos)")
                fig_media.update_traces(textposition="outside")
                st.plotly_chart(fig_media, use_container_width=True)
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.download_button("CSV média por disciplina", df_media.to_csv(index=False), file_name="media_revisoes_por_disciplina.csv", mime="text/csv")
                with col_m2:
                    st.download_button("JSON média por disciplina", df_media.to_json(orient="records"), file_name="media_revisoes_por_disciplina.json", mime="application/json")
            else:
                st.info("Sem dados de média por disciplina no filtro atual.")
                
                
        else:
            st.info("Nenhum 'acerto' para calcular média por disciplina.")

st.markdown("---")
st.caption("Protótipo corrigido — execute: streamlit run app.py")
try:
    st.caption(f"Banco de dados: {get_backend_label()}")
except Exception:
    pass
