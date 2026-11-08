# Passo a passo: GitHub + Netlify (colocar o site no ar e se atualizando sozinho)

Tempo: uns 20 minutos, uma vez só. No fim você tem:

- `https://SEU-SITE.netlify.app/` → página de **pesquisa** (lista de ativos, busca, filtros).
- `https://SEU-SITE.netlify.app/acao.html?t=BBAS3` (e `GOGL34`, `MXRF11`) → página de cada ativo.
- Um robô no GitHub que, todo dia útil às 21h30, baixa os dados novos e salva no repositório. A Netlify vê a mudança e publica sozinha.

Como as peças conversam:

```
GitHub (repositório)  ──  robô roda todo dia útil (GitHub Actions)  ──  salva dados/*.json
        │
        └── a cada mudança, a Netlify publica o site  ──  visitante abre index.html / acao.html
```

---

## Parte A: subir os arquivos e ligar tudo

### 1. Criar o repositório no GitHub

1. Entre em https://github.com/new
2. **Repository name**: por exemplo `acoes-comunidade-invest`.
3. Marque **Public** (precisa ser público para a parte B, se você precisar dela; e as Actions ficam ilimitadas).
4. Não marque "Add a README". Clique em **Create repository**.

### 2. Subir os arquivos (2 rodadas, porque o GitHub aceita até 100 arquivos por vez)

Na página do repositório novo, clique no link **uploading an existing file** (ou *Add file → Upload files*).

**Rodada 1** (tudo menos a pasta `cache`):

1. No Windows, abra a pasta `Comunidade Invest\acoes-site`.
2. Selecione tudo **menos** a pasta `cache` (Ctrl+A e depois Ctrl+clique na pasta `cache` para desmarcar). Tem que ir junto: as pastas `.github` e `dados`, os arquivos `.gitignore` e `.nojekyll` e todos os `.html`, `.js`, `.py`, `.toml` e `.md`.
3. Arraste para a área do GitHub. Importante: arraste o **conteúdo** da pasta, não a pasta `acoes-site` inteira (senão tudo fica dentro de uma subpasta e o site não acha os arquivos).
4. Espere a lista de arquivos aparecer, desça e clique em **Commit changes**.

**Rodada 2** (a pasta `cache`, com o histórico guardado):

1. *Add file → Upload files* de novo.
2. Arraste a pasta `cache` inteira (essa sim, a pasta, para ficar `cache/...`).
3. **Commit changes**.

Confira: na página do repositório você deve ver na raiz `.github`, `cache`, `dados`, `acao.html`, `index.html`, `netlify.toml`... Se aparecer uma pasta `acoes-site` na raiz, foi arrastada a pasta em vez do conteúdo: apague o repositório (*Settings → Danger Zone → Delete*) e refaça.

### 3. Deixar o robô salvar no repositório

1. No repositório: **Settings → Actions → General**.
2. Lá embaixo, em **Workflow permissions**, marque **Read and write permissions** → **Save**.

### 4. Testar o robô uma vez na mão

1. Aba **Actions** do repositório. Se aparecer um botão verde "I understand my workflows, go ahead and enable them", clique.
2. Na esquerda, clique em **Atualizar ações** → botão **Run workflow** → **Run workflow**.
3. Leva uns 3 a 5 minutos. Bolinha verde = deu certo.
   - Se no final aparecer "nada mudou", é normal em fim de semana e feriado (não tem pregão novo).
   - Em dia útil depois das 21h, aparece um commit novo "dados de DD/MM/AAAA" na página do repositório.
   - Bolinha vermelha: clique nela, abra o passo que falhou e copie o texto do erro para o Claude.

### 5. Ligar a Netlify ao repositório

1. Na Netlify: **Add new project** (ou *Add new site*) → **Import an existing project**.
2. Escolha **GitHub** e autorize. Se o repositório não aparecer na lista, clique em **Configure the Netlify app on GitHub**, dê acesso ao repositório `acoes-comunidade-invest` e volte.
3. Escolha o repositório. Na tela de configuração:
   - **Branch to deploy**: `main`
   - **Base directory**: vazio
   - **Build command**: vazio
   - **Publish directory**: `.` (um ponto; já vem do `netlify.toml`)
4. Dê um nome ao projeto (vira o endereço `nome.netlify.app`) e clique em **Deploy**.
5. Em menos de 1 minuto fica "Published".

### 6. Ver funcionando

Abra e confira:

| Endereço | O que deve aparecer |
|---|---|
| `https://NOME.netlify.app/` | Página de pesquisa com 3 ativos. Digite "maxi" na busca: só o MXRF11. Clique em "FIIs", "Ações", "BDRs". Clique no título das colunas para ordenar |
| `https://NOME.netlify.app/acao.html?t=BBAS3` | Banco do Brasil: cotação no topo, indicadores com "Ver mais", gráficos embaixo |
| `.../acao.html?t=GOGL34` | Google (BDR), com dividendos estimados marcados |
| `.../acao.html?t=MXRF11` | Fundo imobiliário: rendimentos, P/VP, rentabilidade, carteira |
| `.../dados/indice.json` | Texto (JSON) com o resumo dos 3. Se abrir, os dados estão sendo publicados |

Na página de um ativo teste também: "← Pesquisa" volta para a lista; a caixa "Buscar outro ativo" no topo sugere enquanto digita; clicar nos nomes da legenda de um gráfico esconde/mostra a linha; clicar no ⓘ abre a explicação.

Pronto. A partir daqui o robô roda sozinho de segunda a sexta às 21h30 (e de novo às 8h do dia seguinte, caso a B3 tenha publicado tarde).

---

## Parte B: só se a sua Netlify for do plano por créditos

Desde setembro de 2025 as contas novas da Netlify usam **créditos**: o plano grátis dá 300 créditos por mês e **cada publicação gasta 15** (só 20 publicações por mês). O robô publica uma vez por dia útil, uns 22 dias por mês, então estoura o grátis, ainda mais somando o site principal da Comunidade.

**Como saber o seu plano**: na Netlify, clique no nome do time (canto superior esquerdo) → **Billing** (ou *Usage*). Se aparecer "Credits", é o plano por créditos: faça esta parte. Se aparecer "Build minutes" e "Bandwidth" sem créditos, é o plano antigo: **pule esta parte**, está tudo certo.

A solução: os dados passam a ser servidos de graça pelo **GitHub Pages**, e a Netlify só republica quando muda o site (HTML), não quando o robô muda só os dados.

1. No repositório: **Settings → Pages** → em *Build and deployment*, **Source: Deploy from a branch** → **Branch: main**, pasta **/(root)** → **Save**.
2. Espere 1 ou 2 minutos e abra `https://SEU-USUARIO.github.io/acoes-comunidade-invest/dados/indice.json`. Tem que aparecer o JSON.
3. No repositório, abra o arquivo `config.js` → lápis (Edit) → troque a última linha por:
   `window.CI_DADOS_URL = window.CI_DADOS_URL || 'https://SEU-USUARIO.github.io/acoes-comunidade-invest/dados/';`
   → **Commit changes**.
4. Abra o `netlify.toml` → lápis → apague o `#` do começo da linha que começa com `# ignore =` (deixe os dois espaços antes de `ignore`) → **Commit changes**.
5. Teste de novo o site da Netlify. Na Netlify, em **Deploys**, as próximas atualizações do robô aparecem como "Canceled" / "Skipped": é o esperado, não gasta crédito.

---

## Problemas comuns

- **A página abre mas fica "Carregando..." ou diz que não achou o ativo**: abra `.../dados/indice.json`. Se der "Page not found", os arquivos foram para uma subpasta (ver passo 2) ou a pasta `dados` não subiu.
- **Robô vermelho com "Permission denied" / "403" no passo de salvar**: faltou o passo 3 (Read and write permissions).
- **Robô vermelho baixando dados**: alguma fonte (B3, CVM, SEC, Yahoo) estava fora do ar. O robô mantém os dados de ontem daquele ativo; tente *Run workflow* de novo mais tarde. Se repetir, mande o erro para o Claude.
- **GitHub mandou e-mail dizendo que desativou o workflow** (acontece se o repositório ficar 60 dias sem atividade): aba Actions → Atualizar ações → *Enable workflow*.
- **Mudei algo e o site não mudou**: na Netlify, *Deploys → Trigger deploy → Deploy site*. E dê Ctrl+F5 no navegador.

## Depois, no site principal

Quando estiver aprovado, o sócio pode:

- usar o endereço da Netlify direto (ou um subdomínio, em *Domain management → Add a domain*, por exemplo `acoes.seusite.com.br`); ou
- copiar `index.html`, `acao.html` e `config.js` para o site principal e apontar o `config.js` para os dados (endereço da Netlify ou do GitHub Pages + `/dados/`). A leitura por outro site já está liberada (CORS).

Para crescer de 3 para todos os ativos, o caminho está no `TUTORIAL-CLAUDE.md`.
