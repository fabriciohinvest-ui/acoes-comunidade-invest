# Páginas de ações (estilo Investidor10) que se atualizam sozinhas

## O que tem aqui

| Arquivo | Para que serve |
|---|---|
| `index.html` | A pesquisa: lista todos os ativos do `dados/indice.json`, com busca, filtro por tipo e setor e ordenação |
| `acao.html` | A página do ativo. Abre pelo endereço: `acao.html?t=BBAS3`, `acao.html?t=GOGL34` ou `acao.html?t=MXRF11` (ações, BDRs e fundos imobiliários usam a mesma página) |
| `atualizar.py` | O robô. Baixa os dados públicos, calcula os indicadores e grava `dados/<TICKER>.json` |
| `dados/` | O que a página lê (um JSON por ação + `indice.json` com o resumo de todas) |
| `cache/` | Histórico guardado pelo robô (cotações desde 2009, balanços da CVM, proventos de BDR). Não apague |
| `tesouro.html` | Tesouro Direto: todas as taxas à venda, se estão altas ou baixas contra 5 anos, simulador até o vencimento e de venda antecipada. Lê `dados/tesouro.json` |
| `tesouro.py` | Robô do Tesouro: baixa as taxas do Tesouro Transparente e os juros do Banco Central e grava `dados/tesouro.json` (roda junto com o `atualizar.py`) |
| `config.js` | Onde as páginas buscam os dados (padrão: a pasta `dados/` do próprio site) |
| `netlify.toml` | Configuração da Netlify (sem build; libera a leitura dos dados por outros sites) |
| `.github/workflows/atualizar.yml` | Agenda o robô todo dia útil às 21h30 (e repete às 8h do dia seguinte) |

## Fontes (todas públicas e gratuitas)

- **B3**: cotação de fechamento de cada dia (arquivo COTAHIST), proventos, desdobramentos/grupamentos, free float, segmento de listagem, dados do BDR.
- **CVM**: balanços trimestrais (ITR) e anuais (DFP) das empresas brasileiras.
- **SEC (EUA)**: balanços das empresas americanas, usados nos BDRs.
- **Yahoo Finance**: cotação da ação original nos EUA e dividendos pagos lá (só BDR).
- **Banco Central**: dólar PTAX, CDI e IPCA.
- **CVM (fundos imobiliários)**: informe mensal de cada fundo (patrimônio, valor patrimonial por cota, cotas, cotistas, taxa de administração, carteira).

## Como colocar no ar

Siga o **PASSO-A-PASSO.md** (GitHub + Netlify, uns 20 minutos, uma vez só).

## Usar dentro do site da Comunidade Invest

- **Mais simples**: usar o endereço da Netlify (ou um subdomínio dela) e linkar no menu do site.
- **Páginas no próprio site**: copie `index.html`, `acao.html` e `config.js` e, no `config.js`, diga onde estão os dados:
  `window.CI_DADOS_URL = 'https://NOME.netlify.app/dados/';` (a leitura por outros sites já está liberada no `netlify.toml`).
- Outras configurações opcionais (ponha no `config.js`): `window.CI_PAGINA_ATIVO` (endereço da página do ativo, padrão `acao.html`) e `window.CI_PAGINA_PESQUISA` (endereço da pesquisa, padrão `index.html`).

## Adicionar uma ação ou BDR

Abra o `atualizar.py` e acrescente uma linha na lista `EMPRESAS` (no começo do arquivo), copiando o modelo:

- Ação brasileira: ticker, CNPJ, código da B3 (4 letras), nome de pregão (como aparece em "Proventos em dinheiro" na B3), ISIN, setor e segmento. Se for banco, `'banco': True`.
- BDR: ticker, código da B3, CIK da empresa na SEC, ticker nos EUA e ISIN do BDR.
- Fundo imobiliário: `'tipo': 'fii'`, ticker, CNPJ do fundo, código da B3 (4 letras), ISIN da cota, segmento e tipo de fundo (copie a linha do MXRF11).

Na primeira vez que o robô vê uma empresa nova, ele baixa sozinho o histórico (cotações desde 2009 e balanços desde 2010). Essa primeira rodada demora mais (uns 20 a 30 minutos); depois volta aos 2 minutos.

## Diferenças conhecidas em relação ao Investidor10

- Indicadores conferidos com o BBAS3 do Investidor10: P/L, P/VP, PSR, EV/EBIT, LPA, VPA, margens, ROE, ROA, DY, payout, free float, CAGR e liquidez batem até a segunda casa decimal ou ficam muito perto (diferença de dia de cotação).
- **ROIC e imposto de banco**: o Investidor10 usa um imposto diferente do que está no balanço consolidado entregue à CVM; aqui usamos o da CVM, então o ROIC do BB sai diferente (dá negativo porque o imposto do período foi maior que o resultado operacional).
- **Receita por região e por segmento de negócio** não estão em nenhum arquivo estruturado da CVM/SEC (só nos PDFs de release), então essas duas seções não foram feitas.
- **Proventos de BDR**: a B3 só mostra os últimos 12 meses. O robô guarda tudo o que aparece (o histórico vai crescendo sozinho) e, para os pagamentos mais antigos, calcula uma estimativa a partir do dividendo pago nos EUA, do dólar e do imposto de 30% retido lá. Esses aparecem na tabela como "Dividendo (estimado)".
- Indicadores de BDR são calculados com o balanço da empresa em dólar e a cotação da ação original nos EUA, que é o mesmo critério do Investidor10.
- **Rendimentos de FII**: a B3 só mostra os últimos 12 meses (guardados pelo robô, o histórico cresce sozinho). Os anteriores vêm do Yahoo, que tem dados do MXRF11 só a partir de abr/2022 e desconta direitos de subscrição; o robô arredonda para o meio centavo, que é como o fundo paga. Antes de abr/2022 DY e rentabilidade aparecem como "-" em vez de um número inventado.
- **Vacância** de FII não está no informe mensal da CVM (só no trimestral, para fundos de imóveis), então não aparece no MXRF11, que é quase todo de papel.
- Cotação é a de **fechamento** do dia. Tempo real exige contratar dados da B3.

## Se algo der errado

- Se uma fonte estiver fora do ar, o robô mantém o arquivo de ontem daquela empresa e atualiza as outras. Na aba Actions aparece o aviso.
- Para refazer tudo do zero: `python atualizar.py --historico` (baixa uns 1,5 GB, leva uns 30 minutos).
