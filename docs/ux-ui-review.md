# Caderno de Questões Inteligente — Avaliação de UX/UI

Data: 2025-11-15

## Nota Geral
- **7/10** — Interface limpa e funcional, porém com hierarquia visual fraca, navegação pelo topo confusa (radios como menu), densidade alta nas tabelas e CTAs pouco destacadas. Painéis e filtros são úteis, mas faltam polimento de usabilidade, responsividade e acessibilidade.

## Pontos Fortes
- **Clareza de fluxo:** páginas têm propósitos claros (Quiz, Caderno de Erros, Revisão, Banco, Desempenho).
- **Métricas úteis:** acertos/erros, próximas revisões, evolução diária.
- **Filtros eficientes:** disciplina, aula, status e busca por texto ajudam muito.
- **Exportação pronta:** CSV/JSON já integrado.

## Ganhos Rápidos (1–2 dias)
- **Navegação:** trocar radios do topo por `st.tabs` ou `st.sidebar` fixa com aba ativa destacada.
- **CTA primária:** cor única consistente (ex.: azul) para “Responder/Salvar”; botão primário sempre visível (sticky) ao final do enunciado.
- **Hierarquia:** limitar largura do conteúdo (~70–80 caracteres por linha), aumentar espaçamentos entre blocos e padronizar títulos/subtítulos.
- **Enunciados longos:** usar `st.expander` para corpo completo e mostrar preview curto por padrão.
- **Alternativas:** numerar (1–5), permitir atalhos de teclado 1–5, realçar a escolhida e mostrar feedback imediato.
- **Filtros visuais:** chips das seleções + botão “Limpar filtros”; encapsular filtros em `st.form` com botão “Aplicar”.
- **Tabelas (Banco):** truncar colunas extensas com tooltip, congelar ID/Disciplina, paginação 25/50, ordenação por cabeçalho.
- **Estados vazios:** mensagens úteis quando “0 revisões” com CTA (ex.: “Ir para Quiz” ou “Carregar questões”).
- **Acessibilidade:** contraste adequado para verde/vermelho, ícones + texto para status, foco de teclado visível.

## Melhorias de Médio Prazo
- **Consistência visual:** definir tokens de design (cores, espaçamentos, bordas, radius) e aplicar em todos os componentes.
- **Feedback/carregamento:** `st.toast`/`st.success` para ações; skeleton loaders para tabelas e cards.
- **Revisão/SRS:** destacar “Itens devidos hoje”, filtro “Somente devidos” e contagem por disciplina.
- **Desempenho:** `st.cache_data` para consultas; paginação server‑side no Banco; lazy‑load de colunas pesadas.
- **Mobile:** pontos de quebra para empilhar colunas; botões maiores; navegação inferior em telas pequenas.
- **Tema:** modo claro/escuro com persistência em `st.session_state`.
- **Telemetria:** instrumentar cliques principais (Responder/Próxima), tempo por questão e taxa de abandono.

## Aprimoramentos Específicos (Streamlit)
- **Tabs/Sidebar:** `st.tabs(["Quiz","Erros","Revisão","Banco","Desempenho"])` ou `st.sidebar.radio(...)` para navegação.
- **Tabelas:** `st.dataframe(..., use_container_width=True, column_config=...)` com formatação condicional de status.
- **Edição/Review:** `st.data_editor` para correções rápidas; `st.download_button` para exportações.
- **Persistência:** `st.session_state` para filtros/última aba; `st.cache_data` para listas estáticas (disciplinas/aulas).

## Próximos Passos Sugeridos
1. Prototipar no Figma a nova navegação e hierarquia.
2. Implementar “quick wins”: tabs/side bar, CTA sticky, melhorias nas tabelas do Banco.
3. Teste com 5 usuários: medir tempo para filtrar e responder 5 questões.
4. Iterar com base nos resultados e instrumentação.

## Checklist de Implementação Rápida
- [ ] Migrar navegação para `st.tabs`/sidebar.
- [ ] Tornar “Responder/Salvar” um botão primário sticky.
- [ ] Numerar alternativas e ativar atalhos 1–5.
- [ ] Compactar enunciados longos com `st.expander`.
- [ ] Tabelas com truncamento + tooltip, ordenação e paginação.
- [ ] Chips de filtros + botão “Limpar filtros”.
- [ ] Estados vazios com CTA adequado.
- [ ] Ajustes de contraste e foco para acessibilidade.

---
Documento preparado para acompanhamento e iteração contínua do design e da usabilidade do projeto. 