# Páginas de ações (estilo Investidor10) que se atualizam sozinhas

## O que tem aqui

| Arquivo | Para que serve |
|---|---|
| `index.html` | A pesquisa: lista todos os ativos do `dados/indice.json`, com busca, filtro por tipo e setor e ordenação |
| `acao.html` | A página do ativo. Abre pelo endereço: `acao.html?t=BBAS3`, `acao.html?t=GOGL34` ou `acao.html?t=MXRF11` (ações, BDRs e fundos imobiliários usam a mesma página) |
| `universo.py` | A lista de ativos: todas as ações e FIIs negociados na B3 no último mês e os BDRs de empresas americanas. Grava `cache/universo.json` uma vez por semana |
| `atualizar.py` | O robô. Baixa os dados públicos, calcula os indicadores e grava `dados/<TICKER>.json` de todos os ativos da lista |
| `dados/` | O que a página lê (um JSON por ação + `indice.json` com o resumo de todas + `indices.json` com IBOV, IFIX, SMLL, IDIV, IVVB11, CDI e IPCA mês a mês, para a comparação) |
| `cache/` | Histórico guardado pelo robô (cotações desde 2009, balanços da CVM, proventos de BDR). Não apague |
| `tesouro.html` | Tesouro Direto: todas as taxas à venda, se estão altas ou baixas contra 5 anos, simulador até o vencimento e de venda antecipada. Lê `dados/tesouro.json` |
| `tesouro.py` | Robô do Tesouro: baixa as taxas do Tesouro Transparente e os juros do Banco Central e grava `dados/tesouro.json` (roda junto com o `atualizar.py`) |
| `config.js` | Onde as páginas buscam os dados (padrão: a pasta `dados/` do próprio site) |
| `netlify.toml` | Configuração da Netlify (sem build; libera a leitura dos dados por outros sites) |
| `.github/workflows/atualizar.yml` | Agenda o robô todo dia útil às 21h30 (e repete às 8h do dia seguinte), guarda a memória dele (`cache/`) no próprio GitHub Actions e publica o site no GitHub Pages |

## Fontes (todas públicas e gratuitas)

- **B3**: cotação de fechamento de cada dia (arquivo COTAHIST), proventos, desdobramentos/grupamentos, free float, segmento de listagem, dados do BDR.
- **CVM**: balanços trimestrais (ITR) e anuais (DFP) das empresas brasileiras.
- **SEC (EUA)**: balanços das empresas americanas, usados nos BDRs.
- **Yahoo Finance**: cotação da ação original nos EUA e dividendos pagos lá (só BDR).
- **Banco Central**: dólar PTAX, CDI e IPCA.
- **B3 (índices)**: IBOV, IFIX, SMLL e IDIV, para o gráfico de comparação. O IVVB11 (S&P 500 em reais) vem da cotação no Yahoo.
- **Comunicados**: CVM (documentos das empresas), B3 Fundos.NET (documentos dos FIIs) e SEC (documentos das empresas dos BDRs).
- **CVM (fundos imobiliários)**: informe mensal de cada fundo (patrimônio, valor patrimonial por cota, cotas, cotistas, taxa de administração, carteira).

## Como colocar no ar

Siga o **PASSO-A-PASSO.md** (GitHub + Netlify, uns 20 minutos, uma vez só).

Com todos os ativos, os dados não vão mais para o git (seriam centenas de MB por dia). A memória do robô (`cache/`) e os JSON do dia ficam no próprio GitHub Actions (actions/cache), e o workflow publica o site no GitHub Pages. Para isso, **o dono do repositório precisa, uma vez**, ir em **Settings → Pages → Build and deployment → Source** e escolher **GitHub Actions**. Enquanto isso não for feito, o robô continua salvando no repositório só os ativos da lista `EMPRESAS`, como antes.

A SEC pede um e-mail de contato no pedido. Para o robô poder atualizar a lista de empresas americanas, crie a variável `CONTATO_SEC` com um e-mail de contato do site (Settings → Secrets and variables → Actions → Variables). Sem ela, vale a última lista guardada.

## Usar dentro do site da Comunidade Invest

- **Mais simples**: usar o endereço da Netlify (ou um subdomínio dela) e linkar no menu do site.
- **Páginas no próprio site**: copie `index.html`, `acao.html` e `config.js` e, no `config.js`, diga onde estão os dados:
  `window.CI_DADOS_URL = 'https://NOME.netlify.app/dados/';` (a leitura por outros sites já está liberada no `netlify.toml`).
- Outras configurações opcionais (ponha no `config.js`): `window.CI_PAGINA_ATIVO` (endereço da página do ativo, padrão `acao.html`) e `window.CI_PAGINA_PESQUISA` (endereço da pesquisa, padrão `index.html`).

## Quais ativos entram

A lista se monta sozinha (`universo.py`, uma vez por semana):

- **Ações**: todo código de ação negociado no mercado à vista da B3 no último mês, de empresa que está na lista de companhias da B3. O nome vem do cadastro da CVM, e o setor e o segmento, da classificação da B3.
- **FIIs**: todo fundo imobiliário negociado no último mês que aparece no informe mensal da CVM (pelo ISIN). O tipo (papel, tijolo, fundo de fundos ou híbrido) sai da carteira do último informe.
- **BDRs**: BDR de empresa (não de ETF) negociado no último mês, cuja empresa entrega balanço à SEC. A empresa é achada pelo nome, e o setor vem do código SIC.
  - Empresa americana (10-K/10-Q): balanço da própria SEC.
  - Empresa de fora dos EUA (20-F: TSMC, Nubank, ASML, Alibaba, Inter, Stone, Novo Nordisk...): balanço anual e trimestral do Yahoo Finance, convertido para dólar pelo câmbio de cada data, com o nº de ações em ADRs. Quem não divulga trimestre fica só com o anual, e a página avisa no topo.
- **ETFs**: todo fundo de índice negociado no último mês (CODBDI 14 no arquivo da B3: BOVA11, IVVB11, SMAL11...). Nome pelo Yahoo; administrador, proventos e desdobramentos pela B3. Não têm balanço: a página mostra cotação, proventos, comparação com índices, quedas e "quanto tempo segurar".
  - **O que tem dentro**: a carteira do mês que o ETF entrega à CVM (CDA, `cda_fie`), com a porcentagem de cada ativo sobre o patrimônio. A página mostra as 10 maiores e "Ver mais". Sai uns 35 dias depois do fim do mês; quem pediu sigilo à CVM aparece com o aviso.
  - Os fundos de infraestrutura listados (CDII11, JURO11, os "Isento" do Itaú e do Bradesco) entram junto, com o segmento "Fundo de infraestrutura" e o texto deles.

Ficam de fora, por enquanto:

- as **units** (SANB11, TAEE11, KLBN11...), porque o nº de ações da CVM conta ON e PN separadas;
- os FIIs sem ISIN no informe da CVM (uns 15% dos negociados);
- os BDRs de empresas que não entregam balanço à SEC (SK Hynix, por exemplo);
- as ações do S&P 500 sem BDR.

A lista `EMPRESAS` do `atualizar.py` continua valendo por cima: o que está escrito lá (nome, segmento, código nos EUA) vence o que veio da lista automática, e esses ativos entram mesmo sem negócio no mês.

Para testar com poucos ativos: `python atualizar.py --so BBAS3,MXRF11` ou `python atualizar.py --limite 30`.

## Em escala: como o robô não demora horas

- **Arquivos grandes, uma vez para todos**: a cotação do dia (um arquivo da B3 traz todos os ativos), os balanços da CVM (um zip por ano), o informe dos FIIs, o Formulário de Referência e os comunicados da CVM são baixados uma vez por rodada e separados por ativo numa leitura só.
- **Respostas guardadas** em `cache/rede/`:

  | O que | Por quanto tempo |
  |---|---|
  | Proventos dos últimos 12 meses (B3) | um dia |
  | Histórico de proventos (B3) | uma semana (o que saiu no meio da semana entra pelo complemento do dia) |
  | Detalhe da empresa (B3) | um mês |
  | Documentos dos FIIs e da SEC | 2 a 3 dias |
  | Histórico do Yahoo | uma semana (a cotação do dia nos EUA é buscada todo dia) |
  | Balanço da SEC | recalculado só quando a empresa entrega um 10-K ou 10-Q novo |

- **8 ativos ao mesmo tempo** (`TRABALHADORES`), porque a maior parte do tempo é espera da rede.
- **Ativo novo** ganha o histórico desde 2009 lendo os arquivos anuais da B3 uma vez para todos os novos.

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
