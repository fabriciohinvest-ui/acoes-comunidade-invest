# Projeto: páginas de ações, BDRs e FIIs da Comunidade Invest

Antes de qualquer coisa, leia `TUTORIAL-CLAUDE.md` inteiro: lá estão as regras, as fontes, as fórmulas conferidas com o Investidor10, as pegadinhas já resolvidas e o plano para escalar para todos os ativos.

Regras curtas:
- Conteúdo educativo: nunca recomendar compra ou venda de ativo.
- Nenhum dado pessoal do dono em User-Agent ou requisições.
- Se uma fonte falhar, manter o JSON de ontem do ativo; nunca inventar número (mostrar "-").
- `atualizar.py` só com a biblioteca padrão do Python.
- Testar `index.html` e `acao.html` servidos por `python -m http.server` (não abrir com duplo clique), em 1200 px e 390 px, sem erro no console.
- Como colocar no ar: `PASSO-A-PASSO.md`.
