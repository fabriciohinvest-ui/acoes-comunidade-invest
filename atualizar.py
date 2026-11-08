#!/usr/bin/env python3
"""Robo diario das paginas de acoes da Comunidade Invest.

Gera dados/<TICKER>.json com cotacao, indicadores, proventos e balancos, so com fontes publicas:
  - B3: cotacoes diarias (COTAHIST), proventos, desdobramentos/grupamentos, dados do BDR
  - CVM: balancos (DFP anual, ITR trimestral) e free float (FRE)
  - SEC (EUA): balancos de empresas americanas (BDRs)
  - Banco Central: dolar PTAX
  - Yahoo Finance: cotacao da acao original nos EUA (BDRs) e rendimentos antigos de FII
  - CVM (fundos imobiliarios): informe mensal (patrimonio, cotas, cotistas, carteira)

Uso:
  python atualizar.py              atualizacao do dia (o GitHub Actions roda isto todo dia)
  python atualizar.py --historico  refaz tudo do zero: cotacoes anuais da B3 desde 2009 e os DFP desde 2010
  python atualizar.py --so BBAS3,MXRF11   so esses ativos (para testar)
  python atualizar.py --limite 30         so os 30 primeiros da lista (para testar)
Precisa so de Python 3.9+, sem instalar nada.

A lista de ativos e a de cache/universo.json (feita pelo universo.py: todas as acoes e FIIs da B3 e os BDRs de
empresas americanas) mais as EMPRESAS abaixo, que valem por cima (nome e segmento escritos a mao).
Em escala, cada arquivo grande (cotacoes do dia, balancos da CVM, informe dos FIIs, comunicados) e baixado uma vez
para todos os ativos, e as respostas da B3, da SEC e do Yahoo ficam guardadas em cache/rede/ por algumas horas ou dias.
"""
import csv, io, json, os, re, sys, time, zipfile, base64, statistics, threading, urllib.request, datetime as dt
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import builtins

# varios ativos sao processados ao mesmo tempo: cada linha do log sai inteira e, durante um ativo, com o ticker na frente
_log_trava, _log_ativo = threading.Lock(), threading.local()


def print(*args, sep=' ', end='\n', **kw):
    texto = sep.join(str(a) for a in args)
    t = getattr(_log_ativo, 'ticker', None)
    if t and texto.strip() and not texto.lstrip().startswith(('ok ', 'ERRO', 'aviso', '==')):
        texto = f'  [{t}] {texto.strip()}'
    with _log_trava:
        builtins.print(texto, end=end, **kw)

AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(AQUI, 'cache')
SAIDA = os.path.join(AQUI, 'dados')
UA = 'ComunidadeInvest dados-publicos'
# A SEC pede um contato no User-Agent (sem ele, www.sec.gov responde 403). Vem da variavel CONTATO_SEC do workflow:
# um e-mail de contato do site, nunca o pessoal do dono.
CONTATO_SEC = os.environ.get('CONTATO_SEC', '').strip()
UA_SEC = f'ComunidadeInvest {CONTATO_SEC}' if CONTATO_SEC else UA
ANO_INICIO = 2009
TRABALHADORES = int(os.environ.get('TRABALHADORES', '8'))  # ativos montados ao mesmo tempo

EMPRESAS = [
    {'ticker': 'BBAS3', 'tipo': 'acao', 'nome': 'Banco do Brasil', 'razao': 'BCO BRASIL S.A.', 'cnpj': '00.000.000/0001-91', 'b3': 'BBAS',
     'pregao': 'BRASIL', 'isin': 'BRBBASACNOR3', 'setor': 'Financeiro', 'segmento': 'Bancos', 'banco': True},
    {'ticker': 'GOGL34', 'tipo': 'bdr', 'nome': 'Alphabet (Google)', 'razao': 'ALPHABET INC.', 'b3': 'GOGL', 'cik': '0001652044', 'us': 'GOOGL',
     'isin': 'BRGOGLBDR001', 'setor': 'Tecnologia', 'segmento': 'Serviços de internet'},
    {'ticker': 'MXRF11', 'tipo': 'fii', 'nome': 'Maxi Renda', 'cnpj': '97.521.225/0001-25', 'b3': 'MXRF', 'isin': 'BRMXRFCTF008',
     'setor': 'Fundo imobiliário', 'segmento': 'Híbrido', 'tipo_fundo': 'Fundo de papel (recebíveis)'},
    # mesmo setor dos tres acima, para o "Lado a lado com o setor"
    {'ticker': 'ITUB4', 'tipo': 'acao', 'nome': 'Itaú Unibanco', 'razao': 'ITAÚ UNIBANCO HOLDING S.A.', 'cnpj': '60.872.504/0001-23', 'b3': 'ITUB',
     'pregao': 'ITAUUNIBANCO', 'isin': 'BRITUBACNPR1', 'setor': 'Financeiro', 'segmento': 'Bancos', 'banco': True},
    {'ticker': 'BBDC4', 'tipo': 'acao', 'nome': 'Bradesco', 'razao': 'BANCO BRADESCO S.A.', 'cnpj': '60.746.948/0001-12', 'b3': 'BBDC',
     'pregao': 'BRADESCO', 'isin': 'BRBBDCACNPR8', 'setor': 'Financeiro', 'segmento': 'Bancos', 'banco': True},
    {'ticker': 'BRSR6', 'tipo': 'acao', 'nome': 'Banrisul', 'razao': 'BANCO DO ESTADO DO RIO GRANDE DO SUL S.A.', 'cnpj': '92.702.067/0001-96', 'b3': 'BRSR',
     'pregao': 'BANRISUL', 'isin': 'BRBRSRACNPB4', 'setor': 'Financeiro', 'segmento': 'Bancos', 'banco': True},
    {'ticker': 'MSFT34', 'tipo': 'bdr', 'nome': 'Microsoft', 'razao': 'MICROSOFT CORP.', 'b3': 'MSFT', 'cik': '0000789019', 'us': 'MSFT',
     'isin': 'BRMSFTBDR005', 'setor': 'Tecnologia', 'segmento': 'Software e nuvem'},
    {'ticker': 'AAPL34', 'tipo': 'bdr', 'nome': 'Apple', 'razao': 'APPLE INC.', 'b3': 'AAPL', 'cik': '0000320193', 'us': 'AAPL',
     'isin': 'BRAAPLBDR004', 'setor': 'Tecnologia', 'segmento': 'Equipamentos e software'},
    {'ticker': 'M1TA34', 'tipo': 'bdr', 'nome': 'Meta (Facebook)', 'razao': 'META PLATFORMS INC.', 'b3': 'M1TA', 'cik': '0001326801', 'us': 'META',
     'isin': 'BRM1TABDR009', 'setor': 'Tecnologia', 'segmento': 'Serviços de internet'},
    {'ticker': 'KNCR11', 'tipo': 'fii', 'nome': 'Kinea Rendimentos', 'cnpj': '16.706.958/0001-32', 'b3': 'KNCR', 'isin': 'BRKNCRCTF000',
     'setor': 'Fundo imobiliário', 'segmento': 'Papel', 'tipo_fundo': 'Fundo de papel (recebíveis)'},
    {'ticker': 'KNIP11', 'tipo': 'fii', 'nome': 'Kinea Índices de Preços', 'cnpj': '24.960.430/0001-13', 'b3': 'KNIP', 'isin': 'BRKNIPCTF001',
     'setor': 'Fundo imobiliário', 'segmento': 'Papel', 'tipo_fundo': 'Fundo de papel (recebíveis)'},
    {'ticker': 'CPTS11', 'tipo': 'fii', 'nome': 'Capitânia Securities II', 'cnpj': '18.979.895/0001-13', 'b3': 'CPTS', 'isin': 'BRCPTSCTF004',
     'setor': 'Fundo imobiliário', 'segmento': 'Papel', 'tipo_fundo': 'Fundo de papel (recebíveis)'},
]


# ---------------------------------------------------------------- rede
def baixar(url, tentativas=4, timeout=300, headers=None):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=headers or {'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            erro = e
        except Exception as e:
            erro = e
        print('   tentando de novo:', erro)
        time.sleep(3 * (i + 1))
    raise erro


def gravar_atomico(p, texto):
    """grava sem deixar arquivo pela metade (varios ativos rodam ao mesmo tempo)"""
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f'{p}.{threading.get_ident()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(texto)
    os.replace(tmp, p)


def em_cache(rel, horas, func):
    """Resposta de uma fonte guardada em cache/rede/<rel>.json por <horas>. Se a fonte falhar, usa a guardada,
    mesmo velha (falha nao apaga dado). Sem copia guardada, o erro sobe."""
    p = os.path.join(CACHE, 'rede', rel + '.json')
    guardado = None
    if os.path.exists(p):
        try:
            guardado = json.load(open(p, encoding='utf-8'))
            if time.time() - guardado['_em'] < horas * 3600:
                return guardado['v']
        except (ValueError, KeyError, TypeError):
            guardado = None
    try:
        v = func()
    except Exception as ex:
        if guardado is not None:
            print(f'   {rel}: fonte indisponivel ({ex!r}), usando a copia guardada')
            return guardado['v']
        raise
    gravar_atomico(p, json.dumps({'_em': time.time(), 'v': v}, ensure_ascii=False, separators=(',', ':')))
    return v


_memo, _memo_travas, _memo_trava = {}, {}, threading.Lock()


def memo(chave, func):
    """calcula uma vez por rodada (dolar, CDI, IPCA, zips da CVM...), mesmo com varios ativos ao mesmo tempo"""
    # uma trava por chave: um calculo guardado pode chamar outro (ptax -> sgs, indice do FRE -> zip do FRE)
    with _memo_trava:
        trava = _memo_travas.setdefault(chave, threading.Lock())
    with trava:
        if chave not in _memo:
            _memo[chave] = func()
        return _memo[chave]


def chave_arquivo(params):
    return re.sub(r'[^\w.-]+', '_', '_'.join(str(v) for v in params.values() if v not in ('pt-br',)))[:120]


def b3api(metodo, params, horas=None):
    q = base64.b64encode(json.dumps(params).encode()).decode()
    busca = lambda: json.loads(baixar(f'https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/{metodo}/{q}', timeout=60))
    return em_cache(f'b3/{metodo}/{chave_arquivo(params)}', horas, busca) if horas else busca()


num_br = lambda s: float(str(s).replace('.', '').replace(',', '.')) if str(s).strip() not in ('', 'None') else None
data_br = lambda s: dt.datetime.strptime(s, '%d/%m/%Y').date().isoformat() if s else None


# ---------------------------------------------------------------- cotacoes B3 (COTAHIST)
def ler_cotahist(linhas, tickers, destino):
    """linhas: texto inteiro ou um arquivo aberto (o anual tem centenas de MB: le linha a linha)"""
    for l in (linhas.splitlines() if isinstance(linhas, str) else linhas):
        if not l.startswith('01'):
            continue
        t = l[12:24].strip()
        if t in tickers and l[24:27] == '010':
            d = l[2:10]
            p = lambda a, b: int(l[a:b]) / 100
            destino[t][f'{d[:4]}-{d[4:6]}-{d[6:]}'] = [p(56, 69), p(69, 82), p(82, 95), p(108, 121), int(l[170:188]) / 100]


def cot_arquivo(t):
    return os.path.join(CACHE, 'cotacoes', t + '.csv')


def cot_ler(t):
    out = {}
    if os.path.exists(cot_arquivo(t)):
        for r in csv.reader(open(cot_arquivo(t))):
            out[r[0]] = [float(x) for x in r[1:]]
    return out


def cot_gravar(t, d):
    os.makedirs(os.path.dirname(cot_arquivo(t)), exist_ok=True)
    with open(cot_arquivo(t), 'w', newline='') as f:
        w = csv.writer(f)
        for k in sorted(d):
            w.writerow([k] + d[k])


def cot_ultimo_dia(t):
    """ultimo pregao guardado de um ativo ('' se nao ha nada)"""
    try:
        with open(cot_arquivo(t), 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400))
            linhas = f.read().decode().strip().splitlines()
        return linhas[-1].split(',')[0] if linhas else ''
    except OSError:
        return ''


def cot_acrescentar(novas, ultimos):
    """acrescenta ao fim de cada cache/cotacoes/<T>.csv os pregoes depois do ultimo guardado"""
    for t, dias in novas.items():
        linhas = [[d] + v for d, v in sorted(dias.items()) if d > ultimos.get(t, '')]
        if not linhas:
            continue
        os.makedirs(os.path.dirname(cot_arquivo(t)), exist_ok=True)
        with open(cot_arquivo(t), 'a', newline='') as f:
            csv.writer(f).writerows(linhas)
        ultimos[t] = linhas[-1][0]


def cotahist(url, tickers, timeout=900, tentativas=4):
    z = baixar(url, tentativas=tentativas, timeout=timeout)
    if not z or z[:2] != b'PK':
        return None
    dados = defaultdict(dict)
    with zipfile.ZipFile(io.BytesIO(z)) as zf, zf.open(zf.namelist()[0]) as f:
        ler_cotahist(io.TextIOWrapper(f, encoding='latin-1'), tickers, dados)
    return dados


def atualizar_cotacoes_todas(tickers, historico=False):
    """Cotacoes de todos os ativos numa passada so: cada arquivo da B3 (o do dia ou o do ano) traz todos os ativos.
    Ativo novo (sem nada guardado) ganha o historico desde 2009 lendo os arquivos anuais uma vez para todos os novos."""
    tickers = set(tickers)
    hoje = dt.date.today()
    if historico:
        for t in tickers:
            if os.path.exists(cot_arquivo(t)):
                os.remove(cot_arquivo(t))
    ultimos = {t: cot_ultimo_dia(t) for t in tickers}
    novos = {t for t in tickers if not ultimos[t]}
    if novos:
        print(f' B3 cotacoes desde {ANO_INICIO} para {len(novos)} ativo(s) novo(s)')
        for ano in range(ANO_INICIO, hoje.year + 1):
            dados = cotahist(f'https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP', novos)
            if dados:
                cot_acrescentar(dados, ultimos)
                print('  ano', ano, 'ok')
    # dias que faltam: desde o ultimo pregao lido (cache/cotacoes/_ultimo.txt) ou, se um ativo novo parou antes
    # (o arquivo do ano pode estar uns dias atrasado), desde o ultimo dia dele
    marca = os.path.join(CACHE, 'cotacoes', '_ultimo.txt')
    ult_geral = open(marca).read().strip() if os.path.exists(marca) else max((u for u in ultimos.values() if u), default='')
    dos_novos = [ultimos[t] for t in novos if ultimos[t]]
    inicio = min([ult_geral] + dos_novos) if ult_geral else f'{hoje.year}-01-01'
    d = dt.date.fromisoformat(inicio) + dt.timedelta(days=1)
    ultimo_lido = ult_geral
    if (hoje - d).days > 40:  # muito atrasado: usa o arquivo do ano
        dados = cotahist(f'https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{hoje.year}.ZIP', tickers)
        if dados:
            cot_acrescentar(dados, ultimos)
            ultimo_lido = max((max(v) for v in dados.values() if v), default=ultimo_lido)
    else:
        while d <= hoje:
            if d.weekday() < 5:
                dados = cotahist(f'https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{d:%d%m%Y}.ZIP', tickers, timeout=120, tentativas=2)
                if dados is not None:
                    cot_acrescentar(dados, ultimos)
                    ultimo_lido = max(ultimo_lido or '', d.isoformat())
                    print(' B3 cotacoes', d)
            d += dt.timedelta(days=1)
    if ultimo_lido:
        os.makedirs(os.path.dirname(marca), exist_ok=True)
        open(marca, 'w').write(ultimo_lido)


# ---------------------------------------------------------------- CVM
CVM = 'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC'
DEMS = ['DRE', 'BPA', 'BPP', 'DFC_MI', 'composicao_capital']


def cvm_baixar(doc, ano, cnpjs):
    """Baixa o zip do ano (DFP ou ITR) e guarda so as linhas das empresas acompanhadas, numa leitura so do arquivo.
    Guarda o consolidado e o individual (_ind): empresa que so entrega o individual usa ele (veja cvm_ler)."""
    z = baixar(f'{CVM}/{doc.upper()}/DADOS/{doc}_cia_aberta_{ano}.zip')
    if not z:
        return
    alvo = set(cnpjs)
    for c in alvo:
        os.makedirs(os.path.join(CACHE, 'cvm', re.sub(r'\D', '', c)), exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(z)) as zf:
        for nome in zf.namelist():
            dem = next((x for x in DEMS if f'_{x}_' in nome), None)
            if not dem:
                continue
            ind = '_ind_' in nome
            txt = zf.read(nome).decode('latin-1').splitlines()
            por = defaultdict(list)
            for l in txt[1:]:
                c = l.split(';', 1)[0]
                if c in alvo:
                    por[c].append(l)
            for c in alvo:
                arq = os.path.join(CACHE, 'cvm', re.sub(r'\D', '', c), f'{doc}_{ano}_{dem}{"_ind" if ind else ""}.csv')
                if por.get(c):
                    open(arq, 'w', encoding='utf-8').write('\n'.join([txt[0]] + por[c]))
                elif os.path.exists(arq):
                    os.remove(arq)  # a empresa saiu desse arquivo (reapresentacao)


def fre_zip(ano):
    """Formulario de Referencia da CVM (um zip por ano, para todas as companhias)"""
    def busca():
        z = baixar(f'{CVM}/FRE/DADOS/fre_cia_aberta_{ano}.zip')
        return zipfile.ZipFile(io.BytesIO(z)) if z else None
    return memo(('fre', ano), busca)


def fre_csv(ano, parte, cnpj):
    """linhas de uma parte do FRE para uma companhia (o arquivo e lido uma vez e separado por CNPJ)"""
    def indexar():
        zf = fre_zip(ano)
        idx = defaultdict(list)
        if zf:
            for r in csv.DictReader(io.TextIOWrapper(zf.open(f'fre_cia_aberta_{parte}_{ano}.csv'), encoding='latin-1'), delimiter=';'):
                idx[r['CNPJ_Companhia']].append(r)
        return idx
    return memo(('fre_idx', ano, parte), indexar).get(cnpj, [])


def fre_free_float(cnpjs):
    ano = dt.date.today().year
    out = {}
    for a in (ano, ano - 1):
        for c in cnpjs:
            for r in fre_csv(a, 'distribuicao_capital', c):
                if c not in out or (r['Data_Referencia'], int(r['Versao'] or 0)) >= (out[c]['data'], out[c]['_v']):
                    q = lambda k: int(r.get(k) or 0)
                    out[c] = {'data': r['Data_Referencia'], '_v': int(r['Versao'] or 0), 'free_float': float(r['Percentual_Total_Acoes_Circulacao']),
                              'acionistas': q('Quantidade_Acionistas_PF') + q('Quantidade_Acionistas_PJ') + q('Quantidade_Acionistas_Investidores_Institucionais'),
                              'pf': q('Quantidade_Acionistas_PF'), 'pj': q('Quantidade_Acionistas_PJ'), 'inst': q('Quantidade_Acionistas_Investidores_Institucionais')}
        if len(out) == len(cnpjs):
            break
    return out


def donos(cnpj):
    """maiores acionistas (5% ou mais, controladores, acoes em tesouraria e "outros") da ultima versao do FRE"""
    ano = dt.date.today().year
    for a in (ano, ano - 1):
        rs = [r for r in fre_csv(a, 'posicao_acionaria', cnpj) if not r.get('ID_Acionista_Relacionado')]
        if not rs:
            continue
        ult = max((r['Data_Referencia'], int(r['Versao'] or 0)) for r in rs)
        rs = [r for r in rs if (r['Data_Referencia'], int(r['Versao'] or 0)) == ult]
        f = lambda r, k: float(r.get(k) or 0)
        lista = [{'nome': r['Acionista'].strip(), 'pct': f(r, 'Percentual_Total_Acoes_Circulacao'), 'on': f(r, 'Percentual_Acao_Ordinaria_Circulacao'),
                  'pn': f(r, 'Percentual_Acao_Preferencial_Circulacao'), 'controlador': r.get('Acionista_Controlador') == 'S',
                  'pessoa': r.get('Tipo_Pessoa_Acionista') or None} for r in rs]
        lista = [x for x in lista if x['pct'] > 0]
        lista.sort(key=lambda x: (x['nome'].lower() == 'outros', x['nome'].lower().startswith('a') and 'tesouraria' in x['nome'].lower(), -x['pct']))
        return {'data': ult[0], 'lista': lista}
    return None


def cvm_ler(cnpj):
    """dict: (doc, dt_refer, ordem, dt_ini, dt_fim) -> {conta: (descricao, valor)}"""
    pasta = os.path.join(CACHE, 'cvm', cnpj.replace('.', '').replace('/', '').replace('-', ''))
    R = defaultdict(dict)
    cap = {}
    nomes = sorted(os.listdir(pasta))
    # consolidado quando a empresa entregou o consolidado naquele documento e ano; senao, o individual
    com_con = {tuple(n.split('_')[:2]) for n in nomes if n.endswith('_DRE.csv')}
    usar = [n for n in nomes if not n.endswith('_ind.csv') or tuple(n.split('_')[:2]) not in com_con]
    for nome in usar:
        doc = nome.split('_')[0]
        for r in csv.DictReader(open(os.path.join(pasta, nome), encoding='utf-8'), delimiter=';'):
            if 'composicao' in nome:
                tot = int(r['QT_ACAO_TOTAL_CAP_INTEGR'] or 0)
                cap[r['DT_REFER']] = tot
                continue
            v = float(r['VL_CONTA']) * (1000 if r['ESCALA_MOEDA'] == 'MIL' else 1)
            ordem = 'U' if r['ORDEM_EXERC'].endswith('LTIMO') and not r['ORDEM_EXERC'].startswith('PEN') else 'P'
            R[(doc, r['DT_REFER'], ordem, r.get('DT_INI_EXERC', ''), r['DT_FIM_EXERC'])][r['CD_CONTA']] = (r['DS_CONTA'], v)
    return R, cap


def conta(contas, codigo=None, desc=None, nivel=None):
    """valor por codigo exato, ou pela primeira conta cuja descricao contem desc (no nivel dado)"""
    if codigo and codigo in contas:
        return contas[codigo][1]
    if desc:
        for c, (d, v) in sorted(contas.items()):
            if re.search(desc, d, re.I) and (nivel is None or c.count('.') == nivel):
                return v
    return None


def fin_brasil(e):
    """Demonstracoes anuais + ultimos 12 meses de uma empresa da CVM (consolidado)."""
    R, cap = cvm_ler(e['cnpj'])

    def dre(cs):
        return {'receita': conta(cs, '3.01'), 'custos': conta(cs, '3.02'), 'lucro_bruto': conta(cs, '3.03'),
                'ebit': conta(cs, '3.05') if e.get('banco') else conta(cs, '3.05'),
                'imposto': conta(cs, '3.06') if e.get('banco') else conta(cs, '3.08'),
                'lucro_liquido': conta(cs, desc=r'^lucro.*consolidado do per[íi]odo', nivel=1) or conta(cs, '3.11'),
                'lucro_ctrl': conta(cs, desc=r'atribu.*(controlador|controladora)(?!.*n[ãa]o)', nivel=2) or conta(cs, '3.11')}

    def bal(a, p):
        pl = conta(p, desc=r'^patrim[ôo]nio l[íi]quido', nivel=1)
        nc = conta(p, desc=r'n[ãa]o controlad', nivel=2) or 0
        disp = (conta(a, '1.01.01') or 0) + (0 if e.get('banco') else (conta(a, '1.01.02') or 0))
        if e.get('banco'):
            disp = (conta(a, '1.01.01') or 0) + (conta(a, desc=r'aplica[çc][õo]es interfinanceiras de liquidez|aplica[çc][õo]es de liquidez', nivel=2) or 0)
        div = None
        if not e.get('banco'):
            div = sum(v for c, (d, v) in p.items() if c.count('.') == 2 and re.search(r'empr[ée]stimos e financiamentos', d, re.I))
        at, pt = conta(a, '1'), conta(p, '2')
        if a.get('1.01') and re.search('circulante', a['1.01'][0], re.I):
            ac, pc, anc, pnc = conta(a, '1.01'), conta(p, '2.01'), conta(a, '1.02'), conta(p, '2.02')
        else:  # balanco de banco (sem circulante): ativos e passivos financeiros
            ac, pc = conta(a, '1.02'), conta(p, '2.02')
            anc = at - ac if at and ac else None
            pnc = pt - (pl or 0) - pc if pt and pc else None
        return {'ativo_total': at, 'ativo_circ': ac, 'ativo_nc': anc,
                'passivo_total': pt, 'passivo_circ': pc, 'passivo_nc': pnc,
                'pl_consolidado': pl, 'pl': (pl or 0) - nc, 'disponibilidade': disp, 'divida_bruta': div,
                'divida_liquida': (div - disp) if div is not None else -disp}

    anual = {}
    for (doc, ref, ordem, ini, fim), cs in R.items():
        if doc != 'dfp' or not ref.endswith('12-31'):
            continue
        ano = int(fim[:4])
        if ordem == 'P' and ano in anual:
            continue  # prefere o numero do proprio ano; o penultimo so preenche anos sem DFP proprio
        if '3.01' in cs:
            anual.setdefault(ano, {}).update(dre(cs))
    # balancos: pareia BPA e BPP do mesmo documento
    bpa, bpp = {}, {}
    for (doc, ref, ordem, ini, fim), cs in R.items():
        if ini == '':
            k = (doc, ref, ordem, fim)
            if '1' in cs:
                bpa[k] = cs
            if '2' in cs:
                bpp[k] = cs
    balancos = {}
    for k in bpa:
        if k in bpp:
            balancos[(k[0], k[1], k[2], k[3])] = bal(bpa[k], bpp[k])
    for (doc, ref, ordem, fim), b in balancos.items():
        if doc == 'dfp' and fim.endswith('12-31'):
            ano = int(fim[:4])
            if ano in anual and ('ativo_total' not in anual[ano] or ordem == 'U'):
                anual[ano].update(b)
    for ano, a in anual.items():
        a['acoes'] = cap.get(f'{ano}-12-31')

    # ultimos 12 meses = ultimo ano + acumulado do ano atual - mesmo periodo do ano anterior
    itr = sorted({ref for (doc, ref, o, i, f) in R if doc == 'itr'})
    ult_ano = max(anual)
    ttm = dict(anual[ult_ano]); ttm_ref = f'{ult_ano}-12-31'
    if itr and itr[-1] > ttm_ref:
        ref = itr[-1]
        ref_ant = f'{int(ref[:4]) - 1}{ref[4:]}'
        ytd = next((cs for (doc, r, o, i, f), cs in R.items() if doc == 'itr' and r == ref and o == 'U' and i[5:] == '01-01' and '3.01' in cs), None)
        ytd_ant = next((cs for (doc, r, o, i, f), cs in R.items() if doc == 'itr' and r == ref and o == 'P' and i[5:] == '01-01' and '3.01' in cs), None)
        if ytd and ytd_ant and int(ref[:4]) - 1 == ult_ano:
            a, b = dre(ytd), dre(ytd_ant)
            for k in a:
                if a[k] is not None and b[k] is not None and ttm.get(k) is not None:
                    ttm[k] = ttm[k] + a[k] - b[k]
            bk = balancos.get(('itr', ref, 'U', ref))
            if bk:
                ttm.update(bk)
            ttm['acoes'] = cap.get(ref) or ttm.get('acoes')
            ttm_ref = ref
    # trimestres (para o grafico de resultados trimestrais)
    trim = {}
    for (doc, r, o, i, f), cs in R.items():
        if o == 'U' and '3.01' in cs and i and f:
            di, df = dt.date.fromisoformat(i), dt.date.fromisoformat(f)
            if 80 < (df - di).days < 100:
                trim[f] = dre(cs)
    for ano, a in anual.items():  # 4o trimestre = ano - 9 meses
        nove = next((cs for (doc, r, o, i, f), cs in R.items() if doc == 'itr' and o == 'U' and r == f'{ano}-09-30' and i == f'{ano}-01-01' and '3.01' in cs), None)
        if nove:
            n = dre(nove)
            trim[f'{ano}-12-31'] = {k: (a[k] - n[k]) if a.get(k) is not None and n.get(k) is not None else None for k in n}
    return anual, ttm, ttm_ref, trim, max(cap) if cap else None, cap


# ---------------------------------------------------------------- SEC (EUA)
_sec_vez = threading.Semaphore(4)  # a SEC aceita ate 10 pedidos por segundo


def sec_baixar(caminho, timeout=120):
    with _sec_vez:
        try:
            return json.loads(baixar(f'https://data.sec.gov/{caminho}', headers={'User-Agent': UA_SEC}, timeout=timeout))
        finally:
            time.sleep(0.15)


def sec_json(caminho, horas):
    """data.sec.gov guardado por <horas> (submissions: documentos entregues, setor SIC)"""
    return em_cache('sec/' + caminho.replace('/', '_').replace('.json', ''), horas, lambda: sec_baixar(caminho))


def sec_fatos(cik):
    return sec_baixar(f'api/xbrl/companyfacts/CIK{cik}.json')['facts']['us-gaap']


def fin_eua_guardado(cik):
    """fin_eua so e recalculado quando a empresa entrega um 10-K ou 10-Q novo (o companyfacts tem de 5 a 20 MB).
    Fica guardado o resultado ja calculado, nao o arquivo da SEC."""
    sub = sec_json(f'submissions/CIK{cik}.json', 72)
    rec = sub['filings']['recent']
    ult = max((d for f, d in zip(rec['form'], rec['filingDate']) if f in ('10-K', '10-Q', '10-K/A', '10-Q/A')), default='')
    pasta = os.path.join(CACHE, 'rede', 'sec')
    arq = os.path.join(pasta, f'fin_{cik}_{ult}_v3.json')  # v3: ano fiscal fora de dezembro, receita de banco, campo mais atualizado
    if os.path.exists(arq):
        a, t, r, tr = json.load(open(arq, encoding='utf-8'))
        return {int(k): v for k, v in a.items()}, t, r, tr
    antigos = sorted(n for n in os.listdir(pasta) if n.startswith(f'fin_{cik}_') and n != os.path.basename(arq)) if os.path.isdir(pasta) else []
    try:
        a, t, r, tr = fin_eua(cik)
    except Exception as ex:
        if not antigos:
            raise
        print('  SEC indisponivel, usando o ultimo balanco calculado:', repr(ex))
        a, t, r, tr = json.load(open(os.path.join(pasta, antigos[-1]), encoding='utf-8'))
        return {int(k): v for k, v in a.items()}, t, r, tr
    gravar_atomico(arq, json.dumps([{str(k): v for k, v in a.items()}, t, r, tr], ensure_ascii=False, separators=(',', ':')))
    for n in antigos:
        os.remove(os.path.join(pasta, n))
    return a, t, r, tr


def fin_eua(cik):
    F = sec_fatos(cik)

    def serie(tags, duracao, primeiro=False, inicios=None):
        """duracao: 'ano', 'trim', 'ytd' ou 'saldo'. Retorna {fim: valor} (ultimo arquivo vence;
        primeiro=True: vale o arquivo original, usado no n. de acoes para nao contar desdobramento duas vezes).
        ytd = do inicio do ano fiscal ate o fim do trimestre (inicios: datas em que comeca um ano fiscal da empresa)"""
        final = {}
        for tag in tags:  # o ultimo campo da lista vence; os anteriores so completam datas que faltam
            out = {}
            for un in F.get(tag, {}).get('units', {}).values():
                for x in un:
                    if x['form'] not in ('10-K', '10-Q', '10-K/A', '10-Q/A'):
                        continue
                    if duracao == 'saldo':
                        if 'start' in x:
                            continue
                    else:
                        if 'start' not in x:
                            continue
                        dias = (dt.date.fromisoformat(x['end']) - dt.date.fromisoformat(x['start'])).days
                        if duracao == 'ano' and not 350 < dias < 380:
                            continue
                        if duracao == 'trim' and not 80 < dias < 100:
                            continue
                        if duracao == 'ytd' and not ((x['start'] in inicios if inicios else x['start'][5:] == '01-01') and dias < 300):
                            continue
                    k = x['end']
                    if k not in out or (x['filed'] < out[k][1] if primeiro else x['filed'] >= out[k][1]):
                        out[k] = (x['val'], x['filed'])
            final.update({k: v for k, (v, f) in out.items()})
        return final

    T = {
        'receita': ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenuesNetOfInterestExpense'],
        'custos': ['CostOfRevenue'], 'ebit': ['OperatingIncomeLoss'], 'lucro_liquido': ['ProfitLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic', 'NetIncomeLoss'],
        'imposto': ['IncomeTaxExpenseBenefit'], 'depreciacao': ['Depreciation', 'DepreciationAndAmortization'],
        'dividendos_pagos': ['PaymentsOfDividends', 'PaymentsOfDividendsCommonStock'],
        'dps': ['CommonStockDividendsPerShareDeclared'], 'lpa': ['EarningsPerShareDiluted'],
    }
    S = {'ativo_total': ['Assets'], 'ativo_circ': ['AssetsCurrent'], 'passivo_total': ['Liabilities'], 'passivo_circ': ['LiabilitiesCurrent'],
         'pl': ['StockholdersEquity'], 'disponibilidade': ['CashCashEquivalentsAndShortTermInvestments'],
         'div_lp': ['LongTermDebtNoncurrent', 'LongTermDebt'], 'div_cp': ['LongTermDebtCurrent'], 'cp': ['CommercialPaper'],
         'acoes': ['CommonStockSharesOutstanding']}
    # cada item vem do campo mais atualizado da empresa (os outros so completam anos que faltam); empate: o ultimo da lista
    formas = ('10-K', '10-Q', '10-K/A', '10-Q/A')
    ultimo_fim = lambda tag: max((x['end'] for un in F.get(tag, {}).get('units', {}).values() for x in un
                                  if 'start' in x and x['form'] in formas), default='')
    for k, tags in T.items():
        principal = max(reversed(tags), key=ultimo_fim)
        T[k] = [t for t in tags if t != principal] + [principal]
    anoS = {k: serie(v, 'ano') for k, v in T.items()}
    # ano fiscal: Apple fecha em setembro, Microsoft em junho, Nvidia em janeiro (semanas de 52/53: tolerancia de 3 dias)
    inicios = {(dt.date.fromisoformat(f) + dt.timedelta(days=1 + d)).isoformat() for f in anoS['receita'] for d in range(-3, 4)}
    ytdS = {k: serie(v, 'ytd', inicios=inicios) for k, v in T.items()}
    triS = {k: serie(v, 'trim') for k, v in T.items()}
    salS = {k: serie(v, 'saldo', primeiro=(k == 'acoes')) for k, v in S.items()}
    # empresa com mais de uma classe de acao (ex.: Meta) nao informa CommonStockSharesOutstanding:
    # usa a media ponderada de acoes do periodo (a do trimestre vale mais que a do ano)
    media = ['WeightedAverageNumberOfSharesOutstandingBasic']
    medS = {**serie(media, 'ano', primeiro=True), **serie(media, 'trim', primeiro=True)}

    def balanco(fim):
        b = {k: salS[k].get(fim) for k in S}
        if not b['acoes']:
            b['acoes'] = medS.get(fim)
        div = (b['div_lp'] or 0) + (b['div_cp'] or 0) + (b['cp'] or 0)
        out = {k: b[k] for k in ('ativo_total', 'ativo_circ', 'passivo_total', 'passivo_circ', 'pl', 'disponibilidade', 'acoes')}
        if out['ativo_total'] and out['ativo_circ']:
            out['ativo_nc'] = out['ativo_total'] - out['ativo_circ']
        if out['passivo_total'] and out['passivo_circ']:
            out['passivo_nc'] = out['passivo_total'] - out['passivo_circ']
        out['pl_consolidado'] = out['pl']
        if out['passivo_total'] is not None and out['pl'] is not None:
            out['passivo_total'] = out['passivo_total'] + out['pl']  # passivo total + patrimonio (= ativo total), como no balanco brasileiro
        out['divida_bruta'] = div
        out['divida_liquida'] = div - (out['disponibilidade'] or 0)
        return out

    anual = {}
    for fim in sorted(anoS['receita']):
        ano = int(fim[:4])
        a = {k: anoS[k].get(fim) for k in T}
        a['fim'] = fim  # fechamento do ano fiscal
        a['lucro_bruto'] = a['receita'] - a['custos'] if a['receita'] and a['custos'] else None
        a['custo_pos'] = a['custos']
        a['custos'] = -a['custos'] if a['custos'] else None
        a['lucro_ctrl'] = a['lucro_liquido']
        a['ebitda'] = a['ebit'] + a['depreciacao'] if a['ebit'] and a['depreciacao'] else None
        a.update(balanco(fim))
        anual[ano] = a
    ult = max(anual)
    ttm = dict(anual[ult]); ttm_ref = anual[ult]['fim']
    ytd_ult = max(ytdS['receita']) if ytdS['receita'] else None
    ant = None
    if ytd_ult and ytd_ult > ttm_ref:  # mesmo periodo do ano fiscal anterior (52/53 semanas: ate 7 dias de diferenca)
        alvo = dt.date.fromisoformat(ytd_ult) - dt.timedelta(days=365)
        ant = min(ytdS['receita'], key=lambda k: abs((dt.date.fromisoformat(k) - alvo).days))
        if abs((dt.date.fromisoformat(ant) - alvo).days) > 7:
            ant = None
    if ant:
        ttm['custos'] = anual[ult].get('custo_pos')  # positivo durante a conta (no anual ja esta com sinal trocado)
        for k in T:
            a, b = ytdS[k].get(ytd_ult), ytdS[k].get(ant)
            base = anual[ult].get('custo_pos') if k == 'custos' else anual[ult].get(k)
            if a is not None and b is not None and base is not None:
                ttm[k] = base + a - b
        # Q1: o "ytd" do 1o tri e o proprio tri
        ttm['lucro_bruto'] = ttm['receita'] - ttm['custos'] if ttm['custos'] else None
        ttm['custos'] = -ttm['custos'] if ttm['custos'] else None
        ttm['lucro_ctrl'] = ttm['lucro_liquido']
        ttm['ebitda'] = ttm['ebit'] + ttm['depreciacao'] if ttm.get('ebit') is not None and ttm.get('depreciacao') else None
        ttm.update(balanco(ytd_ult))
        ttm_ref = ytd_ult
    trim = {}
    for fim in triS['receita']:
        trim[fim] = {'receita': triS['receita'].get(fim), 'lucro_liquido': triS['lucro_liquido'].get(fim), 'lucro_ctrl': triS['lucro_liquido'].get(fim)}
    for ano, a in anual.items():  # 4o trimestre fiscal = ano fiscal - 9 meses
        f = dt.date.fromisoformat(a['fim'])
        nove = next((k for k in ytdS['receita'] if 80 < (f - dt.date.fromisoformat(k)).days < 100), None)
        if a['fim'] not in trim and nove:
            ll, ll9 = a.get('lucro_liquido'), ytdS['lucro_liquido'].get(nove)
            q4 = ll - ll9 if ll is not None and ll9 is not None else None
            trim[a['fim']] = {'receita': a['receita'] - ytdS['receita'][nove], 'lucro_liquido': q4, 'lucro_ctrl': q4}
    return anual, ttm, ttm_ref, trim


# ---------------------------------------------------------------- outros
def ptax():
    """dolar PTAX venda diario desde 2009 (SGS 1): baixado uma vez por rodada, para todos os BDRs"""
    return memo('ptax', lambda: sgs(1, ANO_INICIO))


_yahoo_vez = threading.Semaphore(4)


def yahoo_baixar(sym, inicio):
    with _yahoo_vez:
        raw = baixar(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={inicio}&period2={int(time.time())}&interval=1d&events=div%7Csplit',
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
    d = json.loads(raw)['chart']['result'][0]
    q = d['indicators']['quote'][0]
    precos = {}
    for t, c in zip(d.get('timestamp') or [], q.get('close') or []):
        if c is not None:
            precos[dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()] = round(c, 4)
    ev = d.get('events', {})
    divs = sorted([dt.datetime.fromtimestamp(x['date'], dt.timezone.utc).date().isoformat(), x['amount']] for x in ev.get('dividends', {}).values())
    spl = sorted([dt.datetime.fromtimestamp(x['date'], dt.timezone.utc).date().isoformat(), x['numerator'] / x['denominator']] for x in ev.get('splits', {}).values())
    return {'precos': precos, 'divs': divs, 'spl': spl}


def yahoo(sym, diario=True):
    """Cotacao, dividendos e desdobramentos desde 2009. O historico inteiro fica guardado por uma semana; com diario=True,
    os ultimos 10 dias sao buscados todo dia e entram por cima (a cotacao de hoje do papel nos EUA)."""
    h = em_cache(f'yahoo/{sym}', 24 * 7, lambda: yahoo_baixar(sym, 1230768000))
    precos, divs, spl = dict(h['precos']), {d: v for d, v in h['divs']}, {d: k for d, k in h['spl']}
    if diario:
        r = em_cache(f'yahoo/{sym}_dias', 20, lambda: yahoo_baixar(sym, int(time.time()) - 10 * 86400))
        precos.update(r['precos'])
        divs.update({d: v for d, v in r['divs']})
        spl.update({d: k for d, k in r['spl']})
    return precos, sorted(divs.items()), sorted(spl.items())


EVENTOS_PRECO = ('DESDOBRAMENTO', 'BONIFICACAO', 'GRUPAMENTO')


def validar_eventos(fat, cot):
    """Junta os eventos do mesmo dia e so aceita os que aparecem no preco. A B3 lista alguns que nao mexeram
    na cotacao (ex.: um grupamento de 100 para 1 do Itau em 31/10/2011, sem salto nenhum no preco)."""
    por = {}
    for d, k in fat:
        por[d] = por.get(d, 1) * k
    dias = sorted(cot)
    out = []
    for d, k in sorted(por.items(), reverse=True):
        if abs(k - 1) < 1e-9:
            continue
        antes = [x for x in dias if x <= d]
        depois = [x for x in dias if x > d]
        if not antes or not depois or abs(k - 1) < 0.35:  # fora do historico de precos, ou bonificacao pequena: mantem
            out.append((d, k))
            continue
        r = cot[antes[-1]][3] / cot[depois[0]][3]
        if abs(__import__('math').log(r / k)) < __import__('math').log(1.6):
            out.append((d, k))
        else:
            print('   evento ignorado (o preco nao mudou):', d, k, 'antes/depois', round(r, 3))
    return out


def eventos_b3(e, cot=None):
    """desdobramentos/grupamentos/bonificacoes + proventos da B3. O complemento (proventos dos ultimos 12 meses) e
    buscado todo dia; o historico completo de proventos, uma vez por semana; o detalhe da empresa, uma vez por mes."""
    sup = b3api('GetListedSupplementCompany', {'issuingCompany': e['b3'], 'language': 'pt-br'}, horas=20)[0]
    fat = []
    for s in sup.get('stockDividends', []):
        if s['isinCode'] != e['isin'] or not s.get('lastDatePrior') or s['label'] not in EVENTOS_PRECO:
            continue  # "CIS RED CAP" (cisao com reducao de capital) nao e desdobramento
        f = num_br(s['factor'])
        k = f if s['label'] == 'GRUPAMENTO' else 1 + f / 100
        fat.append((data_br(s['lastDatePrior']), k))
    fat = sorted(set(fat), reverse=True)  # a B3 repete linhas
    if cot:
        fat = validar_eventos(fat, cot)
    pagto = {}
    for c in sup.get('cashDividends', []):
        if c['isinCode'] == e['isin']:
            pagto[(data_br(c['lastDatePrior']), round(num_br(c['rate']), 8))] = {'pagamento': data_br(c['paymentDate']), 'ref': c.get('relatedTo')}
    prov = []
    TIPOS = {'JRS CAP PROPRIO': 'JSCP', 'DIVIDENDO': 'Dividendos', 'RENDIMENTO': 'Rend. Trib.'}
    if e.get('pregao'):
        def historico_proventos():
            res, p = [], 1
            while True:
                d = b3api('GetListedCashDividends', {'language': 'pt-br', 'pageNumber': p, 'pageSize': 120, 'tradingName': e['pregao']})
                res += d['results']
                if p >= d['page']['totalPages']:
                    return res
                p += 1
        for r in em_cache(f'b3/GetListedCashDividends/{chave_arquivo({"p": e["pregao"]})}', 24 * 7, historico_proventos):
            tipo_ok = r['typeStock'] == {'3': 'ON', '5': 'PNA', '6': 'PNB'}.get(e['ticker'][-1], 'PN')
            if not tipo_ok:
                continue
            v = num_br(r['valueCash']) / (num_br(r['quotedPerShares']) or 1)
            dc = data_br(r['lastDatePriorEx'])
            info = pagto.get((dc, round(num_br(r['valueCash']), 8)), {})
            prov.append({'tipo': TIPOS.get(r['corporateAction'], r['corporateAction']), 'data_com': dc, 'pagamento': info.get('pagamento'), 'valor': v})
        # o historico fica guardado uma semana: o que o complemento (de hoje) traz e ainda nao esta nele entra aqui
        for c in sup.get('cashDividends', []):
            if c['isinCode'] != e['isin'] or not c.get('lastDatePrior'):
                continue
            dc, v = data_br(c['lastDatePrior']), num_br(c['rate'])
            if v and not any(p_['data_com'] == dc and abs(p_['valor'] - v) < 1e-6 for p_ in prov):
                prov.append({'tipo': TIPOS.get(c['label'], c['label'].title()), 'data_com': dc, 'pagamento': data_br(c.get('paymentDate')), 'valor': v})
    else:  # BDR: so o complemento traz os proventos
        for c in sup.get('cashDividends', []):
            if c['isinCode'] == e['isin']:
                prov.append({'tipo': c['label'].title(), 'data_com': data_br(c['lastDatePrior']), 'pagamento': data_br(c['paymentDate']), 'valor': num_br(c['rate'])})
    # ajusta proventos antigos pelos desdobramentos/grupamentos
    for p_ in prov:
        for d, k in fat:
            if p_['data_com'] <= d:
                p_['valor'] /= k
    det = b3api('GetDetail', {'codeCVM': sup['codeCVM'], 'language': 'pt-br'}, horas=24 * 30)
    return fat, sorted(prov, key=lambda x: x['data_com'], reverse=True), sup, det


def proventos_bdr(e, prov_b3, divs_us, px):
    """A B3 so mostra os proventos de BDR dos ultimos 12 meses. Guardamos tudo que ja apareceu em
    cache/proventos/<T>.json (o historico cresce sozinho a cada dia) e, para datas anteriores ao primeiro
    registro guardado, estimamos o valor em reais a partir do dividendo pago nos EUA:
    dividendo US$ x dolar PTAX x (1 - 30% de IR retido nos EUA) / proporcao do BDR, calibrada com os valores reais da B3."""
    arq = os.path.join(CACHE, 'proventos', e['ticker'] + '.json')
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    guard = json.load(open(arq)) if os.path.exists(arq) else []
    chave = lambda p: (p['data_com'], round(p['valor'], 6))
    tudo = {chave(p): p for p in guard}
    for p in prov_b3:
        tudo[chave(p)] = p
    reais = sorted(tudo.values(), key=lambda p: p['data_com'], reverse=True)
    json.dump(reais, open(arq, 'w'), ensure_ascii=False, indent=0)
    if not reais:
        return reais
    # casa cada provento da B3 com o dividendo americano mais proximo para calibrar
    us = [(dt.date.fromisoformat(d), v) for d, v in divs_us]
    ks, dif_dc, dif_pg = [], [], []
    for p in reais:
        dc = dt.date.fromisoformat(p['data_com'])
        d, v = min(us, key=lambda x: abs((x[0] - dc).days))
        if abs((d - dc).days) > 15:
            continue
        cam = preco_em(px, d.isoformat())
        ks.append(v * cam * 0.7 / p['valor'])
        dif_dc.append((d - dc).days)
        if p.get('pagamento'):
            dif_pg.append((dt.date.fromisoformat(p['pagamento']) - dc).days)
    if not ks:
        return reais
    k = statistics.median(ks)
    ddc, dpg = round(statistics.median(dif_dc)), round(statistics.median(dif_pg)) if dif_pg else 15
    primeiro = min(p['data_com'] for p in reais)
    inicio_bdr = e.get('desde', '2000-01-01')
    est = []
    for d, v in us:
        dc = d - dt.timedelta(days=ddc)
        if dc.isoformat() >= primeiro or dc.isoformat() < inicio_bdr or (dt.date.fromisoformat(primeiro) - dc).days < 20:
            continue
        cam = preco_em(px, d.isoformat())
        if cam:
            est.append({'tipo': 'Dividendo (estimado)', 'data_com': dc.isoformat(), 'pagamento': (dc + dt.timedelta(days=dpg)).isoformat(),
                        'valor': round(v * cam * 0.7 / k, 8)})
    return sorted(reais + est, key=lambda p: p['data_com'], reverse=True)


def trocas_paridade(cot, fat, px_us, px):
    """BDR: a B3 nem sempre lista a troca de paridade do BDR (ex.: GOGL34 em 22/10/2020, de 1 para 6).
    Procura saltos de preco que o papel nos EUA (convertido pelo dolar) nao teve e devolve o fator,
    no mesmo formato dos desdobramentos: (ultimo dia com o preco antigo, fator)."""
    ds = sorted(cot)
    out = []
    for a, b in zip(ds, ds[1:]):
        if not cot[b][3]:
            continue
        f = cot[a][3] / cot[b][3]
        if 0.6 < f < 1.6 or any(abs((dt.date.fromisoformat(d) - dt.date.fromisoformat(a)).days) <= 7 for d, _ in fat):
            continue
        ua, ub, da, db = preco_em(px_us, a), preco_em(px_us, b), preco_em(px, a), preco_em(px, b)
        if not all((ua, ub, da, db)):
            continue
        g = f * (ub * db) / (ua * da)  # o salto que nao veio do papel la fora nem do dolar
        for den in range(1, 26):
            n = round(g * den)
            if n and abs(n / den / g - 1) < 0.03:
                out.append((a, n / den))
                print(f'   troca de paridade detectada em {a}: fator {n}/{den}')
                break
    return out


def ajustar(cot, fat):
    """divide os precos anteriores a cada desdobramento pelo fator (precos comparaveis com hoje)"""
    out = {}
    for d, v in cot.items():
        k = 1
        for dd, f in fat:
            if d <= dd:
                k *= f
        out[d] = [round(x / k, 4) for x in v[:4]] + [v[4]]
    return out


def preco_em(precos, d):
    ks = [k for k in precos if k <= d]
    return precos[max(ks)] if ks else None


# ---------------------------------------------------------------- indicadores
def div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def indicadores(f, preco, n, prov12, banco=False, ev_igual_vm=False):
    """f: demonstracoes (12 meses ou ano); preco por acao; n acoes; prov12 = proventos por acao no periodo"""
    vm = preco * n if preco and n else None
    lpa = div(f.get('lucro_ctrl'), n); vpa = div(f.get('pl'), n)
    ev = vm if banco or vm is None else vm + (f.get('divida_liquida') or 0)
    acl = (f['ativo_circ'] - f['passivo_total']) if f.get('ativo_circ') is not None and f.get('passivo_total') is not None else None
    cg = (f['ativo_circ'] - f['passivo_circ']) if f.get('ativo_circ') is not None and f.get('passivo_circ') is not None else None
    pct = lambda x: x * 100 if x is not None else None
    return {
        'pl': div(preco, lpa), 'pvp': div(preco, vpa), 'psr': div(vm, f.get('receita')), 'ev_ebit': div(ev, f.get('ebit')),
        'ev_ebitda': div(ev, f.get('ebitda')), 'p_ebit': div(vm, f.get('ebit')), 'p_ativo': div(vm, f.get('ativo_total')),
        'p_acl': div(vm, acl), 'p_cg': div(vm, cg), 'lpa': lpa, 'vpa': vpa,
        'margem_bruta': pct(div(f.get('lucro_bruto'), f.get('receita'))), 'margem_ebit': pct(div(f.get('ebit'), f.get('receita'))),
        'margem_ebitda': pct(div(f.get('ebitda'), f.get('receita'))),
        'margem_liquida': pct(div(f.get('lucro_ctrl'), f.get('receita'))), 'giro_ativos': div(f.get('receita'), f.get('ativo_total')),
        'roe': pct(div(f.get('lucro_ctrl'), f.get('pl'))), 'roa': pct(div(f.get('lucro_liquido'), f.get('ativo_total'))),
        'roic': pct(div((f.get('ebit') or 0) - abs(f.get('imposto') or 0), (f.get('pl') or 0) + (f.get('divida_bruta') or 0))) if f.get('ebit') is not None else None,
        'dy': pct(div(prov12, preco)), 'payout': pct(div(prov12, lpa)),
        'liquidez_corrente': div(f.get('ativo_circ'), f.get('passivo_circ')),
        'pl_ativos': div(f.get('pl'), f.get('ativo_total')), 'passivos_ativos': div((f.get('passivo_total') or 0) - (f.get('pl_consolidado') or 0), f.get('ativo_total')) if f.get('passivo_total') else None,
        'divliq_pl': div(f.get('divida_liquida'), f.get('pl')) if not banco else None,
        'divliq_ebitda': div(f.get('divida_liquida'), f.get('ebitda')) if not banco else None,
        'valor_mercado': vm, 'valor_firma': ev,
    }


def cagr(a, b, anos):
    return ((a / b) ** (1 / anos) - 1) * 100 if a and b and a > 0 and b > 0 else None


# ---------------------------------------------------------------- fundos imobiliarios (FII)
FII_CVM = 'https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS'


def sgs(serie, inicio):
    """serie do Banco Central {data ISO: valor} desde <inicio>. Baixada uma vez por rodada (desde 2009) e cortada."""
    def busca():
        out, hoje = {}, dt.date.today()
        for ini in range(ANO_INICIO, hoje.year + 1, 9):
            fim = min(ini + 8, hoje.year)
            raw = baixar(f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json&dataInicial=01/01/{ini}&dataFinal=31/12/{fim}', timeout=90)
            for x in json.loads(raw):
                d = data_br(x['data'])
                if d <= hoje.isoformat():
                    out[d] = float(x['valor'])
        return out
    tudo = memo(('sgs', serie), busca)
    corte = f'{inicio}-01-01'
    return {d: v for d, v in tudo.items() if d >= corte} if inicio > ANO_INICIO else dict(tudo)


def fii_cvm_baixar(cnpjs):
    """Informe mensal de todos os FIIs acompanhados, numa leitura so de cada zip anual da CVM. Fundo novo ganha os anos
    desde 2016; os outros, so o ano atual (e o anterior nos primeiros 45 dias do ano). Guarda por fundo e ano em cache/fii/."""
    pasta = lambda c: os.path.join(CACHE, 'fii', re.sub(r'\D', '', c))
    novos = {c for c in cnpjs if not os.path.isdir(pasta(c))}
    hoje = dt.date.today()
    recentes = {hoje.year, (hoje - dt.timedelta(days=45)).year}
    for ano in range(2016, hoje.year + 1):
        alvo = set(cnpjs) if ano in recentes else novos
        if not alvo:
            continue
        print(' CVM FII', ano, f'({len(alvo)} fundos)')
        z = baixar(f'{FII_CVM}/inf_mensal_fii_{ano}.zip', timeout=300)
        if not z:
            continue
        meses = defaultdict(dict)
        with zipfile.ZipFile(io.BytesIO(z)) as zf:
            for nome in zf.namelist():
                parte = next((p for p in ('geral', 'complemento', 'ativo_passivo') if f'_{p}_' in nome), None)
                if not parte:
                    continue
                for r in csv.DictReader(io.StringIO(zf.read(nome).decode('latin-1')), delimiter=';'):
                    c = r.get('CNPJ_Fundo_Classe') or r.get('CNPJ_Fundo')
                    if c not in alvo:
                        continue
                    m = meses[c].setdefault(r['Data_Referencia'][:7], {})
                    if int(r.get('Versao') or 0) >= int(m.get('_v_' + parte, 0)):
                        m['_v_' + parte] = int(r.get('Versao') or 0)
                        m.update({k: v for k, v in r.items() if k})
        for c in alvo:
            os.makedirs(pasta(c), exist_ok=True)
            json.dump(meses.get(c, {}), open(os.path.join(pasta(c), f'{ano}.json'), 'w'), ensure_ascii=False)


def fii_cvm(e):
    """Informe mensal do fundo na CVM (patrimonio, cotas, cotistas, DY do mes, carteira), ja baixado por fii_cvm_baixar."""
    pasta = os.path.join(CACHE, 'fii', re.sub(r'\D', '', e['cnpj']))
    if not os.path.isdir(pasta):
        fii_cvm_baixar([e['cnpj']])
    tudo = {}
    for f in sorted(os.listdir(pasta)):
        tudo.update(json.load(open(os.path.join(pasta, f))))
    return dict(sorted(tudo.items()))


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def dia_util_antes(d):
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def fii_rendimentos(e, sup, cvm, dias):
    """Rendimentos por cota: B3 (oficial, ultimos 12 meses, guardados no cache para o historico crescer)
    e Yahoo para os meses mais antigos."""
    b3 = []
    for c in sup.get('cashDividends', []):
        if c['isinCode'] == e['isin']:
            b3.append({'tipo': c['label'].title(), 'data_com': data_br(c['lastDatePrior']), 'pagamento': data_br(c['paymentDate']), 'valor': num_br(c['rate'])})
    arq = os.path.join(CACHE, 'proventos', e['ticker'] + '.json')
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    guard = json.load(open(arq)) if os.path.exists(arq) else []
    tudo = {(p['data_com'], round(p['valor'], 6)): p for p in guard + b3}
    reais = sorted(tudo.values(), key=lambda p: p['data_com'])
    json.dump(reais, open(arq, 'w'), ensure_ascii=False, indent=0)
    meses = {p['data_com'][:7] for p in reais}
    dif_pg = [(dt.date.fromisoformat(p['pagamento']) - dt.date.fromisoformat(p['data_com'])).days for p in reais if p.get('pagamento')]
    dpg = round(statistics.median(dif_pg)) if dif_pg else 15
    out = list(reais)
    try:
        _, divs, _ = yahoo(e['ticker'] + '.SA', diario=False)  # so os rendimentos antigos: o historico da semana basta
    except Exception as ex:
        print('  Yahoo indisponivel:', ex)
        divs = []
    primeiro_b3 = min((p['data_com'] for p in reais), default='9999')
    perto = lambda dc: any(abs((dt.date.fromisoformat(p['data_com']) - dc).days) < 8 for p in out)
    for d, v in divs:
        # data com = ultimo pregao antes da data ex do Yahoo (assim feriados nao atrapalham)
        ant = [x for x in dias if x < d]
        dc = dt.date.fromisoformat(ant[-1]) if ant else dia_util_antes(dt.date.fromisoformat(d))
        # ja existe um rendimento a menos de 8 dias (a data ex do Yahoo cai depois de feriados): e o mesmo
        if perto(dc):
            continue
        meses.add(dc.isoformat()[:7])
        out.append({'tipo': 'Rendimento', 'data_com': dc.isoformat(), 'pagamento': (dc + dt.timedelta(days=dpg)).isoformat(), 'valor': round(round(v / 0.005) * 0.005, 3)})
    # so o trecho continuo mais recente (o Yahoo tem buracos antes de 2022: melhor mostrar menos do que mostrar errado)
    out.sort(key=lambda p: p['data_com'], reverse=True)
    for n in range(1, len(out)):
        if (dt.date.fromisoformat(out[n - 1]['data_com']) - dt.date.fromisoformat(out[n]['data_com'])).days > 50:
            out = out[:n]
            break
    return sorted(out, key=lambda p: p['data_com'], reverse=True)


def montar_fii(e, historico=False):
    print('==', e['ticker'])
    cot_raw = cot_ler(e['ticker'])
    if not cot_raw:
        raise ValueError('sem cotacao na B3')
    par = {'cnpj': re.sub(r'\D', '', e['cnpj']), 'identifierFund': e['b3'], 'typeFund': 7}
    q = base64.b64encode(json.dumps(par).encode()).decode()
    sup = em_cache(f'b3/GetListedSupplementFunds/{chave_arquivo(par)}', 20,
                   lambda: json.loads(baixar(f'https://sistemaswebb3-listados.b3.com.br/fundsProxy/fundsCall/GetListedSupplementFunds/{q}', timeout=60)))
    fat = []
    for s in sup.get('stockDividends') or []:
        if s['isinCode'] == e['isin'] and s.get('lastDatePrior') and s['label'] in EVENTOS_PRECO:
            f = num_br(s['factor'])
            fat.append((data_br(s['lastDatePrior']), f if s['label'] == 'GRUPAMENTO' else 1 + f / 100))
    fat = validar_eventos(sorted(set(fat), reverse=True), cot_raw)
    cot = ajustar(cot_raw, fat)
    dias = sorted(cot)
    hoje_d = dias[-1]
    preco = cot[hoje_d][3]
    fech = {d: cot[d][3] for d in dias}
    cvm = fii_cvm(e)
    prov = fii_rendimentos(e, sup, cvm, dias)
    um_ano = (dt.date.fromisoformat(hoje_d) - dt.timedelta(days=365)).isoformat()
    rend12 = [p['valor'] for p in prov if um_ano < p['data_com'] <= hoje_d]
    # antes disso nao ha rendimentos confiaveis: rentabilidades ficam de fora (fundo novo, sem rendimento ainda: nenhuma)
    ini_rend = min((p['data_com'] for p in prov), default=hoje_d)
    ult = cvm[max(cvm)]
    vp = fnum(ult.get('Valor_Patrimonial_Cotas'))
    cotas = fnum(ult.get('Cotas_Emitidas')) or fnum(ult.get('Quantidade_Cotas_Emitidas'))
    vol = [cot[d][4] for d in dias[-21:]]
    # mensal: informe da CVM + preco de fim de mes + rendimentos com data com no mes
    rend_mes = defaultdict(float)
    for p in prov:
        rend_mes[p['data_com'][:7]] += p['valor']
    mensal = {}
    for m, r in cvm.items():
        pm = preco_em(fech, m + '-31')
        kd = 1
        for dd, f in fat:
            if m < dd[:7]:
                kd *= f
        v = fnum(r.get('Valor_Patrimonial_Cotas'))
        v = v / kd if v else v
        mensal[m] = {'vp_cota': v, 'pl': fnum(r.get('Patrimonio_Liquido')), 'ativo': fnum(r.get('Valor_Ativo')), 'cotas': (fnum(r.get('Cotas_Emitidas')) or 0) * kd or None,
                     'cotistas': fnum(r.get('Total_Numero_Cotistas')), 'taxa_adm': fnum(r.get('Percentual_Despesas_Taxa_Administracao')),
                     'preco': pm, 'pvp': pm / v if pm and v else None, 'rend': round(rend_mes.get(m, 0), 6) or None}
    # taxa de administracao: soma das despesas dos ultimos 12 informes (em % do patrimonio)
    ult12 = list(mensal)[-12:]
    taxa12 = sum((mensal[m]['taxa_adm'] or 0) for m in ult12) * 100 if len(ult12) == 12 else None
    # rentabilidade com rendimentos (sem reinvestir) contra CDI e IPCA
    cdi = sgs(12, int(dias[0][:4]))
    ipca = sgs(433, int(dias[0][:4]))
    ex = defaultdict(float)  # rendimentos pela data ex (dia util seguinte a data com)
    for p in prov:
        d = dt.date.fromisoformat(p['data_com']) + dt.timedelta(days=1)
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        ex[d.isoformat()] += p['valor']

    def ret_fii(a, b):
        pa, pb = preco_em(fech, a), preco_em(fech, b)
        return (pb + sum(v for d, v in ex.items() if a < d <= b)) / pa - 1 if pa and pb else None

    def ret_cdi(a, b):
        f = 1
        for d, v in cdi.items():
            if a < d <= b:
                f *= 1 + v / 100
        return f - 1

    def ret_ipca(a, b):
        f = 1
        for d, v in ipca.items():
            if a[:7] < d[:7] <= b[:7]:
                f *= 1 + v / 100
        return f - 1
    hd = dt.date.fromisoformat(hoje_d)
    rentab = {}
    for k, meses_ in (('1m', 1), ('3m', 3), ('6m', 6), ('12m', 12), ('24m', 24), ('60m', 60), ('120m', 120)):
        a = (hd - dt.timedelta(days=round(meses_ * 30.4375))).isoformat()
        if a < dias[0] or a < ini_rend:
            continue
        rentab[k] = {'fii': ret_fii(a, hoje_d) * 100, 'cdi': ret_cdi(a, hoje_d) * 100, 'ipca': ret_ipca(a, hoje_d) * 100}
    # serie mensal acumulada (reinvestindo os rendimentos) para o grafico
    fims = sorted({d[:7] for d in dias if d[:7] >= ini_rend[:7]})
    serie = {'datas': [], 'fii': [], 'cdi': [], 'ipca': []}
    acc = [1, 1, 1]
    for i, m in enumerate(fims):
        if i:
            a, b = max(d for d in dias if d[:7] == fims[i - 1]), max(d for d in dias if d[:7] == m)
            acc[0] *= 1 + (ret_fii(a, b) or 0)
            acc[1] *= 1 + ret_cdi(a, b)
            acc[2] *= 1 + ret_ipca(a, b)
        serie['datas'].append(m)
        for j, k in enumerate(('fii', 'cdi', 'ipca')):
            serie[k].append(round((acc[j] - 1) * 100, 2))
    # anual
    anual = {}
    for a in sorted({d[:4] for d in dias}):
        pa = preco_em(fech, f'{a}-12-31')
        rs = sum(p['valor'] for p in prov if p['data_com'][:4] == a) if ini_rend[:7] <= f'{a}-01' else 0
        mv = [m for m in mensal if m[:4] == a]
        vpa = mensal[mv[-1]]['vp_cota'] if mv else None
        ini = preco_em(fech, f'{int(a) - 1}-12-31') and f'{int(a) - 1}-12-31' if ini_rend[:7] <= f'{a}-01' else None
        anual[a] = {'preco': pa, 'rend': rs or None, 'dy': rs / pa * 100 if rs and pa else None, 'vp_cota': vpa, 'pvp': pa / vpa if pa and vpa else None,
                    'pl': mensal[mv[-1]]['pl'] if mv else None, 'cotistas': mensal[mv[-1]]['cotistas'] if mv else None,
                    'rent': ret_fii(ini, min(f'{a}-12-31', hoje_d)) * 100 if ini else None, 'cdi': ret_cdi(ini, min(f'{a}-12-31', hoje_d)) * 100 if ini else None}
    # carteira (ultimo informe)
    g = lambda *ks: sum(fnum(ult.get(k)) or 0 for k in ks)
    itens = [['CRI / CRA', g('CRI', 'CRI_CRA')], ['Cotas de outros FII', g('FII')], ['Imóveis', g('Direitos_Bens_Imoveis')],
             ['Participações em sociedades', g('Acoes', 'Acoes_Sociedades_Atividades_FII', 'Cotas_Sociedades_Atividades_FII')],
             ['LCI / LCA', g('LCI', 'LCI_LCA', 'Letras_Hipotecarias', 'LIG')],
             ['Caixa e renda fixa', g('Disponibilidades', 'Titulos_Publicos', 'Titulos_Privados', 'Fundos_Renda_Fixa')],
             ['Outros títulos e fundos', g('Debentures', 'FIP', 'FDIC', 'Outras_Cotas_FI', 'Fundo_Acoes', 'Notas_Promissorias', 'CEPAC', 'Certificados_Deposito_Valores_Mobiliarios', 'Cedulas_Debentures', 'Bonus_Subscricao', 'Outros_Valores_Mobliarios')],
             ['Valores a receber', g('Valores_Receber')]]
    itens = [x for x in itens if x[1] > 0]
    ind = {'dy': sum(rend12) / preco * 100 if rend12 else None, 'pvp': preco / vp if vp else None, 'ultimo_rendimento': prov[0]['valor'] if prov else None,
           'ultimo_rend_data': prov[0]['data_com'] if prov else None, 'rend_medio_12m': statistics.mean(rend12) if rend12 else None, 'rend_12m': sum(rend12),
           'vp_cota': vp, 'pl': fnum(ult.get('Patrimonio_Liquido')), 'valor_mercado': preco * cotas if cotas else None, 'liquidez_diaria': statistics.mean(vol),
           'cotistas': fnum(ult.get('Total_Numero_Cotistas')), 'cotas': cotas, 'taxa_adm_12m': taxa12,
           'rent_12m': (rentab.get('12m') or {}).get('fii'), 'dy_medio_5a': None}
    cg = lambda *ks: int(sum(fnum(ult.get(k)) or 0 for k in ks))
    cotistas = {'data': ult.get('Data_Informacao_Numero_Cotistas') or max(cvm), 'total': cg('Total_Numero_Cotistas'),
                'grupos': [x for x in [['Pessoas físicas', cg('Numero_Cotistas_Pessoa_Fisica')],
                                       ['Empresas', cg('Numero_Cotistas_Pessoa_Juridica_Nao_Financeira')],
                                       ['Bancos, corretoras e financeiras', cg('Numero_Cotistas_Banco_Comercial', 'Numero_Cotistas_Corretora_Distribuidora', 'Numero_Cotistas_Outras_Pessoas_Juridicas_Financeira', 'Numero_Cotistas_Distribuidores_Fundo')],
                                       ['Fundos (FII e outros)', cg('Numero_Cotistas_FII', 'Numero_Cotistas_Outros_Fundos')],
                                       ['Previdência e seguradoras', cg('Numero_Cotistas_Entidade_Aberta_Previdencia_Complementar', 'Numero_Cotistas_Entidade_Fechada_Previdência_Complementar', 'Numero_Cotistas_Regime_Proprio_Previdencia_Servidores_Publicos', 'Numero_Cotistas_Sociedade_Seguradora_Resseguradora', 'Numero_Cotistas_Sociedade_Capitalizacao_Arrendamento_Mercantil')],
                                       ['Investidores de fora do Brasil', cg('Numero_Cotistas_Investidores_Nao_Residentes')],
                                       ['Outros', cg('Numero_Cotistas_Outros_Tipos')]] if x[1] > 0]}
    a5 = [anual[a]['dy'] for a in list(anual)[-6:-1] if anual[a]['dy']]
    ind['dy_medio_5a'] = statistics.mean(a5) if a5 else None
    info = {'razao': ult.get('Nome_Fundo_Classe') or ult.get('Nome_Fundo'), 'cnpj': e['cnpj'], 'publico_alvo': (ult.get('Publico_Alvo') or '').title(),
            'mandato': ult.get('Mandato') or None, 'segmento_cvm': ult.get('Segmento_Atuacao') or None, 'tipo_gestao': ult.get('Tipo_Gestao') or None,
            'prazo': ult.get('Prazo_Duracao') or None, 'administrador': ult.get('Nome_Administrador') or sup.get('ifd'), 'inicio': ult.get('Data_Funcionamento'),
            'isin': e['isin'], 'site': ult.get('Site') or None, 'informe_ref': max(cvm)}
    return {'ticker': e['ticker'], 'tipo': 'fii', 'nome': e['nome'], 'razao': info['razao'], 'setor': e['setor'], 'segmento': e['segmento'],
            'tipo_fundo': e.get('tipo_fundo'), 'atualizado': dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime('%Y-%m-%d %H:%M'),
            'fechamento': hoje_d, 'preco': preco, 'cotacao': [[d] + cot[d] for d in dias], 'moeda_balanco': 'BRL', 'balanco_ref': max(cvm) + '-01',
            'indicadores': ind, 'info': info, 'mensal': mensal, 'anual': anual, 'rentab': rentab, 'serie_rent': serie,
            'composicao': {'data': max(cvm), 'itens': itens}, 'cotistas': cotistas, 'proventos': prov, 'eventos': [{'data': d, 'fator': k} for d, k in fat]}


def montar(e, historico=False):
    if e['tipo'] == 'fii':
        return montar_fii(e, historico)
    print('==', e['ticker'])
    cot_raw = cot_ler(e['ticker'])
    if not cot_raw:
        raise ValueError('sem cotacao na B3')
    fat, prov, sup, det = eventos_b3(e, cot_raw)
    if e['tipo'] == 'bdr':
        yh, px = yahoo(e['us']), ptax()
        extra = trocas_paridade(cot_raw, fat, yh[0], px)
        for p_ in prov:
            for d, k in extra:
                if p_['data_com'] <= d:
                    p_['valor'] /= k
        fat = sorted(fat + extra, reverse=True)
    cot = ajustar(cot_raw, fat)
    dias = sorted(cot)
    hoje_d = dias[-1]
    preco = cot[hoje_d][3]
    ult_ano = int(hoje_d[:4])
    # proventos por data com
    def prov_entre(a, b):
        return sum(p['valor'] for p in prov if a < p['data_com'] <= b)
    um_ano = (dt.date.fromisoformat(hoje_d) - dt.timedelta(days=365)).isoformat()
    out = {'ticker': e['ticker'], 'tipo': e['tipo'], 'nome': e['nome'], 'razao': e['razao'], 'setor': e['setor'], 'segmento': e['segmento'],
           'atualizado': dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime('%Y-%m-%d %H:%M'), 'fechamento': hoje_d,
           'preco': preco, 'cotacao': [[d] + cot[d] for d in dias]}
    if e['tipo'] == 'acao':
        anual, ttm, ref, trim, cap_ref, caps = fin_brasil(e)
        # a CVM nao diz a escala da composicao do capital: algumas empresas informam em milhares (Itau sempre,
        # Bradesco ate 2023). Fica a escala (x1 ou x1000) mais perto do total de acoes que a B3 mostra hoje.
        ref_n = num_br(sup.get('totalNumberShares'))
        if ref_n:
            esc = lambda v: min((v, v * 1000), key=lambda x: abs(__import__('math').log(x / ref_n))) if v else v
            for a_ in anual.values():
                a_['acoes'] = esc(a_.get('acoes'))
            ttm['acoes'] = esc(ttm.get('acoes'))
        n = ttm['acoes']
        fatk = lambda d: __import__('math').prod(k for dd, k in fat if d <= dd)  # todos os eventos depois da data
        prov12 = prov_entre(um_ano, hoje_d)
        ind = indicadores(ttm, preco, n, prov12, banco=e.get('banco'))
        hist = {}
        for ano in sorted(anual):
            a = anual[ano]
            pa = preco_em({d: cot[d][3] for d in dias}, f'{ano}-12-31')
            na = (a.get('acoes') or n) * fatk(f'{ano}-12-31')  # acoes do ano no criterio de hoje
            hist[ano] = indicadores(a, pa, na, prov_entre(f'{ano - 1}-12-31', f'{ano}-12-31'), banco=e.get('banco')) if pa else {}
            hist[ano]['preco'] = pa
        ff = fre_free_float([e['cnpj']]).get(e['cnpj'], {})
        try:
            dn = donos(e['cnpj'])
        except Exception as ex:
            print('  aviso: donos de', e['ticker'], repr(ex)); dn = None
        if dn:
            dn.update({k: ff.get(k) for k in ('pf', 'pj', 'inst')})
            out['donos'] = dn
        out['acoes_hist'] = {str(a): round((anual[a].get('acoes') or 0) * fatk(f'{a}-12-31')) or None for a in sorted(anual)}
        out['acoes_hist']['hoje'] = n
        vol60 = [cot[d][4] for d in dias[-21:]]  # liquidez media do ultimo mes
        info = {'valor_mercado': ind['valor_mercado'], 'valor_firma': ind['valor_firma'], 'pl': ttm.get('pl'), 'n_papeis': n,
                'ativos': ttm.get('ativo_total'), 'ativo_circ': ttm.get('ativo_circ'), 'disponibilidade': ttm.get('disponibilidade'),
                'divida_bruta': ttm.get('divida_bruta'), 'divida_liquida': ttm.get('divida_liquida'),
                'free_float': ff.get('free_float'), 'acionistas': ff.get('acionistas'),
                'tag_along': 100.0 if sup.get('segment') == 'NM' else None, 'liquidez_diaria': statistics.mean(vol60),
                'listagem': {'NM': 'Novo Mercado', 'N1': 'Nível 1', 'N2': 'Nível 2'}.get(sup.get('segment'), sup.get('segment')),
                'setor_b3': det.get('industryClassification'), 'cnpj': e['cnpj'], 'site': det.get('website'), 'atividade': det.get('activity')}
        moeda = 'BRL'
    else:
        anual, ttm, ref, trim = fin_eua_guardado(e['cik'])
        px_us, divs_us, splits = yh
        splits_depois = lambda d: __import__('math').prod(k for dd, k in splits if dd > d)
        prov = proventos_bdr({**e, 'desde': e.get('desde') or dias[0]}, prov, divs_us, px)  # sem estimar antes do BDR existir
        d_us = max(px_us); p_us = px_us[d_us]
        n = ttm['acoes']
        prov12 = sum(v for d, v in divs_us if d > (dt.date.fromisoformat(d_us) - dt.timedelta(days=365)).isoformat())
        ind = indicadores(ttm, p_us, n, prov12)
        hist = {}
        fim_ano = lambda a: anual[a].get('fim') or f'{a}-12-31'  # fechamento do ano fiscal da empresa
        for ano in sorted(anual):
            fa = fim_ano(ano)
            pa = preco_em(px_us, fa)
            fa0 = (dt.date.fromisoformat(fa) - dt.timedelta(days=365)).isoformat()
            dps = sum(v for d, v in divs_us if fa0 < d <= fa)
            na = (anual[ano].get('acoes') or n) * splits_depois(fa)
            hist[ano] = indicadores(anual[ano], pa, na, dps) if pa else {}
            hist[ano]['preco'] = pa
        dolar = preco_em(px, hoje_d)
        paridade = round(p_us * dolar / preco, 2) if dolar else None
        vol60 = [cot[d][4] for d in dias[-21:]]  # liquidez media do ultimo mes
        info = {'valor_mercado': ind['valor_mercado'], 'valor_firma': ind['valor_firma'], 'pl': ttm.get('pl'), 'n_papeis': n,
                'ativos': ttm.get('ativo_total'), 'ativo_circ': ttm.get('ativo_circ'), 'disponibilidade': ttm.get('disponibilidade'),
                'divida_bruta': ttm.get('divida_bruta'), 'divida_liquida': ttm.get('divida_liquida'),
                'liquidez_diaria': statistics.mean(vol60), 'preco_eua': p_us, 'data_eua': d_us, 'dolar': dolar, 'paridade': paridade,
                'n_bdrs': num_br(sup.get('totalNumberShares')), 'depositario': sup.get('hasPreferred'), 'codigo_cvm': sup.get('codeCVM'),
                'site': det.get('website'), 'atividade': det.get('activity'), 'ticker_eua': e['us']}
        out['proventos_empresa'] = [{'data_com': d, 'valor': v} for d, v in reversed(divs_us)]
        out['acoes_hist'] = {str(a): round((anual[a].get('acoes') or 0) * splits_depois(fim_ano(a))) or None for a in sorted(anual)}
        out['acoes_hist']['hoje'] = n
        out['preco_eua_anual'] = {str(a): preco_em(px_us, fim_ano(a)) for a in anual}
        out['preco_eua_mensal'] = {d[:7]: px_us[d] for d in sorted(px_us)}  # ultimo pregao de cada mes (termometro do BDR)
        moeda = 'USD'
    anos = sorted(anual)
    a5 = [a for a in anos if a <= ult_ano - 5]
    base5 = anual[ult_ano - 6] if ult_ano - 6 in anual else None  # ultimo ano fechado - 5
    ultimo_fechado = max(anos)
    ind['cagr_receitas_5a'] = cagr(ttm['receita'], anual.get(ultimo_fechado - 4, {}).get('receita'), 5)  # mesmo criterio do Investidor10
    ind['cagr_lucros_5a'] = cagr(anual[ultimo_fechado]['lucro_liquido'], anual.get(ultimo_fechado - 5, {}).get('lucro_liquido'), 5)
    campos = ['receita', 'custos', 'lucro_bruto', 'lucro_liquido', 'lucro_ctrl', 'ebitda', 'ebit', 'imposto', 'divida_bruta', 'divida_liquida',
              'ativo_total', 'ativo_circ', 'ativo_nc', 'passivo_total', 'passivo_circ', 'passivo_nc', 'pl_consolidado', 'pl', 'disponibilidade', 'acoes']
    out.update({
        'moeda_balanco': moeda, 'balanco_ref': ref, 'indicadores': ind, 'info': info,
        'anual': {str(a): {k: anual[a].get(k) for k in campos} for a in anos},
        'ttm': {k: ttm.get(k) for k in campos},
        'hist_indicadores': {str(a): hist[a] for a in anos},
        'trimestres': {d: trim[d] for d in sorted(trim)},
        'proventos': prov, 'eventos': [{'data': d, 'fator': k} for d, k in fat],
    })
    return out


def resumo(d):
    """linha do indice.json: e o que a pagina de pesquisa (index.html) lista e filtra"""
    c, I, inf = d['cotacao'], d['indicadores'], d.get('info', {})
    ult = c[-1]
    ant = c[-2] if len(c) > 1 else ult
    um_ano = (dt.date.fromisoformat(ult[0]) - dt.timedelta(days=365)).isoformat()
    base = next((r for r in c if r[0] >= um_ano), c[0])
    fii = d['tipo'] == 'fii'
    return {'ticker': d['ticker'], 'nome': d['nome'], 'tipo': d['tipo'], 'setor': d.get('setor'), 'segmento': d.get('segmento'),
            'fechamento': d['fechamento'], 'preco': d['preco'], 'var_dia': (ult[4] / ant[4] - 1) * 100, 'var_12m': (ult[4] / base[4] - 1) * 100,
            'dy': I.get('dy'), 'pvp': I.get('pvp'), 'pl': None if fii else I.get('pl'), 'roe': None if fii else I.get('roe'),
            'liquidez': I.get('liquidez_diaria') if fii else inf.get('liquidez_diaria'),
            'valor_mercado': I.get('valor_mercado') if fii else inf.get('valor_mercado'), 'moeda_vm': 'USD' if d['tipo'] == 'bdr' else 'BRL',
            # para o "Lado a lado com o setor"
            'tipo_fundo': d.get('tipo_fundo'), 'margem_liquida': None if fii else I.get('margem_liquida'),
            'divliq_ebitda': None if fii else I.get('divliq_ebitda'), 'cagr_lucros_5a': None if fii else I.get('cagr_lucros_5a'),
            'cagr_receitas_5a': None if fii else I.get('cagr_receitas_5a'), 'taxa_adm': I.get('taxa_adm_12m') if fii else None,
            'rent_12m': I.get('rent_12m') if fii else None, 'cotistas': I.get('cotistas') if fii else inf.get('acionistas')}


# ---------------------------------------------------------------- indices de comparacao
INDICES_B3 = ['IBOV', 'IFIX', 'SMLL', 'IDIV']
INDICE_INICIO = 2012


def indice_b3_ano(idx, ano):
    """fechamento diario de um indice da B3 num ano {data ISO: valor} (tabela dia x mes do site da B3)"""
    q = base64.b64encode(json.dumps({'language': 'pt-br', 'index': idx, 'year': str(ano)}).encode()).decode()
    d = json.loads(baixar(f'https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{q}', timeout=60))
    out = {}
    for r in d.get('results', []):
        for m in range(1, 13):
            v = r.get(f'rateValue{m}')
            if v:
                out[f'{ano}-{m:02d}-{r["day"]:02d}'] = float(v.replace('.', '').replace(',', '.'))
    return out


def fim_de_mes(serie):
    """{data ISO: valor} -> {AAAA-MM: ultimo valor do mes}"""
    out = {}
    for d in sorted(serie):
        out[d[:7]] = serie[d]
    return out


def indices():
    """dados/indices.json: fim de cada mes de IBOV, IFIX, SMLL, IDIV (B3), IVVB11 (Yahoo), CDI e IPCA do mes (Banco Central).
    Os anos fechados ficam em cache/indices/; so o ano corrente e baixado de novo."""
    hoje = dt.date.today()
    pasta = os.path.join(CACHE, 'indices')
    os.makedirs(pasta, exist_ok=True)
    series, ultimo = {}, {}
    for idx in INDICES_B3:
        diario = {}
        for ano in range(INDICE_INICIO, hoje.year + 1):
            arq = os.path.join(pasta, f'{idx}_{ano}.json')
            if ano < hoje.year and os.path.exists(arq):
                diario.update(json.load(open(arq)))
                continue
            v = indice_b3_ano(idx, ano)
            if ano < hoje.year and v:
                json.dump(v, open(arq, 'w'), separators=(',', ':'))
            diario.update(v)
        series[idx] = fim_de_mes(diario)
        ultimo[idx] = max(diario) if diario else None
    precos, _, _ = yahoo('IVVB11.SA')
    series['IVVB11'] = fim_de_mes(precos)
    ultimo['IVVB11'] = max(precos)
    cdi = {d[:7]: v for d, v in sgs(4391, INDICE_INICIO).items()}
    ipca = {d[:7]: v for d, v in sgs(433, INDICE_INICIO).items()}
    return {'atualizado': dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime('%Y-%m-%d %H:%M'),
            'ultimo_dia': ultimo, 'mensal': series, 'cdi_mes': cdi, 'ipca_mes': ipca,
            'fontes': 'B3 (IBOV, IFIX, SMLL, IDIV), Yahoo Finance (IVVB11), Banco Central (CDI e IPCA do mês)'}


# ---------------------------------------------------------------- comunicados
def ipe(ano):
    """documentos entregues pelas companhias abertas a CVM num ano (um zip para todas), separados por CNPJ"""
    def busca():
        z = zipfile.ZipFile(io.BytesIO(baixar(f'{CVM}/IPE/DADOS/ipe_cia_aberta_{ano}.zip', timeout=180)))
        idx = defaultdict(list)
        for r in csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding='latin-1'), delimiter=';'):
            idx[r['CNPJ_Companhia']].append(r)
        return idx
    return memo(('ipe', ano), busca)


SEC_FORMS = {'10-K': 'Relatório anual (10-K)', '10-Q': 'Relatório trimestral (10-Q)', '8-K': 'Comunicado ao mercado (8-K)',
             'DEF 14A': 'Convocação de assembleia (DEF 14A)', '20-F': 'Relatório anual (20-F)', '6-K': 'Comunicado ao mercado (6-K)'}
COMUNICADOS_MAX = 60


MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
IPE_RELATORIOS = ('Apresentações a analistas/agentes do mercado', 'Press-release', 'Relatório de Análise Gerencial')
RELATORIOS_MAX = 36


def comunicados(e):
    """documentos oficiais do ativo, em duas listas de {data, titulo, tipo, url}:
    comunicados (avisos, fatos relevantes, atas...) e relatorios (o material visual de resultados:
    relatorio gerencial do FII, apresentacao/release de resultados da empresa, release trimestral na SEC)."""
    com, rel = [], []
    if e['tipo'] == 'fii':
        cnpj = re.sub(r'\D', '', e['cnpj'])
        def busca():
            docs = []
            for s in (0, 100):  # ~200 documentos mais recentes: da para uns 3 anos de relatorios gerenciais
                raw = baixar(f'https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados?d=0&s={s}&l=100'
                             f'&o%5B0%5D%5BdataEntrega%5D=desc&cnpjFundo={cnpj}', headers={'User-Agent': UA, 'X-Requested-With': 'XMLHttpRequest'}, timeout=60)
                docs += json.loads(raw)['data']
            return docs
        docs = em_cache(f'fnet/{cnpj}', 60, busca)  # documentos do fundo: a cada 2 dias e meio
        for x in docs:
            tipo = (x.get('tipoDocumento') or '').strip()
            cat = (x.get('categoriaDocumento') or '').strip()
            d, m, a = x['dataEntrega'][:10].split('/')
            url = f'https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={x["id"]}'
            if tipo == 'Relatório Gerencial':
                ref = (x.get('dataReferencia') or '').strip()
                ref = MESES[int(ref[3:5]) - 1] + '/' + ref[6:10] if len(ref) == 10 else ''
                rel.append({'data': f'{a}-{m}-{d}', 'titulo': 'Relatório Gerencial' + (f' · {ref}' if ref else ''), 'tipo': 'B3 Fundos.NET', 'url': url})
            else:
                titulo = tipo if tipo and tipo != 'Outros Documentos' else (x.get('especieDocumento') or '').strip() or cat
                com.append({'data': f'{a}-{m}-{d}', 'titulo': titulo, 'tipo': cat, 'url': url})
    elif e['tipo'] == 'acao':
        hoje = dt.date.today()
        lin = [x for ano in (hoje.year, hoje.year - 1) for x in ipe(ano).get(e['cnpj'], [])]
        for x in lin:
            if x['Categoria'].startswith('Valores Mobiliários negociados'):
                continue  # posicao mensal de administradores: muito repetitivo
            titulo = x['Assunto'].strip() or x['Tipo'].strip() or x['Categoria'].strip()
            item = {'data': x['Data_Entrega'][:10], 'titulo': titulo[:140], 'tipo': x['Categoria'].strip(), 'url': x['Link_Download']}
            if x['Tipo'].strip() in IPE_RELATORIOS:
                item['tipo'] = x['Tipo'].strip().replace('Apresentações a analistas/agentes do mercado', 'Apresentação')
                rel.append(item)
            else:
                com.append(item)
    elif e['tipo'] == 'bdr':
        r = sec_json(f'submissions/CIK{e["cik"]}.json', 72)['filings']['recent']
        for i, f in enumerate(r['form']):
            if f not in SEC_FORMS:
                continue
            ac = r['accessionNumber'][i]
            base = f'https://www.sec.gov/Archives/edgar/data/{int(e["cik"])}/{ac.replace("-", "")}/'
            if f in ('8-K', '6-K') and '2.02' in (r.get('items') or [''] * (i + 1))[i]:
                # 8-K item 2.02 = divulgacao de resultado; o release (anexo 99.1) fica na pagina do envio
                fd = r['filingDate'][i]
                q, y = (int(fd[5:7]) - 1) // 3, int(fd[:4])  # o release sai no trimestre seguinte ao que ele cobre
                q, y = (4, y - 1) if q == 0 else (q, y)
                rel.append({'data': fd, 'titulo': f'Resultado do {q}º trimestre de {y} (release)',
                            'tipo': 'SEC (em inglês)', 'url': base + ac + '-index.htm'})
            else:
                com.append({'data': r['filingDate'][i], 'titulo': SEC_FORMS[f], 'tipo': 'SEC (em inglês)', 'url': base + r['primaryDocument'][i]})
    com.sort(key=lambda x: x['data'], reverse=True)
    rel.sort(key=lambda x: x['data'], reverse=True)
    vistos = set()  # documento reenviado (nova versao) aparece uma vez so, a mais nova
    rel = [x for x in rel if not (x['titulo'] in vistos or vistos.add(x['titulo']))]
    return com[:COMUNICADOS_MAX], rel[:RELATORIOS_MAX]


def gravar(arq, d):
    """grava o JSON so se mudou algo alem do horario de 'atualizado' (evita commit e nova publicacao na Netlify sem dado novo)"""
    sem_hora = lambda x: {k: v for k, v in x.items() if k != 'atualizado'}
    if os.path.exists(arq):
        try:
            if sem_hora(json.load(open(arq, encoding='utf-8'))) == json.loads(json.dumps(sem_hora(d), ensure_ascii=False)):
                return False
        except ValueError:
            pass
    json.dump(d, open(arq, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    return True


def carregar_empresas():
    """cache/universo.json (todas as acoes e FIIs da B3 e os BDRs de empresas americanas, feito pelo universo.py)
    com as EMPRESAS escritas a mao por cima. Sem o universo, so as EMPRESAS."""
    fixas = {e['ticker']: e for e in EMPRESAS}
    arq = os.path.join(CACHE, 'universo.json')
    lista = []
    if os.path.exists(arq):
        for e in json.load(open(arq, encoding='utf-8'))['ativos']:
            lista.append({**e, **fixas.get(e['ticker'], {})})
    vistos = {e['ticker'] for e in lista}
    return lista + [e for t, e in fixas.items() if t not in vistos]


def opcao(nome):
    return sys.argv[sys.argv.index(nome) + 1] if nome in sys.argv and sys.argv.index(nome) + 1 < len(sys.argv) else None


def main():
    historico = '--historico' in sys.argv
    os.makedirs(SAIDA, exist_ok=True)
    hoje = dt.date.today()
    inicio = time.time()
    empresas = carregar_empresas()
    so = opcao('--so')
    if so:
        quer = {x.strip().upper() for x in so.split(',')}
        empresas = [e for e in empresas if e['ticker'] in quer]
    if opcao('--limite'):
        empresas = empresas[:int(opcao('--limite'))]
    teste = bool(so or opcao('--limite'))
    conta = lambda k: sum(1 for e in empresas if e['tipo'] == k)
    print(f"{len(empresas)} ativos: {conta('acao')} acoes, {conta('fii')} FIIs, {conta('bdr')} BDRs")

    # 1. arquivos grandes, uma vez para todos: balancos da CVM, informes dos FIIs, cotacoes da B3
    cnpjs = sorted({e['cnpj'] for e in empresas if e['tipo'] == 'acao'})
    pasta_cvm = lambda c: os.path.join(CACHE, 'cvm', re.sub(r'\D', '', c))
    novos = [c for c in cnpjs if not os.path.isdir(pasta_cvm(c))]  # empresa nova: busca os balancos desde 2010
    if cnpjs:
        for ano in range(2010, hoje.year):
            alvo = cnpjs if (historico or ano == hoje.year - 1) else novos
            if alvo:
                print(' CVM DFP', ano, f'({len(alvo)} empresas)'); cvm_baixar('dfp', ano, alvo)
        for ano in (hoje.year - 1, hoje.year):
            print(' CVM ITR', ano); cvm_baixar('itr', ano, cnpjs)
    fiis = sorted({e['cnpj'] for e in empresas if e['tipo'] == 'fii'})
    if fiis:
        fii_cvm_baixar(fiis)
    atualizar_cotacoes_todas([e['ticker'] for e in empresas], historico)
    print(f' arquivos em lote prontos em {round(time.time() - inicio)} s')

    # 2. cada ativo (varios ao mesmo tempo: a maior parte do tempo e espera da rede)
    arq_ind = os.path.join(SAIDA, 'indice.json')
    antigo = {x['ticker']: x for x in json.load(open(arq_ind, encoding='utf-8')).get('acoes', [])} if os.path.exists(arq_ind) else {}

    def processar(e):
        _log_ativo.ticker = e['ticker']
        try:
            d = montar(e, historico)
        except Exception as ex:  # mantem o arquivo de ontem desse ativo e segue com os outros
            print('  ERRO em', e['ticker'], repr(ex)[:300])
            return e, None
        arq = os.path.join(SAIDA, e['ticker'] + '.json')
        try:
            d['comunicados'], d['relatorios'] = comunicados(e)
        except Exception as ex:  # fonte fora do ar: ficam as listas de ontem
            print('  aviso: comunicados de', e['ticker'], repr(ex)[:200])
            try:
                ontem = json.load(open(arq, encoding='utf-8'))
            except Exception:
                ontem = {}
            d['comunicados'], d['relatorios'] = ontem.get('comunicados', []), ontem.get('relatorios', [])
        gravar(arq, d)
        print(f"  ok {d['ticker']}: {d['preco']} em {d['fechamento']}, balanço {d['balanco_ref']}")
        return e, resumo(d)

    with ThreadPoolExecutor(max_workers=TRABALHADORES) as ex:
        resultados = list(ex.map(processar, empresas))
    indice, erros = [], []
    for e, r in resultados:
        if r:
            indice.append(r)
        else:
            erros.append(e['ticker'])
            if e['ticker'] in antigo:
                indice.append(antigo[e['ticker']])
    try:
        gravar(os.path.join(SAIDA, 'indices.json'), indices())
        print('  ok índices de comparação')
    except Exception as ex:  # fica o arquivo de ontem
        print('  aviso: índices de comparação', repr(ex))
    if teste and antigo:  # rodada de teste: os ativos que ficaram de fora continuam na pesquisa
        feitos = {x['ticker'] for x in indice}
        indice += [x for t, x in antigo.items() if t not in feitos]
    indice.sort(key=lambda x: -(x.get('liquidez') or 0))  # a pesquisa abre pelos mais negociados
    gravar(arq_ind, {'atualizado': dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).strftime('%Y-%m-%d %H:%M'), 'acoes': indice})
    print(f'\n{len(empresas) - len(erros)} de {len(empresas)} ativos atualizados em {round((time.time() - inicio) / 60, 1)} min.'
          + (f' Ficaram com os dados anteriores ({len(erros)}): {", ".join(erros)}' if erros else ''))
    if erros and len(erros) == len(empresas):
        sys.exit('nenhum ativo foi atualizado')


if __name__ == '__main__':
    main()
