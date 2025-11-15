# app.py - Caderno de Questões Inteligente (corrigido: navegação + responder desativado corretamente)
import streamlit as st
import json
from models import Questao
import re
from datetime import datetime, timedelta
import ast
import pandas as pd
import plotly.express as px
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

# session defaults
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "Quiz"  # default tab
if "quiz_idx" not in st.session_state:
    st.session_state.quiz_idx = 0
if "quiz_last_qid" not in st.session_state:
    st.session_state.quiz_last_qid = None
if "err_idx" not in st.session_state:
    st.session_state.err_idx = 0

# Top navigation — horizontal segmented control
nav_items = [
    ("📥", "Importar JSON"),
    ("🧠", "Quiz"),
    ("📕", "Caderno de Erros"),
    ("⏰", "Revisão"),
    ("🗃️", "Banco"),
    ("📈", "Desempenho"),
]
tab_names = [label for _, label in nav_items]
tab_labels = [f"{icon} {label}" for icon, label in nav_items]

# pequeno estilo para agrupar como "pills"
st.markdown(
    """
    <style>
    /* Container do grupo */
    div[role="radiogroup"]{
        gap:.4rem; padding:.25rem; background:#f3f4f6; border-radius:10px; flex-wrap:wrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

selected_label = st.radio(
    "Menu",
    tab_labels,
    index=tab_names.index(st.session_state.current_tab) if st.session_state.current_tab in tab_names else 1,
    horizontal=True,
    label_visibility="collapsed",
    key="top_menu",
)
st.session_state.current_tab = tab_names[tab_labels.index(selected_label)]
tab = st.session_state.current_tab

# -----------------------
# ABA: Importar (colar JSON)
# -----------------------
if tab == "Importar JSON":
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
elif tab == "Quiz":
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
        resp_btn = st.button("Responder", disabled=already_answered)

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
                        new_status = "acerto"
                        next_date = schedule_next_date(is_correct=True)
                else:
                    new_status = "erro"
                    next_date = schedule_next_date(is_correct=False)

                update_question_status(qid, new_status, next_date)

                if is_correct:
                    st.success("✅ Resposta correta!")
                else:
                    if resp_certa.upper() in ["A","B","C","D","E"]:
                        st.error(f"❌ Incorreta. Correta: {resp_certa.upper()}")
                    else:
                        correta_label = "Certo" if str(resp_certa).strip().lower() in ["certo","correta","c","true"] else "Errado"
                        st.error(f"❌ Incorreta. Correta: {correta_label}")
                if comentario:
                    with st.expander("💬 Comentário do professor"):
                        st.write(comentario)
                # manter na aba e permitir ver feedback antes de avançar
                st.session_state.current_tab = "Quiz"
                # NÃO chamamos st.rerun aqui para que o usuário veja o resultado;
                # o usuário pode clicar em "Próxima" para seguir.

        # Navigation
        col1, col2, col3 = st.columns([1,1,6])
        with col1:
            if st.button("⬅️ Anterior") and st.session_state.quiz_idx > 0:
                st.session_state.quiz_idx -= 1
                st.session_state.current_tab = "Quiz"
                st.rerun()
        with col2:
            if st.button("Próxima ➡️"):
                # recalc pendentes after possible status change
                new_pend = get_all_questions(filters=filters, status="nao_respondida")
                if not new_pend:
                    st.info("Não há mais questões pendentes neste filtro.")
                else:
                    st.session_state.quiz_idx = min(st.session_state.quiz_idx + 1, max(0, len(new_pend)-1))
                    st.session_state.current_tab = "Quiz"
                    st.rerun()

# -----------------------
# ABA: Caderno de Erros (1 por vez) — ajustado para alterar status
# -----------------------
elif tab == "Caderno de Erros":
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
        if st.session_state.get("show_erro_success"):
            st.success("✅ Acertou — removida do caderno de erros. Será revisada em 7 dias.")
            st.session_state.show_erro_success = False
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

        choice = st.radio("Escolha (treino rápido):", alternativas, key=choice_key)

        # responder in caderno: if acertar => vira 'acerto' + proxima 7d (sai do caderno)
        if st.button("Responder (caderno)"):
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
                    next_date = schedule_next_date(is_correct=True)
                    update_question_status(qid, new_status, next_date)
                    st.session_state.show_erro_success = True
                    st.session_state.current_tab = "Caderno de Erros"
                    st.rerun()
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
            if st.button("⬅️ Anterior (caderno)") and st.session_state.err_idx > 0:
                st.session_state.err_idx -= 1
                st.session_state.current_tab = "Caderno de Erros"
                st.rerun()
        with col2:
            if st.button("Próxima ➡️ (caderno)"):
                st.session_state.err_idx = min(st.session_state.err_idx + 1, max(0, len(erros)-1))
                st.session_state.current_tab = "Caderno de Erros"
                st.rerun()

# -----------------------
# ABA: Revisão
# -----------------------
elif tab == "Revisão":
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
    if not due:
        st.info("Nenhuma revisão pendente hoje nesse filtro.")
    else:
        row = due[0]
        qid = row[0]
        numero = row[1]
        enunciado = row[6]
        alternativas_text = row[7]
        resposta_correta = row[8]
        comentario = row[9]
        status = row[10]

        st.subheader(f"Aula: {row[4]} — {row[5]}")
        st.write(enunciado)
        alternativas = carregar_alternativas(alternativas_text) or ["Certo","Errado"]
        choice_key = f"rev_choice_{qid}"
        if st.session_state.get("rev_last_qid") != qid:
            st.session_state[choice_key] = None
            st.session_state.rev_last_qid = qid
        choice = st.radio("Escolha:", alternativas, key=choice_key)

        if st.button("Responder Revisão"):
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

                # Simplified transition: correct => revisado (no schedule), wrong => erro (+1d)
                new_status = "revisado" if is_correct else "erro"
                next_date = None if is_correct else schedule_next_date(is_correct=False)

                update_question_status(qid, new_status, next_date)
                if is_correct:
                    st.success("✅ Acertou na revisão!")
                else:
                    st.error("❌ Ainda incorreto.")
                if comentario:
                    with st.expander("💬 Comentário do professor"):
                        st.write(comentario)
                st.session_state.current_tab = "Revisão"
                st.rerun()

elif tab == "Banco":
    st.header("🔍 Banco de Questões — visão avançada")
    rows = get_all_questions()
    if not rows:
        st.info("Banco vazio.")
    else:
        # Base DataFrame completo
        df = pd.DataFrame(rows, columns=[
            "id","numero","tipo","disciplina","aula","origem_pdf","enunciado","alternativas","resposta_correta",
            "comentario","status","data_resposta","proxima_revisao"
        ])

        # ----------------------
        with st.expander("🎯 Filtros", expanded=True):
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            disciplinas_all = sorted(df["disciplina"].dropna().unique())
            selected_disc = col_f1.multiselect("Disciplina", disciplinas_all, default=[])
            aulas_all = sorted(df["aula"].dropna().unique())
            selected_aula = col_f2.multiselect("Aula", aulas_all, default=[])
            status_all = sorted(df["status"].dropna().unique())
            selected_status = col_f3.multiselect("Status", status_all, default=[])
            termo_busca = col_f4.text_input("Buscar texto (enunciado/comentário)")

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

        cols_base = ["id","disciplina","aula","status","data_resposta","proxima_revisao","dias_revisao","alternativas_preview"]
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

        st.dataframe(styled, width="stretch")

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
elif tab == "Desempenho":

    st.header("📈 Desempenho e Progresso")
    rows = get_all_questions()
    if not rows:
        st.info("Nenhum dado para mostrar.")
    else:
        df = pd.DataFrame(rows, columns=[
            "id","numero","tipo","disciplina","aula","origem_pdf","enunciado","alternativas","resposta_correta",
            "comentario","status","data_resposta","proxima_revisao"
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

        # Progresso percentual
        st.subheader("Progresso geral")
        pct = 100 * len(respondidas) / total if total else 0
        st.progress(pct/100, text=f"{pct:.1f}% das questões já respondidas.")

st.markdown("---")
st.caption("Protótipo corrigido — execute: streamlit run app.py")
try:
    st.caption(f"Banco de dados: {get_backend_label()}")
except Exception:
    pass
