# Tutorial para o Claude: páginas de ações, BDRs e FIIs da Comunidade Invest

Este arquivo é para o Claude que vai continuar este projeto. Leia inteiro antes de mexer em qualquer coisa. Ele resume tudo o que foi decidido e descoberto com o Fabricio (dono da Comunidade Invest) até aqui.

---

## 1. O que é e em que pé está

Um site de páginas de ativos no estilo do Investidor10. As regras são três:

- **Só dados públicos e gratuitos.**
- **Atualização sozinha todo dia útil.**
- **Números o mais fiéis possível** ao que o Investidor10 mostra.

**Hoje (versão 1)** o site tem 3 ativos, um de cada tipo, que servem de modelo:

| Ticker | Tipo no código | O que testa |
|---|---|---|
| BBAS3 (Banco do Brasil) | `acao` com `'banco': True` | Ação brasileira; balanço de banco, que é diferente |
| GOGL34 (Alphabet/Google) | `bdr` | BDR: balanço em dólar da SEC, cotação dos EUA, dividendos convertidos |
| MXRF11 (Maxi Renda) | `fii` | Fundo imobiliário: rendimentos, P/VP, rentabilidade × CDI/IPCA, carteira |

A **página de pesquisa** (`index.html`) já está pronta para centenas ou milhares de ativos: busca, filtros por tipo e setor, ordenação e paginação de 50 em 50. Ela lê só o `dados/indice.json`.

**Próxima etapa (seu trabalho):** cobrir **todas as ações e FIIs da B3**, **todas as ações americanas que têm BDR na B3** e as do **S&P 500**. Essa lista dos EUA foi escolha do Fabricio porque é grátis via SEC + Yahoo. Tudo continua se atualizando sozinho todo dia, rápido. O plano está na seção 9.

Colocar no ar: ver `PASSO-A-PASSO.md` (GitHub + Netlify). O site principal da Comunidade fica na Netlify. O sócio do Fabricio integra estas páginas ao site depois.

### Estado em 08/11/2026: escala feita (versão 2)

O plano da seção 9 foi feito para ações, FIIs e BDRs. Falta o tipo `eua` (S&P 500 sem BDR).

- **`universo.py`** monta `cache/universo.json` uma vez por semana (detalhes no `LEIA-ME.md`, "Quais ativos entram"):
  - ações negociadas no último mês, com CNPJ e nome de pregão da lista `GetInitialCompanies` da B3, nome com acento do cadastro da CVM e setor/segmento do `GetDetail`;
  - FIIs pelo ISIN do informe mensal da CVM;
  - BDRs de empresa pelo `GetCompaniesBDR` (categoria 6) e pela lista de tickers da SEC, só os que entregam 10-K/10-Q.
- **`atualizar.py`** lê essa lista, e a `EMPRESAS` vale por cima:
  - Cotações numa passada para todos (`atualizar_cotacoes_todas`), com o arquivo anual lido linha a linha.
  - DFP/ITR, FRE, informe de FII e IPE baixados uma vez e separados por CNPJ.
  - Respostas da B3, da SEC, do Yahoo e do Fundos.NET guardadas por idade em `cache/rede/` (`em_cache`).
  - Balanço da SEC recalculado só com 10-K/10-Q novo (`fin_eua_guardado`).
  - 8 ativos ao mesmo tempo (`ThreadPoolExecutor`).
- **Balanço individual**: empresa que não entrega o consolidado num ano usa o individual (`_ind` em `cache/cvm/`), o que resolve o caso do ABCB4.
- **Workflow**: `actions/cache` para `cache/` e `dados/`; o site vai para o GitHub Pages pelo próprio workflow (`deploy-pages`).
  - Exige Settings → Pages → Source: GitHub Actions, que só o dono pode trocar.
  - No modo antigo do Pages, o workflow salva no git só os ativos da `EMPRESAS`.
- **A cotação não foi enxugada** (item 9.3). Medido em 08/11/2026: média de 250 KB por ação, 170 KB por FII e 160 KB por BDR. Com uns 1.260 ativos, o site no Pages fica perto de 240 MB, abaixo do limite de 1 GB, e o `acao.html` não precisou mudar.
- **Balanço americano (`fin_eua`) corrigido para qualquer empresa**:
  - **Ano fiscal fora de dezembro** (Apple em setembro, Microsoft em junho, Nvidia em janeiro). Antes, o `balanco_ref` saía "31/12" do ano fiscal (uma data no futuro) e o TTM ficava parado no último 10-K. Agora o ytd conta do início do ano fiscal, o TTM entra com o último 10-Q e o 4º trimestre é o ano fiscal menos os 9 meses. Preço e dividendos do histórico anual também usam o fechamento do ano fiscal.
  - **Cada item vem do campo XBRL mais atualizado da empresa.** Os outros campos só completam datas que faltam. Exemplos: bancos (JPMorgan & cia.) informam a receita em `RevenuesNetOfInterestExpense` desde 2015, e a Broadcom informa o lucro em `ProfitLoss` desde 2025.
  - **Proteções para banco**, que não tem lucro operacional (o EBITDA fica "-"), e para ano sem lucro informado.
  - Em empresas de ano fiscal em dezembro, os números não mudaram (Google, Amazon, Meta e Tesla foram comparados antes e depois).
  - O resultado guardado tem versão no nome (`fin_{cik}_{data}_v5.json`). Se mudar o cálculo de novo, suba a versão para refazer os guardados.
- **Correções da 1ª rodada no GitHub (08/11/2026)**: saíram 1.217 de 1.259 ativos. Os 42 que deram erro foram corrigidos assim:
  - **Ano fiscal fora de dezembro na CVM** (São Martinho, Raízen e Jalles em março, Camil em fevereiro, BrasilAgro em junho): o mês de fechamento sai dos DFP da empresa (`mes_fy` em `fin_brasil`). O ano leva o número do ano em que fecha. TTM, 4º trimestre, preço e proventos do histórico usam o fechamento real. O DFP do ano corrente também é baixado, porque traz quem fecha antes de dezembro.
  - **Mais campos de receita na SEC**:
    - `RevenueFromContractWithCustomerIncludingAssessedTax` (CrowdStrike, Hormel, Kraft Heinz, Valero);
    - os de antes de 2018, que só completam anos que faltam (`SalesRevenueNet`, `RealEstateRevenueNet`). Não use `SalesRevenueGoodsNet`/`ServicesNet`: são partes da receita, não o total.
  - **Receita parcial**: às vezes o campo principal traz só uma parte da receita (P&G 2012-2014 em `Revenues`; REITs, seguradoras e bancos em `RevenueFromContractWithCustomerExcludingAssessedTax`, que deixa de fora aluguel, prêmio e juros). Se outro campo de receita tem o dobro ou mais na mesma data, vale o outro (`parte` em `serie`). Exceções:
    - banco com `RevenuesNetOfInterestExpense` (a receita líquida é menor que a bruta, e é a líquida que queremos);
    - a receita com impostos sobre venda, que nunca substitui a líquida (na Philip Morris ela é 2,5 vezes maior).
  - **Antes dessas correções, uns 40 BDRs publicados tinham o balanço parado em anos antigos** (NextEra e Duke em 2013, Halliburton em 2011, TJX em 2015), porque a empresa tinha trocado o campo da receita. A comparação com o publicado está em "Testes".
  - **Empresa americana sem receita na SEC** (sem vendas ainda, como QuantumScape e Biohaven, ou banco regional que não informa receita): os anos fiscais saem do lucro e a receita fica "-". Não usamos receita de juros bruta no lugar, para não misturar critérios.
  - **Sem nº de ações na SEC** (mais de uma classe: Berkshire, Visa...): os indicadores por ação do histórico ficam "-" em vez de quebrar.
  - **Holding nova com CIK novo** (ExxonMobil Holdings, 2026): `CIK_ANTERIOR` junta o histórico do cadastro antigo.
  - **Nome do BDR**: a ligação com a SEC também aceita as mesmas palavras em outra ordem ("T ROWE PRICE" × "PRICE T ROWE") e não liga empresa a fundo/ETF de nome parecido. Com isso, a Charles Schwab entrou.
  - **FII que a B3 não detalha** (JPPA11, APXM11): fica sem eventos da B3, e os rendimentos vêm pelo Yahoo.
  - **Ficam de fora até entregar o 1º 10-K**: SpaceX e Cerebras, que só têm 10-Q.
  - **Lista refeita quando a regra muda**: `universo.json` guarda `versao`. Se mudar a regra da lista, suba `VERSAO` no `universo.py`, e a próxima rodada refaz a lista sem esperar a semana.
  - **CNPJ de filial**: quando a B3 traz o CNPJ de uma filial (Tupy), a lista usa o da matriz no cadastro da CVM, desde que só exista uma companhia com aquela raiz.
- **Log**: com 8 ativos ao mesmo tempo, cada linha sai inteira e, durante um ativo, com `[TICKER]` na frente.
- **BDRs de empresas estrangeiras (20-F) e ETFs (08/11/2026, à noite)**:
  - **20-F** (`estrangeira: true` no `universo.json`, `fin_estrangeira`): a SEC só tem o anual, com atraso. O balanço vem do Yahoo (`fundamentals-timeseries`, sem login): uns 4 anos e 5 trimestres, na moeda da empresa.
    - **Câmbio:** tudo é convertido para dólar pelo câmbio do fim de cada período (`{MOEDA}USD=X` no Yahoo).
    - **TTM:** a soma dos 4 últimos trimestres. Sem trimestres, fica o último ano, e o JSON leva `aviso`, que a página mostra no topo.
    - **Ações por ADR:** o nº de ações é contado em ADRs, porque a cotação usada é a do ADR. A proporção sai do P/L do Yahoo (preço do ADR ÷ lucro por ADR) e encaixa numa lista de proporções comuns: TSMC 5, Alibaba e Baidu 8. Pelo valor de mercado não dá certo, porque o Yahoo calcula com a ação de casa e o ADR da TSMC tem uns 15% de ágio. Com prejuízo, usa o valor de mercado.
  - **ETFs** (`tipo: etf`, `montar_etf`, `renderEtf` no `acao.html`): CODBDI 14. Nome pelo Yahoo (`nome_etf` limpa o nome longo), segmento pelo nome (`ETF_TIPOS`), administrador, proventos e desdobramentos pelo `GetListedSupplementFunds` da B3 (typeFund 20).
  - **Carteira dos ETFs** (`cda_etfs`, `carteira_etf`): o CDA mensal da CVM (`cda_fi_AAAAMM.zip`, arquivo `cda_fie_AAAAMM.csv`, linhas `CLASSES FIIM`). Vale o mês mais recente com pelo menos 50 fundos; o do mês corrente sai incompleto.
    - **Ligação com o fundo:** o ETF é ligado ao fundo pelo nome. `palavras_fundo` tira acento e as palavras genéricas ("fundo de índice", "responsabilidade limitada", "resp") e compara o resto.
    - **Porcentagens:** % sobre `VL_PATRIM_LIQ`. Ações emprestadas são somadas à posição. Disponibilidades e valores a receber ou a pagar vão para "caixa e outros".
    - **Ativo de fora sem nome** (emissor 9000132): vale o código do ativo (QQQ, IAU).
    - **Sigilo:** quem está só no `cda_fie_CONFID` sai com `sigilo: true`.
    - **Na página:** `carteiraHTML`, com 10 linhas e "Ver mais" (classe `l10`). Quando um fundo tem mais de 90% da carteira (IVVB11 → iShares Core S&P 500), a nota avisa que o ETF investe por meio de outro fundo.
  - **Fundos de infraestrutura** listados (CODBDI 14 também) ficam com o segmento "Fundo de infraestrutura" e o texto próprio na página.
  - **Lista:** `VERSAO = 5` no `universo.py`, para refazer a lista na hora.
- **Ficaram de fora**:
  - units;
  - FIIs sem ISIN no informe da CVM (uns 15%);
  - BDRs de empresas que não entregam balanço à SEC (SK Hynix);
  - o tipo `eua`.
- **Limite da fonte**: algumas empresas americanas aparecem com o balanço atrasado porque a própria base da SEC (`companyfacts`) ainda não trouxe os 10-Q mais novos. Em 08/11/2026, o Citi estava em dez/2025 e a Southern em mar/2026. O robô usa o mais recente que existe; não é erro do código.
- **Testes de 08/11/2026** (no computador, com `--so`): 22 ativos variados, 20 BDRs de anos fiscais e bancos diferentes e 90 sorteados (30 ações, 30 FIIs e 30 BDRs, de muito a pouco negociados). Todos saíram sem erro. Com os 88 ativos novos, o histórico desde 2009 levou uns 3 minutos e o pico de memória ficou em 1,2 GB.

## 2. Regras que não podem ser quebradas

1. **Conteúdo educativo.** Nunca escreva recomendação de compra ou venda, "melhores ações", nota ou ranking de "qual comprar". Ordenar uma tabela por um indicador é aceito; dizer que algo "está barato" não é.
2. **Nada de dado pessoal do Fabricio** (e-mail, nome) em User-Agent, URL ou cabeçalho de requisição. O User-Agent padrão é `ComunidadeInvest dados-publicos`. A SEC pede um contato no User-Agent: use um e-mail de contato **do site** que o Fabricio ou o sócio informarem. Não invente um.
3. **Falha não apaga dado.** Se uma fonte cair, o robô mantém o JSON de ontem daquele ativo e segue com os outros. Ele só sai com erro se todos falharem. Mantenha isso no código em escala.
4. **Nunca invente número.** Se não há dado confiável, mostre "-" e explique no rodapé ou no ⓘ. Exemplos: rendimentos de FII antes de 2022 e vacância.
5. **Sem dependências.** O `atualizar.py` usa só a biblioteca padrão do Python (3.9+). Se precisar de algo novo, prefira manter assim (o workflow não roda `pip install`).
6. Linguagem das páginas: português simples, para quem está começando.

## 3. O que o Fabricio pediu no layout (já está feito, mantenha)

- **Cotação no topo**: gráfico de cotação logo depois do cabeçalho.
- **Medir no gráfico da cotação**: clicar (ou tocar) num ponto e arrastar para o lado mostra "De X a Y: ±Z% (R$ a → R$ b)", só preço, sem proventos. É a opção `medir:true` da função `chart()` (retângulo `#msel` + `<div class="med">`, `touch-action:pan-y` para não travar a rolagem no celular). Usa a primeira série do gráfico.
- **Análise técnica** (logo abaixo da cotação): a cotação abre lisa e, embaixo, um bloco recolhido com o título grande "Análise técnica" e "Ver mais" (`#tecTg`, estado `st.tecAb`, começa fechado). Aberto, mostra de padrão os 3 gráficos de baixo (Volume, RSI 14 com linhas 70/30, MACD 12/26/9 com histograma) e **nenhuma** linha no preço; a pessoa liga Média 20/50/100/200 e Máx./mín. de 52 semanas (a Bollinger foi tirada a pedido do Fabricio) pelos botões (`st.tec`, um `Set`). Os indicadores saem de `tecCalc()` (guardado em `_tec`), calculados no histórico inteiro de fechamento e depois cortados no período escolhido, para a média de 200 já começar certa. Volume vem de `cotacao[i][5]`. Textos ⓘ em `EXP` (`t_mm`, `t_m`, `t_vol`, `t_rsi`, `t_macd`). A nota avisa que não é recomendação.
  - **RSI de 7, 14 ou 21 dias** (08/11/2026): com o RSI ligado, aparecem os botões de período ao lado dele (`RSI_P`, `st.rsi`, padrão 14). `tecCalc()` calcula os três (`T.rsiN`).
- Opções da `chart()` além das antigas: `passo` (de quantos em quantos rótulos no eixo X), `fixo:[min,max]` (eixo Y fixo, usado no RSI) e `medir`.
- **Informações sobre a empresa (ou o fundo) logo depois da cotação e da análise técnica** (pedido do Fabricio), com ⓘ em cada informação (textos no dicionário `EXPI`, chave = o nome que aparece no cartão; no `data-aj` vai com o prefixo `i:`). Informação nova precisa de texto lá.
- **Só para assinantes** (pedido do Fabricio): *Termômetro*, *Quanto tempo segurar*, *Lado a lado com o setor* e *Quem são os donos e o número de ações* (FII: *Quem são os cotistas*; BDR: *Número de ações*). Ficam juntas no fim, depois do divisor "Para assinantes" (item "Assinantes" no menu), e logo depois vêm os comunicados e relatórios, que são grátis. A página lê `window.CI_ASSINANTE` (`false` = cadeado com botão para `window.CI_LINK_ASSINAR`; sem definir = tudo aparece) e a lista fica em `SO_ASSINANTE` no `acao.html`. Como ligar no login do site e o limite de esconder só na tela: `CLAUDE.md` do pacote do sócio, seção "Seções para assinantes".
  - Na trava, depois da descrição, vem a frase "Indicador muito importante para você decidir a compra." (pedido do Hallan, 08/11/2026).
- Depois, **os dados escritos**, cada seção com uma **prévia** e o botão **"Ver mais"**. As seções são: indicadores fundamentalistas, histórico de indicadores, histórico de dividendos, resultados e balanço patrimonial. Isso vale para todos os ativos.
- **Todos os outros gráficos juntos, embaixo dos dados escritos, um abaixo do outro**, depois do divisor "Gráficos". Ficam lá: histórico de um indicador, dividendos, payout, receitas e lucros, lucro × cotação e patrimônio.
- **Menu do topo funcionando**: usa `data-go` + `scrollIntoView`. Não use link com `#secao`, porque isso quebrou a prévia e o hash é lido como ticker.
- **Legenda clicável em todos os gráficos**: clicar numa série esconde ou mostra só ela (`[data-lg]`, estado em `el._ocultas`).
- **ⓘ ao lado de cada nome** (ROE, ROIC, P/VP...): abre um quadradinho com explicação simples **na própria página**, sem ir para outra. Os textos estão nos dicionários `EXP` (ações e BDR) e `EXPF` (FII) em `acao.html`. Todo indicador novo precisa ganhar texto lá.
- **"← Pesquisa"** no topo da página do ativo e uma **caixa "Buscar outro ativo"** com sugestões enquanto digita.
- Funciona no celular. Testado em 390 px de largura, sem rolagem lateral.
- **Emoji em cada informação** da empresa ou do fundo (dicionário `EMO` em `acao.html`; diferentes dos do Investidor10). Campo novo sem emoji ganha 📌.
- **Comunicados e relatórios** (última seção, antes do rodapé; no menu fica no fim), dividida ao meio, 6 por página, com link para o documento original:
  - esquerda, *Comunicados*: ação = CVM IPE; FII = B3 Fundos.NET; BDR = SEC (10-K, 10-Q, 8-K...).
  - direita, o material visual de resultados: FII = *Relatório Gerencial* (Fundos.NET, tipo "Relatório Gerencial", rótulo com o mês de referência); ação = IPE com tipo "Apresentações a analistas/agentes do mercado", "Press-release" ou "Relatório de Análise Gerencial"; BDR = 8-K com item 2.02 (release de resultado; o link abre a página do envio, o release é o anexo 99.1).
- **Gráficos novos, no fim da página**, todos calculados no navegador a partir do JSON do ativo + `dados/indices.json`, então se atualizam junto com o robô:
  - *Comparação com índices* (1A, 2A, 5A, 10A): o ativo com proventos reinvestidos contra CDI, IPCA, IBOV, IFIX, SMLL, IDIV e IVVB11, com a calculadora "Se você tivesse investido R$ X há N anos". FII começa no primeiro rendimento confiável (abr/2022 no MXRF11) e a nota avisa.
  - *Termômetro* (1A, 2A, 5A, 10A; mostra 3 linhas e "Ver mais"): cada indicador de hoje numa régua do mínimo ao máximo do próprio ativo, com a média. Ações e BDR: P/L, P/VP, DY e EV/EBIT no fim de cada mês = múltiplo do último balanço anual × variação do preço (BDR usa `preco_eua_mensal`, a ação nos EUA) × ajuste pelo lucro/EBIT dos últimos 4 trimestres já publicados (2 meses após o fim do trimestre). ROE e margem só em 5A/10A (anuais). FII: P/VP, DY 12M e rendimento do mês, mensais. Texto neutro ("parte alta/baixa do histórico"), nunca "barato/caro".
    - **A pessoa escolhe os indicadores** (08/11/2026): "+ Adicionar indicador" no topo, "×" em cada linha e "Voltar ao padrão". Padrão em `TRM_PAD`; a escolha fica no `localStorage` (`ci_termometro`), separada para empresas e FIIs. Além dos de antes, entram P/Receita, P/EBIT e P/Ativo (mês a mês) e, em 5A/10A, os do balanço anual de `TRM_ANUAL` (ROA, ROIC, margens, endividamento, liquidez, giro).
  - *Quanto caiu e quanto demorou para voltar* (1A, 2A, 5A, 10A, MAX): queda desde o topo do período escolhido (com proventos reinvestidos), a maior queda, o tempo de recuperação e a tabela das quedas de 10% ou mais.
  - *Quanto tempo segurar*: para cada pregão do histórico como data de compra, o resultado depois de 1, 2, 5 e 10 anos (preço + proventos reinvestidos, `trIndex()`): % de vezes no positivo, % que bateu o CDI (CDI aproximado pelo mês), pior, **média** (média simples, com % ao ano; o Fabricio pediu "média" no lugar de "típico") e melhor. Prazo com menos de 120 datas de compra aparece como "histórico curto". O gráfico (`caminhos(N)`) mostra R$ 1.000 mês a mês desde a compra até N anos: linha "Média", "Quando foi bem" (percentil 90), "Quando foi mal" (percentil 10) e o CDI médio, que só sobe. Não volte ao gráfico antigo por data de compra: as linhas se cruzavam e o CDI parecia cair, e o Fabricio não entendeu.
    - A linha da média usa `--azul` (no site da Comunidade, o verde de `--c1` era igual ao de "quando foi bem").
  - *Renda x inflação* (**só FII**, pedido do Fabricio): rendimentos por ano no valor da época e corrigidos pelo IPCA, e a tabela de *yield on cost* (quem comprou em janeiro de cada ano recebe hoje X% sobre o que pagou), com 4 linhas e "Ver mais".
  - *Quem são os donos e o número de ações* (ação), *Número de ações* (BDR) ou *Quem são os cotistas* (FII): rosca dos maiores acionistas (controlador marcado, ON e PN quando a empresa tem as duas) e barras do nº de ações por ano em 2A, 5A ou 10A (`st.na`) com o texto "emitiu ações novas" ou "recomprou e cancelou". FII: rosca dos tipos de cotista e a linha de cotistas ou de cotas emitidas (botões), 10 anos.
  - *Lado a lado com o setor* (assinantes): lê o `indice.json` (o mesmo da pesquisa) e compara com os ativos do mesmo `segmento` (FII: mesmo `tipo_fundo`); se o grupo tiver menos de 3, usa o mesmo `setor`. Régua igual à do termômetro (traço grande = o ativo, bolinhas = os outros, traço pequeno = média) e a tabela com todos os números no "Ver mais". Banco não mostra margem nem dívida/EBITDA. Fica melhor sozinho conforme o site ganha ativos; para a prévia entraram ITUB4, BBDC4, ABCB4, MSFT34, AAPL34, M1TA34, KNCR11, KNIP11 e CPTS11. Texto neutro, nunca "melhor" ou "pior".
    - Os ativos comparados ficam numa caixa que abre (`.cmpQuem`), com o código e o nome de cada um e o link para a página dele, em vez de uma frase com todos os códigos.
  - FII: a *Distribuição da carteira* virou rosca (SVG). Saiu o gráfico antigo "Rentabilidade acumulada x CDI e IPCA", que a comparação substitui.
- Cores dos gráficos: `--c1` a `--c8` no `:root` (`--c6` a `--c8` são da comparação e da rosca).

## 4. Mapa dos arquivos

| Arquivo | O que é |
|---|---|
| `atualizar.py` | O robô (cerca de 1.100 linhas). Baixa, calcula e grava `dados/<TICKER>.json` + `dados/indice.json` + `dados/indices.json` (índices para a comparação) |
| `index.html` | A pesquisa. Lê `indice.json` e manda para `acao.html?t=TICKER`. Lê `?q=` e `?tipo=` da URL |
| `acao.html` | A página de qualquer ativo (`?t=TICKER`). `render()` faz ação e BDR, `renderFii()` faz FII |
| `tesouro.html` + `tesouro.py` | Página do Tesouro Direto (veio da área de investimentos da Comunidade; CSS e JS embutidos) e o robô dela, que grava `dados/tesouro.json`. A página busca esse JSON ao abrir e, se falhar, usa os dados embutidos. Pegadinha: a API do Banco Central responde 304 para `ultimos/1`; use `ultimos/10` |
| `config.js` | `window.CI_DADOS_URL` (onde estão os JSON). Opcionais: `CI_PAGINA_ATIVO`, `CI_PAGINA_PESQUISA` |
| `netlify.toml` | Sem build, publica a raiz e dá CORS `*` em `/dados/*`. Tem uma linha `ignore` comentada (parte B do passo a passo) |
| `.github/workflows/atualizar.yml` | Cron `30 0 * * 2-6` (21h30 BRT, seg a sex) e `0 11 * * 2-6` (repescagem às 8h), mais `workflow_dispatch` |
| `dados/` | Saída: o que as páginas leem |
| `cache/` | Memória do robô. **Não apagar.** Detalhes na seção 6 |
| `PASSO-A-PASSO.md` | Como pôr no ar (GitHub + Netlify) |
| `LEIA-ME.md` | Visão para humanos: fontes, como adicionar ativo, diferenças conhecidas |

Para testar localmente, rode `python -m http.server 8765` na pasta e abra `http://localhost:8765/`. As páginas usam `fetch`, então abrir o arquivo direto com duplo clique não funciona.

Como o robô funciona:

- `python atualizar.py` faz a atualização do dia.
- `python atualizar.py --historico` refaz tudo do zero, desde 2009 (uns 1,5 GB de download).
- Ticker novo em `EMPRESAS` baixa o próprio histórico sozinho na primeira vez. Vários tickers novos de uma vez baixam o histórico de cotações juntos, numa passada só pelos arquivos anuais da B3 (`novos_t` no `main`), e não um por um.

## 5. Formato dos dados

### `dados/indice.json`

É uma linha por ativo, feita pela função `resumo(d)`. É isto que a pesquisa lista:

```json
{"atualizado": "2026-11-08 02:22", "acoes": [
  {"ticker": "BBAS3", "nome": "Banco do Brasil", "tipo": "acao", "setor": "Financeiro", "segmento": "Bancos",
   "fechamento": "2026-11-06", "preco": 17.13, "var_dia": 3.88, "var_12m": -25.07, "dy": 4.03, "pvp": 0.53,
   "pl": 8.0, "roe": 6.6, "liquidez": 1163271197.6, "valor_mercado": 98169187105.2, "moeda_vm": "BRL"}]}
```

Regras do índice:

- Percentuais já vêm em % (4.03 = 4,03%).
- `pl` e `roe` são `null` para FII.
- `moeda_vm` é `USD` para BDR, porque o valor de mercado é o da empresa nos EUA.
- Para o "Lado a lado com o setor", cada linha também tem `tipo_fundo, margem_liquida, divliq_ebitda, cagr_lucros_5a, cagr_receitas_5a, taxa_adm, rent_12m, cotistas`.
- Em escala, mantenha o índice enxuto: cerca de 400 bytes por linha, 2.000 ativos ≈ 800 KB.

### `dados/<TICKER>.json`

**Campos comuns a todos:** `ticker`, `tipo`, `nome`, `razao`, `setor`, `segmento`, `atualizado` (horário de Brasília), `fechamento` (último pregão), `preco`, `cotacao`, `moeda_balanco`, `balanco_ref`, `proventos`, `eventos`, `comunicados`.

- `comunicados` (até 60) e `relatorios` (até 36, sem repetir título: reenvio fica só o mais novo) são listas de `{data, titulo, tipo, url}`, do mais novo para o mais antigo. Se a fonte falhar, o robô mantém as listas de ontem. O FII busca os 200 documentos mais recentes no Fundos.NET (`l` aceita no máximo 100, por isso 2 páginas: `s=0` e `s=100`).

- `cotacao` é uma lista de `[data, abertura, máxima, mínima, fechamento, volume_R$]`, ajustada por desdobramentos e grupamentos.
- `proventos` é uma lista de `{tipo, data_com, pagamento, valor}`, já ajustados por desdobramento.
- `eventos` é uma lista de `{data, fator}` (desdobramento > 1, grupamento < 1).

**Campos de ação (`acao`) e BDR (`bdr`):**

- `indicadores`: `pl, pvp, psr, ev_ebit, ev_ebitda, p_ebit, p_ativo, p_acl, p_cg, lpa, vpa, margem_bruta, margem_ebit, margem_ebitda, margem_liquida, giro_ativos, roe, roa, roic, dy, payout, liquidez_corrente, pl_ativos, passivos_ativos, divliq_pl, divliq_ebitda, valor_mercado, valor_firma, cagr_receitas_5a, cagr_lucros_5a`
- `info`: valor de mercado, valor da firma, PL, nº de papéis, ativos, dívidas, free float, tag along, liquidez diária, listagem, CNPJ, site e atividade. Para BDR também `preco_eua, data_eua, dolar, paridade, n_bdrs, depositario, ticker_eua`.
- `anual` (por ano) e `trimestres` (por data de balanço): receita, custos, lucros, EBIT, EBITDA, imposto, ativos, passivos, PL, dívida, caixa e ações.
- `ttm`: soma dos últimos 4 trimestres.
- `hist_indicadores`: os indicadores calculados ano a ano.
- Só BDR: `proventos_empresa` (dividendo em US$ por ação nos EUA), `preco_eua_anual` e `preco_eua_mensal` (último pregão de cada mês nos EUA, usado no termômetro).
- `acoes_hist`: `{ano: nº de ações no fim do ano, "hoje": nº atual}`, já corrigido por desdobramentos, grupamentos e bonificações (BDR: desdobramentos nos EUA), para mostrar emissão ou recompra de verdade.
- Só ação: `donos`: `{data, lista: [{nome, pct, on, pn, controlador, pessoa}], pf, pj, inst}`. Vem do Formulário de Referência da CVM (`fre_cia_aberta_posicao_acionaria_AAAA.csv`, só as linhas sem `ID_Acionista_Relacionado`, que são os acionistas diretos, na última versão) e as contagens de `fre_cia_aberta_distribuicao_capital`. O FRE é baixado uma vez por execução (`fre_zip`, ~8 MB) e serve para todas as empresas. A SEC não tem lista de acionistas em formato aberto, então o BDR fica sem `donos`.

**Campos de FII (`fii`):**

- `indicadores`: `dy, pvp, ultimo_rendimento, ultimo_rend_data, rend_medio_12m, rend_12m, vp_cota, pl, valor_mercado, liquidez_diaria, cotistas, cotas, taxa_adm_12m, rent_12m, dy_medio_5a`
- `info`: razão social, CNPJ, público-alvo, mandato, segmento na CVM, gestão, prazo, administrador, início, ISIN e site.
- `mensal` (`AAAA-MM`): PL, VP por cota, cotas, cotistas, taxa de administração e DY do mês.
- `anual`: rendimentos e DY por ano.
- `rentab`: `1m, 3m, 6m, 12m, 24m...`, cada um com fii, cdi e ipca.
- `serie_rent`: datas e as séries acumuladas fii, cdi e ipca.
- `composicao`: `{data, itens}`, a carteira por categoria.
- `cotistas`: `{data, total, grupos: [[tipo, quantidade]]}` do último informe mensal (pessoas físicas, empresas, bancos, fundos, previdência, de fora do Brasil). A CVM dá quantos cotistas há de cada tipo, não quanto cada um tem.

### `dados/indices.json` (um arquivo só, para todos os ativos)

`{atualizado, ultimo_dia, mensal: {IBOV, IFIX, SMLL, IDIV, IVVB11: {"AAAA-MM": pontos no último pregão do mês}}, cdi_mes: {"AAAA-MM": % no mês}, ipca_mes: {"AAAA-MM": % no mês}, fontes}`, desde jan/2012 (IVVB11 desde abr/2014). Os anos fechados ficam em `cache/indices/{INDICE}_{ano}.json` e não são baixados de novo.

## 6. Fontes, endereços e pegadinhas

Todas sem login e sem chave. O que cada uma dá:

| Fonte | Endereço | Uso |
|---|---|---|
| B3 COTAHIST anual | `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP` | Cotações desde 2009 (histórico) |
| B3 COTAHIST diário | `.../COTAHIST_D{ddmmaaaa}.ZIP` | Pregão do dia. **Um arquivo traz todos os ativos** |
| B3 empresas | `https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/{Metodo}/{base64 do JSON}` | `GetListedSupplementCompany` (proventos 12m, desdobramentos, dados do BDR), `GetListedCashDividends` (histórico de proventos em dinheiro, pelo **nome de pregão**), `GetDetail` (free float, site, atividade), `GetInitialCompanies` (lista de todas as empresas) |
| B3 fundos | `https://sistemaswebb3-listados.b3.com.br/fundsProxy/fundsCall/GetListedSupplementFunds/{base64 de {"cnpj":"só dígitos","identifierFund":"MXRF","typeFund":7}}` | Rendimentos 12m e desdobramentos de FII |
| CVM DFP/ITR | `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{DFP,ITR}/DADOS/{dfp,itr}_cia_aberta_{ano}.zip` | Balanços. **Um zip por ano traz todas as empresas** |
| CVM FRE | `.../CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{ano}.zip` | Free float, acionistas |
| CVM FII | `https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip` | Informe mensal de **todos** os FIIs: arquivos `geral`, `complemento` e `ativo_passivo` |
| SEC | `https://data.sec.gov/api/xbrl/companyfacts/CIK{10 dígitos}.json` | Balanços das empresas americanas (BDR e EUA) |
| Yahoo | `https://query1.finance.yahoo.com/v8/finance/chart/{SYM}?period1=..&period2=..&interval=1d&events=div%7Csplit` | Cotação nos EUA, dividendos e splits; rendimentos antigos de FII (`MXRF11.SA`) |
| B3 índices | `https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{base64 de {"language":"pt-br","index":"IFIX","year":"2025"}}` | Fechamento diário de IBOV, IFIX, SMLL e IDIV num ano: `results` com 31 linhas `{day, rateValue1..rateValue12}` (uma coluna por mês, número em formato brasileiro). `GetYearlyIndexes` e `GetIndexHistory` dão 404 |
| CVM IPE | `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip` | Comunicados das empresas (fato relevante, comunicado ao mercado, atas, avisos). **Um zip por ano traz todas as empresas**. Colunas `CNPJ_Companhia, Categoria, Tipo, Especie, Assunto, Data_Entrega, Link_Download`. Pule a categoria "Valores Mobiliários negociados e detidos" (é repetitiva) |
| B3 Fundos.NET | `https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados?d=0&s=0&l=60&o%5B0%5D%5BdataEntrega%5D=desc&cnpjFundo={só dígitos}` com o cabeçalho `X-Requested-With: XMLHttpRequest` | Documentos do FII. Link: `https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={id}` |
| SEC submissions | `https://data.sec.gov/submissions/CIK{10 dígitos}.json` → `filings.recent` | Documentos da empresa americana (10-K, 10-Q, 8-K...). Link: `https://www.sec.gov/Archives/edgar/data/{cik sem zeros}/{accessionNumber sem traços}/{primaryDocument}` |
| Banco Central SGS | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{N}/dados?formato=json&dataInicial=..&dataFinal=..` | 1 = dólar PTAX, 12 = CDI diário, 433 = IPCA mensal. Pedir em janelas de até 10 anos |

**Pegadinhas já resolvidas** (não "conserte" de volta):

- **COTAHIST** é texto de largura fixa. Use o mercado à vista (TPMERC 010). Os preços vêm em centavos e sem vírgula. O volume usado é o financeiro.
- **Desdobramentos**: ajuste a cotação e os proventos antigos pelo fator dos eventos da B3. O MXRF11 teve desdobramento de 1 para 10 em 16/05/2017, e o VP por cota e o nº de cotas antigos também precisam desse ajuste.
- **Lucro de banco**: na DRE consolidada da CVM, até 2019 o lucro do banco está na conta **3.09**, não na 3.11. O robô procura pela descrição (`^lucro.*consolidado do per[íi]odo`, nível 1) e só usa a 3.11 se não achar.
- **Nº de ações na SEC**: use o número do **arquivo original** de cada período. O 10-K seguinte já vem corrigido pelo desdobramento, então aplicar o split por cima dá P/L 10 ou 20 vezes errado (o Google 2021 deu P/L 504). Esse número original é multiplicado pelos splits posteriores. O código faz isso em `serie(..., primeiro=True)`.
- **Ano fiscal na SEC e na CVM**: não suponha que o ano termina em 31/12 (na CVM: `mes_fy` em `fin_brasil`). O ano fiscal acaba no fim do período de 350 a 380 dias do 10-K (semanas de 52/53 variam uns dias). O ytd começa no dia seguinte ao fim do ano fiscal anterior (`inicios` em `fin_eua`).
- **Proventos de BDR**: a B3 só mostra 12 meses. O robô acumula o que vê em `cache/proventos/{T}.json`, então o histórico cresce sozinho. Para trás, estima assim: dividendo em US$ × PTAX da data com × 0,7 (imposto de 30% retido nos EUA) ÷ k, sendo k a paridade calibrada com os pagamentos reais. Na tabela aparece como **"Dividendo (estimado)"**.
- **Rendimentos de FII**:
  - A B3 só mostra 12 meses (acumulados em `cache/proventos/`).
  - O Yahoo tem o MXRF11 contínuo só a partir de **abr/2022** e desconta direitos de subscrição. Arredonde para 0,005, que é como o fundo paga.
  - Use só o trecho contínuo mais recente: um buraco de mais de 50 dias corta o histórico.
  - A **data com** é o pregão anterior à data ex; use o dia útil anterior para não cair em feriado (deu duplicado no Finados).
  - Junte duplicados com tolerância de ±8 dias.
- **Nº de ações na CVM sem escala**: o arquivo `composicao_capital` do DFP/ITR não diz se está em unidades ou em milhares, e varia por empresa e por ano (Itaú sempre em milhares, Bradesco até 2023 em milhares). O robô escolhe x1 ou x1000, o que ficar mais perto do `totalNumberShares` da B3 de hoje. Sem isso o P/L do Itaú dava 0,01. Esse arquivo só existe desde 2020, então o gráfico de nº de ações de empresa brasileira começa em 2020.
- **Empresa só com balanço individual**: o ABC Brasil (ABCB4) parou de entregar o consolidado depois de 2023, e o robô só lê o consolidado. Ficou fora; o Banrisul (BRSR6) entrou no lugar.
- **Eventos da B3 que não mexem no preço**: a lista `stockDividends` traz "CIS RED CAP" (cisão com redução de capital, como a saída da XP do Itaú em 2021) e até um grupamento de 100 para 1 do Itaú em 2011 que não aconteceu no preço. O robô só usa DESDOBRAMENTO, BONIFICACAO e GRUPAMENTO, junta os do mesmo dia (o Bradesco teve um de 50 e um de 0,02 no mesmo dia, que se anulam) e descarta o que não aparece na cotação (`validar_eventos`: fechamento antes ÷ depois tem que bater com o fator, folga de 60%; bonificação pequena passa sempre). A cisão não é ajustada: a cotação antiga do Itaú fica sem o desconto da XP.
- **Fator do nº de ações de anos antigos** (`fatk`) é o produto de **todos** os eventos depois da data, não só o mais recente.
- **Ação PNA ou PNB**: o tipo do provento na B3 segue o final do código (3 = ON, 5 = PNA, 6 = PNB, o resto PN).
- **Meta e outras com mais de uma classe na SEC** não informam `CommonStockSharesOutstanding`: o robô usa a média ponderada de ações do trimestre ou do ano (`WeightedAverageNumberOfSharesOutstandingBasic`).
- **Unit (SANB11, BPAC11...)**: o nº de ações da CVM conta ON e PN separadas, e a unit junta várias. Ainda não está tratado: antes de incluir uma unit, divida o nº de ações pelo tamanho da unit e confira o provento da unit.
- **DY_mes da CVM** de anos antigos tem lixo (negativo, repetido). Não use para estimar rendimento.
- **Coluna de CNPJ do informe de FII** muda de nome: é `CNPJ_Fundo_Classe` nos anos novos e `CNPJ_Fundo` nos antigos.
- **www.sec.gov** (onde fica `company_tickers.json`) deu **403** a partir do ambiente do Claude. Já `data.sec.gov` funciona. No GitHub Actions, com um User-Agent de contato correto, deve funcionar; senão use a lista do S&P 500 da Wikipédia, que já traz o CIK.
- **Troca de paridade de BDR**: a B3 nem sempre lista nos eventos. O GOGL34 passou de 1 para 6 em 22/10/2020 e a B3 não mostra; sem ajuste, o gráfico de quedas dizia "-84%". `trocas_paridade()` procura saltos de mais de 40% num dia que o papel nos EUA (convertido pelo dólar) não teve, e acrescenta o fator aos eventos. O robô imprime `troca de paridade detectada` quando acha uma.
- **IPCA** sai por volta do dia 10 do mês seguinte, então a linha do IPCA na comparação termina um ou dois meses antes das outras. A nota do gráfico mostra até quando vai.
- A **BBAS3 caiu cerca de 30% em 26/10/2026**. É dado real da B3, não erro de ajuste.

## 7. Fórmulas (conferidas contra o Investidor10 no BBAS3 e no GOGL34)

- **Nº de ações** = total, **incluindo tesouraria** (composição do capital da CVM; na SEC, `dei:EntityCommonStockSharesOutstanding` do arquivo original).
- **LPA** = lucro líquido **do controlador** (TTM) ÷ nº de ações. **VPA** = PL do controlador ÷ ações.
- **P/L** = preço ÷ LPA. **P/VP** = preço ÷ VPA. **PSR** = valor de mercado ÷ receita TTM.
- **Valor da firma (EV)** = valor de mercado + dívida líquida. **Para banco, EV = valor de mercado.**
- **Banco**: ativo circulante = conta **1.02** e passivo circulante = **2.02** (é assim que o Investidor10 trata).
- **P/ACL** = valor de mercado ÷ (ativo circulante − passivo total, incluindo o PL, como o Investidor10 faz).
- **CAGR receitas/lucros 5 anos** = TTM comparado com o ano (último ano fechado − 4).
- **Liquidez diária** = média do volume financeiro dos últimos **21 pregões**.
- **DY** = soma dos proventos com **data com** nos últimos 12 meses ÷ preço. **Payout** = proventos ÷ lucro.
- **BDR**: indicadores com o balanço em dólar e a **cotação da ação original nos EUA** (mesmo critério do Investidor10). DY com os proventos do BDR em R$ ÷ preço do BDR.
- **FII**:
  - **DY** = rendimentos 12m ÷ preço.
  - **P/VP** = preço ÷ `Valor_Patrimonial_Cotas` do último informe.
  - **Rentabilidade** = (preço final + rendimentos pelas datas ex no período) ÷ preço inicial − 1, comparada com o CDI e o IPCA acumulados no mesmo período.
  - **Taxa de administração 12m** = soma dos últimos 12 `Percentual_Despesas_Taxa_Administracao` mensais.
  - **Carteira** = categorias do `ativo_passivo`.

## 8. Diferenças aceitas (não perca tempo tentando zerar)

- **ROIC e imposto de banco**: o Investidor10 usa outro imposto. Aqui fica o da CVM, por isso o ROIC do BB sai diferente (até negativo).
- **Receita por região e por segmento**: não existe em arquivo estruturado da CVM ou da SEC (só em PDF de release). Seção não feita.
- **FII**: sem rendimentos antes de abr/2022 (MXRF11). Sem vacância, que só está no informe trimestral e só para fundo de imóveis.
- **Cotação é a de fechamento.** Tempo real exige contrato pago com a B3.

## 9. Plano para escalar para todos os ativos

Não dá para montar um ativo por vez: o código já é genérico e o que falta é **gerar a lista `EMPRESAS` sozinho** e **baixar em lote**. A estimativa é de uns 2 dias de trabalho. Faça nesta ordem e teste cada passo com 20 ou 30 ativos antes de rodar com todos.

### 9.1 Montar o universo automaticamente

Crie um arquivo `universo.py` (ou uma função) que gera `cache/universo.json` uma vez por semana, com uma linha por ativo no mesmo formato de `EMPRESAS`:

- **Tickers da B3**: do COTAHIST do último pregão. Fique com TPMERC 010 e lote padrão e classifique pelo **ISIN**:
  - `...ACN...` = ação (exemplo `BRBBASACNOR3`)
  - `...CTF...` = FII (exemplo `BRMXRFCTF008`)
  - `...BDR...` = BDR (exemplo `BRGOGLBDR001`)
  - Confira os códigos BDI no layout oficial do COTAHIST (`SeriesHistoricas_Layout.pdf`, no site da B3) antes de filtrar por eles.
  - Descarte ativos sem negócio nos últimos 30 dias.
- **Ações → CNPJ, nome de pregão e setor**:
  - `GetInitialCompanies` da B3. São cerca de 3.550 registros, e o tipo 1 dá cerca de 567 empresas com ações.
  - O cadastro da CVM (`https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv`, com setor).
  - O FCA da CVM (`.../CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip`, arquivo de valores mobiliários com o código de negociação). Confira os nomes de coluna no arquivo.
  - Os 4 primeiros caracteres do ticker são o `b3`.
  - Marque `banco: True` quando o setor da CVM for banco, ou quando a DFP tiver a estrutura de instituição financeira.
- **FIIs → CNPJ**: no `inf_mensal_fii_{ano}_geral` da CVM, ligue o ISIN da cota ao CNPJ do fundo (o nome das colunas muda entre anos, veja a seção 6). Segmento e tipo vêm do próprio informe (mandato e segmento de atuação).
- **BDRs → empresa nos EUA**: do `GetListedSupplementCompany` do BDR (vem código e paridade) e do ticker americano, ache o **CIK** (Wikipédia "List of S&P 500 companies" tem o CIK; `company_tickers.json` da SEC, se acessível). Fique só com as empresas que entregam balanço à SEC (10-K/10-Q). Pule ETFs e BDRs de empresas não americanas, ou trate sem balanço.
- **S&P 500 sem BDR**: lista da Wikipédia (ticker, nome, setor GICS e CIK). Isso pede um **tipo novo `eua`**: ação americana com preço em US$ do Yahoo e balanço da SEC. É o caminho do BDR sem a parte da B3 e sem a conversão. No `acao.html`, reuse `render()` com a moeda em US$ e sem o bloco "dados do BDR"; no `index.html`, adicione o botão "EUA" no filtro de tipos.

### 9.2 Baixar em lote, não ativo por ativo

O robô de hoje já baixa os zips da CVM uma vez e filtra pelos CNPJs. Em escala:

- **Cotações**: **um** COTAHIST diário por dia, lido uma vez, com uma linha acrescentada em `cache/cotacoes/{T}.csv` para cada ticker. Hoje `atualizar_cotacoes` é chamada por ativo; troque por uma chamada única com todos os tickers. Ela já aceita uma lista.
- **Balanços BR**: DFP e ITR do ano atual e do anterior, uma vez para todos os CNPJs. Divida por CNPJ em `cache/cvm/{cnpj}/`.
- **FII**: um zip do informe mensal do ano para todos os fundos. Divida por CNPJ em `cache/fii/{cnpj}/`.
- **B3 (proventos, desdobramentos, free float)**: são 3 chamadas por ativo, e com cerca de 2.000 ativos isso pesa. Faça cache por idade:
  - `GetListedSupplementCompany` / `GetListedSupplementFunds`: todo dia (traz os 12 meses).
  - `GetListedCashDividends` (histórico completo): uma vez por semana.
  - `GetDetail`: uma vez por mês.
  - Guarde a data da última busca no cache.
- **SEC**: balanço só muda a cada trimestre. Busque o `companyfacts` de um CIK uma vez por semana, ou só quando o endpoint `https://data.sec.gov/submissions/CIK{cik}.json` mostrar um 10-Q/10-K novo. Limite: no máximo 10 requisições por segundo.
- **Comunicados**: o IPE da CVM é um zip por ano para todas as empresas (baixe uma vez por rodada). Fundos.NET e SEC são uma chamada por ativo: em escala, busque uma vez por dia só para quem negociou, ou uma vez por semana para o resto.
- **Índices**: `indices.json` é um só para todos os ativos; não muda com a escala.
- **Yahoo**: uma chamada por ativo americano por dia, usando `range=5d` no dia a dia e o histórico inteiro só na primeira vez.
- **Paralelismo**: `concurrent.futures.ThreadPoolExecutor(max_workers=8)` para B3, Yahoo e SEC, com novas tentativas e pausa crescente (já existe em `baixar`). Se a B3 ou o Yahoo devolverem 429, baixe para 4 workers.
- Meta: atualização diária em **menos de 15 minutos** no GitHub Actions. A primeira carga leva horas e pode rodar em partes.

### 9.3 Deixar os arquivos leves

Hoje um JSON tem de 160 a 280 KB, por causa da cotação diária desde 2009. Com 2.000 ativos daria uns 400 MB.

- No `dados/`, grave a cotação como `[data, fechamento]`: diária nos últimos 2 anos e semanal antes disso. O OHLC completo fica só no `cache/`. Ajuste o `chart` da cotação no `acao.html` para ler o formato novo, verificando o tamanho de cada linha para continuar aceitando o antigo.
- Grave sem espaços (`separators=(',', ':')`, como já está). A Netlify e o GitHub Pages já entregam com gzip.
- Alvo: até cerca de 50 KB por ativo, uns 100 MB no total.
- O robô já **não regrava um JSON quando só o horário mudou** (função `gravar`). Isso evita commit e publicação sem dado novo.

### 9.4 Onde guardar e publicar em escala

Commitar 100 MB de JSON todo dia incha o histórico do git (gigabytes por ano). Troque para:

- **`cache/`** fora do git: `actions/cache` com a chave `cache-${{ github.run_id }}` e `restore-keys: cache-`. Isso restaura o último e salva um novo a cada rodada; o limite é 10 GB por repositório. Faça também um backup semanal do cache como *release asset* ou *artifact*, porque o `actions/cache` apaga o que fica 7 dias sem uso.
- **`dados/`** publicado sem commit:
  - Opção A, grátis e recomendada: **GitHub Pages via Actions** (`actions/upload-pages-artifact` + `actions/deploy-pages`). O site pode ter até 1 GB e o CORS já vem liberado. As páginas leem os dados via `config.js` (`CI_DADOS_URL = 'https://USUARIO.github.io/REPO/dados/'`).
  - Opção B: um **site separado na Netlify só para os dados**, publicado com `netlify deploy --prod --dir=dados` (token em secret). O `--prod` substitui o site inteiro, por isso tem que ser um site separado, nunca o site principal. Atenção: no plano por créditos da Netlify, cada publicação gasta 15 dos 300 créditos grátis do mês.
- O HTML (`index.html`, `acao.html`, `config.js`) continua na Netlify, e só muda quando você muda o código.

### 9.5 Ordem sugerida de trabalho

1. `universo.py` + teste: imprimir quantos ativos de cada tipo e conferir 10 ao acaso no site da B3.
2. Cotações em lote + JSON enxuto + `acao.html` lendo o formato novo.
3. Ações BR: rodar 30, comparar 5 com o Investidor10 (checklist da seção 10), depois todas.
4. FIIs: idem.
5. BDRs, depois o tipo `eua` (S&P 500).
6. Cache por idade + paralelismo, medindo o tempo da rodada diária.
7. Workflow novo (actions/cache + Pages), com aviso claro no log de quantos ativos falharam.
8. Pesquisa: botão "EUA", conferir que a paginação e a busca continuam rápidas com o índice completo.

## 10. Checklist de validação (rode a cada mudança grande)

- [ ] `python atualizar.py` termina, e o log mostra `ok TICKER` para todos (ou `ERRO` só onde a fonte caiu, com o JSON de ontem mantido).
- [ ] `index.html`:
  - [ ] lista todos os ativos;
  - [ ] busca "maxi" acha o MXRF11, e "brasil" + Enter abre o BBAS3;
  - [ ] filtro por tipo e setor funciona;
  - [ ] ordenar por DY e por liquidez funciona;
  - [ ] paginação funciona.
- [ ] `acao.html?t=BBAS3`, `?t=GOGL34` e `?t=MXRF11`:
  - [ ] sem erro no console;
  - [ ] "Ver mais" abre e fecha;
  - [ ] menu do topo rola até a seção certa;
  - [ ] legenda esconde e mostra a série;
  - [ ] ⓘ abre a explicação;
  - [ ] "← Pesquisa" volta;
  - [ ] busca do topo sugere.
- [ ] Celular (390 px): sem rolagem lateral, e os rótulos dos eixos não se sobrepõem.
- [ ] Compare com o Investidor10, para 5 ativos de cada tipo:
  - ações: P/L, P/VP, DY, ROE, margem líquida, LPA, VPA, liquidez e valor de mercado;
  - FII: DY, P/VP, último rendimento, VP por cota e cotistas.
  - Diferença aceitável: a do dia de cotação. Se uma passar de 2%, investigue antes de seguir.
- [ ] Um ativo com desdobramento recente: a cotação antiga e os proventos antigos estão ajustados.
- [ ] Um banco além do BB (por exemplo ITUB4): lucro de anos antes de 2020 preenchido.

## 11. Como foi feito o teste até aqui

Testes com Playwright no Chromium, com o site servido por `python -m http.server`, em 1200 px e 390 px:

- fluxo da pesquisa (busca, filtros, ordenação, Enter);
- busca do topo da página do ativo;
- legendas, ⓘ e "Ver mais";
- console sem erros.

Repita esse tipo de teste depois de cada mudança no HTML.
