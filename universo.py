#!/usr/bin/env python3
"""Lista de todos os ativos que o robo acompanha: grava cache/universo.json, que o atualizar.py le.

  - Acoes: todo codigo de acao (ISIN ...ACN...) negociado no mercado a vista da B3 no ultimo mes, da empresa que esta na
    lista de companhias da B3. Nome com acento do cadastro da CVM; setor e segmento da classificacao da B3.
    Ficam de fora, por enquanto, as units (SANB11, TAEE11...): o n. de acoes da CVM conta ON e PN separadas.
  - FIIs: todo fundo imobiliario (ISIN ...CTF..., codigo BDI 12) negociado no ultimo mes que esta no informe mensal da CVM.
    O tipo (papel, tijolo, fundo de fundos, hibrido) sai da carteira do ultimo informe.
  - BDRs: BDR de empresa (nao de ETF) negociado no ultimo mes, cuja empresa entrega 10-K/10-Q a SEC (balanco em US GAAP).
    A empresa americana e achada pelo nome (lista de tickers da SEC); setor pelo codigo SIC.

Roda uma vez por semana: o workflow chama todo dia, e o script so refaz a lista se ela tiver 7 dias ou mais
(ou com --forcar). Uso: python universo.py [--forcar]
Fontes publicas e gratuitas: B3 (COTAHIST, listas de empresas e BDRs), CVM (cadastro, informe de FII) e SEC.
"""
import csv, io, json, os, re, sys, time, unicodedata, zipfile, datetime as dt
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import atualizar as A

ARQ = os.path.join(A.CACHE, 'universo.json')
VERSAO = 4  # suba quando mudar a regra da lista: a lista guardada e refeita na hora, sem esperar a semana
DIAS = 30  # negociado nesse periodo


def fmt_cnpj(c):
    c = re.sub(r'\D', '', str(c)).zfill(14)
    return f'{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}'


MINUSCULAS = {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'of', 'and', 'the', 'para'}
SUFIXOS = (r'(?<![\wÀ-ÿ])(S\.\s?A\.?|S/A|SA|LTDA\.?|INC\.?|INCORPORATED|CORP\.?|CORPORATION|CO\.|COS|COMPANY|PLC|LIMITED|LTD\.?|N\.V\.?|NV|AG|SE|'
           r'HOLDINGS?|GROUP|CLASS [A-Z]|THE)(?![\wÀ-ÿ])')
# siglas com vogal que ficam em maiusculas (as sem vogal, como BRF, CSN, CSHG, ficam sozinhas)
SIGLAS = {'WEG', 'TIM', 'EOG', 'IRB', 'GPA', 'AES', 'IBM', 'AMD', 'UPS', 'EQT', 'AXA', 'ING', 'UBS', 'BHP', 'ABB', 'SAP', 'ASML', 'AIG', 'EA',
          'GE', 'HP', 'IHS', 'ICE', 'IQV', 'EOS', 'AEP', 'AGCO', 'AON', 'AVB', 'BIO', 'CVS', 'EIX', 'ETN', 'IDXX', 'ITW', 'KO', 'LOW', 'MCO',
          'NIO', 'ODFL', 'ORLY', 'OTIS', 'SEA', 'UNP', 'USB', 'AT&T', 'MRV', 'CVC', 'BTG', 'JBS', 'XP', 'BB', 'RNI', 'PDG', 'UOL'}


PALAVRAS_CURTAS = {'LOG', 'VIA', 'SUL', 'RIO', 'MAR', 'SOL', 'LAR', 'BEM', 'TOP', 'NEW', 'ONE', 'SEC', 'CAP', 'RE', 'MAX', 'PAR', 'ALZ'}


def nome_bonito(s, siglas3=False):
    """'PETRÓLEO BRASILEIRO S.A. - PETROBRAS' -> 'Petróleo Brasileiro - Petrobras'; 'META PLATFORMS. INC.' -> 'Meta Platforms'"""
    s = re.sub(r'\s*-?\s*EM RECUPERA[CÇ][AÃ]O JUDICIAL.*', '', s.strip(), flags=re.I)
    s = re.sub(SUFIXOS, ' ', s, flags=re.I)
    s = re.sub(r'[\s.,&-]+$', '', re.sub(r'^\s*[-.,]\s*', '', re.sub(r'\s+', ' ', s))).strip(' .,&')  # "JPMORGAN CHASE & CO" -> sem o & no fim
    s = re.sub(r'\s+([.,])', r'\1', s)
    out = []
    for i, w in enumerate(s.split(' ')):
        base = re.sub(r'[^\wÀ-ÿ]', '', w)
        if i and base.lower() in MINUSCULAS:
            out.append(w.lower())
        elif siglas3 and len(base) <= 3 and base.isalpha() and base.upper() not in PALAVRAS_CURTAS and base.lower() not in MINUSCULAS:
            out.append(w.upper())  # nome de FII: HSI Malls, VBI Prime, Valora CRI CDI
        elif base.upper() == base and (base.upper() in SIGLAS or w.upper().strip('.,') in SIGLAS or (2 <= len(base) <= 4 and base.isalpha() and not re.search('[AEIOUYÁÉÍÓÚÂÊÔÃÕ]', base.upper()))):
            out.append(w)  # sigla: WEG, BRF, TIM, EOG, CSHG
        elif re.fullmatch(r'(I{1,3}|IV|VI{0,3}|IX|X{1,3})', base.upper()) and i:
            out.append(base.upper() + w[len(base):])  # numero romano: TRX Real Estate II
        elif any(ch.isdigit() for ch in base):
            out.append(w)
        else:
            out.append('-'.join(p[:1].upper() + p[1:].lower() for p in w.split('-')))
    return ' '.join(out) or s


def nome_fii(s):
    """'MAXI RENDA FUNDO DE INVESTIMENTO IMOBILIARIO - FII' -> 'Maxi Renda'"""
    s = re.sub(r'\bRESPONSABIL\w*.*|\bRESP\b.*|CLASSE [ÚU]NICA.*|\bDE RESP\w*.*', ' ', s, flags=re.I)  # o resto do nome e juridiquês
    s = re.sub(r'FUNDO DE INVESTIMENTO IMOBILI[AÁ]RIO|\bFI IMOBILI[AÁ]RIO\b|\bFII\b|\bF\.I\.I\.?|\bLTDA\b|\bLIMITADA\b|\bRL\b', ' ', s, flags=re.I)
    return nome_bonito(re.sub(r'\s*-\s*', ' ', s), siglas3=True)


# ---------------------------------------------------------------- B3: o que foi negociado no ultimo mes
def pregoes():
    """{ticker: {isin, bdi, especi, nomres, ultimo, volume, dias}} do mercado a vista nos pregoes dos ultimos DIAS dias"""
    hoje = dt.date.today()
    out = {}
    d = hoje - dt.timedelta(days=DIAS)
    while d <= hoje:
        if d.weekday() < 5:
            z = A.baixar(f'https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{d:%d%m%Y}.ZIP', tentativas=2, timeout=120)
            if z and z[:2] == b'PK':
                with zipfile.ZipFile(io.BytesIO(z)) as zf:
                    for l in zf.read(zf.namelist()[0]).decode('latin-1').splitlines():
                        if not l.startswith('01') or l[24:27] != '010':
                            continue
                        t = l[12:24].strip()
                        x = out.setdefault(t, {'volume': 0.0, 'dias': 0})
                        x.update(isin=l[230:242], bdi=l[10:12], especi=l[39:49].strip(), nomres=l[27:39].strip(), ultimo=d.isoformat())
                        x['volume'] += int(l[170:188]) / 100
                        x['dias'] += 1
        d += dt.timedelta(days=1)
    print(f' B3: {len(out)} codigos negociados no mercado a vista nos ultimos {DIAS} dias')
    return out


def b3_paginas(metodo):
    def busca():
        res, p = [], 1
        while True:
            d = A.b3api(metodo, {'language': 'pt-br', 'pageNumber': p, 'pageSize': 120})
            res += d['results']
            if p >= d['page']['totalPages']:
                return res
            p += 1
    return A.em_cache(f'b3/{metodo}', 24 * 7, busca)


def cadastro_cvm():
    """{CNPJ: [nome social, nome comercial, setor]} das companhias abertas ativas (com acento)"""
    def busca():
        txt = A.baixar('https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv', timeout=120).decode('latin-1')
        return {r['CNPJ_CIA']: [r['DENOM_SOCIAL'], r['DENOM_COMERC'], r['SETOR_ATIV']]
                for r in csv.DictReader(io.StringIO(txt), delimiter=';') if r['SIT'] == 'ATIVO'}
    return A.em_cache('cvm/cadastro', 24 * 7, busca)


# ---------------------------------------------------------------- acoes
def acoes(neg):
    empresas = {r['issuingCompany']: r for r in b3_paginas('GetInitialCompanies') if r.get('type') == '1'}
    cad = cadastro_cvm()
    candidatos = []
    for t, p in neg.items():
        if p['isin'][6:9] != 'ACN' or p['bdi'] not in ('02', '06', '07', '08') or not re.fullmatch(r'[A-Z0-9]{4}\d{1,2}', t):
            continue
        em = empresas.get(t[:4])
        if not em or re.sub(r'\D', '', em.get('cnpj') or '') in ('', '0'):
            continue
        candidatos.append((t, p, em))
    detalhes = {}
    codigos = sorted({em['codeCVM'] for _, _, em in candidatos})

    def det(c):
        try:
            return c, A.b3api('GetDetail', {'codeCVM': c, 'language': 'pt-br'}, horas=24 * 30)
        except Exception as ex:
            print('  aviso: detalhe da B3 de', c, repr(ex)[:120])
            return c, {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        detalhes = dict(ex.map(det, codigos))
    # a B3 as vezes traz o CNPJ de uma filial (Tupy: /0003-00); os balancos da CVM estao no da matriz (/0001-49)
    por_raiz = defaultdict(list)
    for c in cad:
        por_raiz[c[:10]].append(c)
    out = []
    for t, p, em in candidatos:
        cnpj = fmt_cnpj(em['cnpj'])
        if cnpj not in cad and len(por_raiz.get(cnpj[:10], [])) == 1:
            cnpj = por_raiz[cnpj[:10]][0]
        social, comercial, setor_cvm = cad.get(cnpj, [em['companyName'], '', ''])
        classe = re.sub(r'\s*\.\s+', ', ', detalhes.get(em['codeCVM'], {}).get('industryClassification') or '')  # a B3 troca a virgula por ponto
        partes = [x.strip() for x in classe.split('/') if x.strip()]
        setor = partes[0] if partes else (setor_cvm or 'Outros')
        segmento = partes[-1] if partes else (setor_cvm or setor)
        e = {'ticker': t, 'tipo': 'acao', 'nome': nome_bonito(comercial or social or em['companyName']), 'razao': social or em['companyName'],
             'cnpj': cnpj, 'b3': t[:4], 'pregao': em['tradingName'], 'isin': p['isin'], 'setor': setor, 'segmento': segmento}
        if segmento == 'Bancos' or setor_cvm == 'Bancos':
            e['banco'] = True
        out.append(e)
    return out


# ---------------------------------------------------------------- FIIs
PAPEL = ('CRI', 'CRI_CRA', 'LCI', 'LCI_LCA', 'LIG', 'Letras_Hipotecarias')
TIJOLO = ('Direitos_Bens_Imoveis', 'Acoes_Sociedades_Atividades_FII', 'Cotas_Sociedades_Atividades_FII')


def informe_fii():
    """{ISIN: {cnpj, nome, segmento, tipo_fundo}} do informe mensal mais recente da CVM"""
    def busca():
        hoje = dt.date.today()
        por_isin, carteira = {}, {}
        for ano in (hoje.year - 1, hoje.year):  # o ano atual vence o anterior
            z = A.baixar(f'{A.FII_CVM}/inf_mensal_fii_{ano}.zip', timeout=300)
            if not z:
                continue
            with zipfile.ZipFile(io.BytesIO(z)) as zf:
                for nome in zf.namelist():
                    rd = csv.DictReader(io.StringIO(zf.read(nome).decode('latin-1')), delimiter=';')
                    if '_geral_' in nome:
                        for r in rd:
                            c = r.get('CNPJ_Fundo_Classe') or r.get('CNPJ_Fundo')
                            isin = (r.get('Codigo_ISIN') or '').strip()
                            if isin and (isin not in por_isin or r['Data_Referencia'] >= por_isin[isin]['_ref']):
                                por_isin[isin] = {'_ref': r['Data_Referencia'], 'cnpj': c, 'nome': r.get('Nome_Fundo_Classe') or r.get('Nome_Fundo') or '',
                                                  'segmento_cvm': (r.get('Segmento_Atuacao') or '').strip()}
                    elif '_ativo_passivo_' in nome:
                        for r in rd:
                            c = r.get('CNPJ_Fundo_Classe') or r.get('CNPJ_Fundo')
                            if c not in carteira or r['Data_Referencia'] >= carteira[c]['_ref']:
                                g = lambda ks: sum(A.fnum(r.get(k)) or 0 for k in ks)
                                carteira[c] = {'_ref': r['Data_Referencia'], 'papel': g(PAPEL), 'tijolo': g(TIJOLO), 'fof': g(('FII',)),
                                               'total': A.fnum(r.get('Total_Investido')) or 0}
        for x in por_isin.values():
            x['carteira'] = carteira.get(x['cnpj'])
        return por_isin
    return A.em_cache('cvm/informe_fii', 24 * 7, busca)


def tipo_fii(x):
    c = x.get('carteira') or {}
    soma = (c.get('papel') or 0) + (c.get('tijolo') or 0) + (c.get('fof') or 0)
    seg = x.get('segmento_cvm') or ''
    seg = '' if seg in ('Multicategoria', 'Outros', 'Híbrido') else seg
    if soma > 0:
        if c['papel'] / soma >= 0.6:
            return 'Papel', 'Fundo de papel (recebíveis)'
        if c['fof'] / soma >= 0.6:
            return 'Fundo de fundos', 'Fundo de fundos'
        if c['tijolo'] / soma >= 0.6:
            return seg or 'Renda urbana', 'Fundo de tijolo (imóveis)'
    return 'Híbrido', 'Fundo híbrido'


def fiis(neg):
    inf = informe_fii()
    out = []
    for t, p in neg.items():
        if p['isin'][6:9] != 'CTF' or p['bdi'] != '12' or not re.fullmatch(r'[A-Z0-9]{4}11', t):
            continue
        x = inf.get(p['isin'])
        if not x or not x.get('cnpj'):
            continue
        segmento, tipo = tipo_fii(x)
        out.append({'ticker': t, 'tipo': 'fii', 'nome': nome_fii(x['nome']) or t, 'cnpj': x['cnpj'], 'b3': t[:4], 'isin': p['isin'],
                    'setor': 'Fundo imobiliário', 'segmento': segmento, 'tipo_fundo': tipo})
    return out


# ---------------------------------------------------------------- BDRs
def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'[^A-Z0-9 ]', ' ', s)
    fora = {'INC', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 'COS', 'LTD', 'LIMITED', 'PLC', 'SA', 'S', 'A', 'N', 'V', 'NV', 'AG', 'SE', 'THE',
            'HOLDINGS', 'HOLDING', 'GROUP', 'CLASS', 'CL', 'COM', 'INCORPORATED', 'LLC', 'LP', 'DE', 'ADR', 'SPONSORED', 'NEW', 'PUBLIC'}
    return ' '.join(w for w in s.split() if w not in fora)


SIC = [  # (de, ate, setor, segmento)
    (100, 999, 'Agronegócio', 'Agropecuária'), (1000, 1299, 'Materiais básicos', 'Mineração'), (1300, 1389, 'Petróleo e gás', 'Exploração e serviços'),
    (1390, 1499, 'Materiais básicos', 'Mineração'), (1500, 1799, 'Bens industriais', 'Construção'), (2000, 2079, 'Consumo não cíclico', 'Alimentos'),
    (2080, 2099, 'Consumo não cíclico', 'Bebidas'), (2100, 2199, 'Consumo não cíclico', 'Tabaco'), (2200, 2399, 'Consumo cíclico', 'Tecidos e vestuário'),
    (2400, 2599, 'Materiais básicos', 'Madeira e móveis'), (2600, 2699, 'Materiais básicos', 'Papel e celulose'), (2700, 2799, 'Comunicações', 'Mídia e editoras'),
    (2800, 2829, 'Materiais básicos', 'Química'), (2830, 2836, 'Saúde', 'Farmacêutica e biotecnologia'), (2837, 2839, 'Materiais básicos', 'Química'),
    (2840, 2844, 'Consumo não cíclico', 'Higiene e limpeza'), (2845, 2899, 'Materiais básicos', 'Química'), (2900, 2999, 'Petróleo e gás', 'Refino'),
    (3000, 3299, 'Materiais básicos', 'Materiais diversos'), (3300, 3399, 'Materiais básicos', 'Siderurgia e metalurgia'),
    (3400, 3499, 'Bens industriais', 'Produtos de metal'), (3500, 3569, 'Bens industriais', 'Máquinas e equipamentos'),
    (3570, 3579, 'Tecnologia', 'Computadores e equipamentos'), (3580, 3599, 'Bens industriais', 'Máquinas e equipamentos'),
    (3600, 3669, 'Tecnologia', 'Equipamentos eletrônicos'), (3670, 3679, 'Tecnologia', 'Semicondutores'), (3680, 3699, 'Tecnologia', 'Equipamentos eletrônicos'),
    (3700, 3719, 'Consumo cíclico', 'Automóveis'), (3720, 3729, 'Bens industriais', 'Aeroespacial'), (3730, 3799, 'Bens industriais', 'Material de transporte'),
    (3800, 3839, 'Tecnologia', 'Instrumentos de medição'), (3840, 3851, 'Saúde', 'Equipamentos médicos'), (3852, 3999, 'Bens industriais', 'Outros industriais'),
    (4000, 4599, 'Bens industriais', 'Transporte'), (4600, 4699, 'Petróleo e gás', 'Oleodutos'), (4700, 4799, 'Bens industriais', 'Transporte'),
    (4800, 4899, 'Comunicações', 'Telecomunicações'), (4900, 4999, 'Utilidade pública', 'Energia, gás e saneamento'), (5000, 5199, 'Consumo cíclico', 'Atacado'),
    (5200, 5799, 'Consumo cíclico', 'Varejo'), (5800, 5899, 'Consumo cíclico', 'Restaurantes'), (5900, 5999, 'Consumo cíclico', 'Varejo'),
    (6000, 6199, 'Financeiro', 'Bancos'), (6200, 6299, 'Financeiro', 'Corretoras e bolsas'), (6300, 6499, 'Financeiro', 'Seguros'),
    (6500, 6797, 'Financeiro', 'Imóveis e holdings'), (6798, 6798, 'Financeiro', 'Fundos imobiliários (REIT)'), (6799, 6799, 'Financeiro', 'Imóveis e holdings'),
    (7000, 7099, 'Consumo cíclico', 'Hotéis e viagens'), (7370, 7379, 'Tecnologia', 'Software e serviços de internet'), (7800, 7999, 'Consumo cíclico', 'Entretenimento'),
    (7200, 7369, 'Bens industriais', 'Serviços'), (7380, 7399, 'Bens industriais', 'Serviços'), (8000, 8099, 'Saúde', 'Serviços de saúde'),
    (8200, 8299, 'Consumo cíclico', 'Educação'), (8700, 8799, 'Bens industriais', 'Serviços profissionais'),
]


def sic_setor(sic):
    try:
        n = int(sic)
    except (TypeError, ValueError):
        return 'Outros', 'Outros'
    return next(((s, g) for a, b, s, g in SIC if a <= n <= b), ('Outros', 'Outros'))


def tickers_sec():
    """lista da SEC (ticker, CIK, nome). Fica guardada: sem CONTATO_SEC a SEC recusa, e vale a ultima lista baixada."""
    return A.em_cache('sec/company_tickers', 24 * 7,
                      lambda: json.loads(A.baixar('https://www.sec.gov/files/company_tickers.json', headers={'User-Agent': A.UA_SEC}, timeout=60)))


# nome curto que o nome da B3 nao da (pelo codigo nos EUA)
NOMES_BDR = {'NU': 'Nubank', 'TSM': 'TSMC (Taiwan Semiconductor)', 'STNE': 'StoneCo', 'NVO': 'Novo Nordisk', 'PAGS': 'PagSeguro',
             'BABA': 'Alibaba', 'BIDU': 'Baidu', 'PDD': 'PDD (Temu)', 'INTR': 'Inter&Co', 'XP': 'XP Inc'}


def bdrs(neg):
    lista = {r['issuingCompany']: r for r in b3_paginas('GetCompaniesBDR') if r.get('codeCategoryBVMF') == '6'}
    sec = list(tickers_sec().values())
    por_nome, por_palavras, por_ticker = defaultdict(list), defaultdict(list), {}
    for v in sec:
        por_nome[norm(v['title'])].append(v)
        por_palavras[frozenset(norm(v['title']).split())].append(v)
        por_ticker[v['ticker']] = v

    def achar(em):
        """empresa americana do BDR: pelo nome; se nao achar, pelo codigo da B3 sem os numeros (VRTX, SCHW, ORLY...)"""
        n = norm(em['companyName'])
        cands = por_nome.get(n) or []
        if not cands:  # mesmas palavras em outra ordem: "T ROWE PRICE" na B3, "PRICE T ROWE" na SEC
            cands = por_palavras.get(frozenset(n.split())) or []
        if not cands:
            v = por_ticker.get(re.sub(r'\d', '', em['issuingCompany']))
            if v and norm(v['title']).split()[:1] == n.split()[:1]:
                cands = [v]
        if not cands:
            pre = [k for k in por_nome if n and (k.startswith(n + ' ') or n.startswith(k + ' ')) and len(k.split()) >= 2
                   and not re.search(r'\b(ETF|FUND|TRUST)\b', k)]  # nao confundir a empresa com um fundo de nome parecido
            if len(pre) == 1:
                cands = por_nome[pre[0]]
        if not cands:
            return None
        cod = re.sub(r'\d', '', em['issuingCompany'])
        # varias classes (GOOGL e GOOG): fica a que mais parece o codigo da B3. Codigo de 5 letras terminado em F e a acao
        # de fora negociada no balcao americano (BPPFF), sem dividendos no Yahoo: o ADR na bolsa (BP) vem antes
        return max(cands, key=lambda v: (not (len(v['ticker']) == 5 and v['ticker'].endswith('F')),
                                         len(os.path.commonprefix([v['ticker'], cod])), -len(v['ticker'])))

    candidatos = []
    for t, p in neg.items():
        if p['isin'][6:9] != 'BDR' or not re.fullmatch(r'[A-Z0-9]{4}3[1-5]', t):
            continue
        em = lista.get(t[:4])
        v = achar(em) if em else None
        if v:
            candidatos.append((t, p, em, str(v['cik_str']).zfill(10), v['ticker']))

    def sub(cik):
        try:
            return cik, A.sec_json(f'submissions/CIK{cik}.json', 72)
        except Exception as ex:
            print('  aviso: SEC', cik, repr(ex)[:120])
            return cik, None
    with ThreadPoolExecutor(max_workers=4) as ex:
        subs = dict(ex.map(sub, sorted({c[3] for c in candidatos})))
    out = []
    for t, p, em, cik, us in candidatos:
        s = subs.get(cik)
        formas = set(s['filings']['recent']['form']) if s else set()
        if formas & {'10-K', '10-Q'}:
            estrangeira = False  # balanco da SEC (10-K/10-Q, US GAAP)
        elif formas & {'20-F', '20-F/A', '40-F'}:
            estrangeira = True  # empresa de fora dos EUA (TSMC, Nubank...): balanco pelo Yahoo, que traz os trimestres (veja fin_estrangeira)
        else:
            continue  # sem balanco na SEC
        setor, segmento = sic_setor(s.get('sic'))
        e = {'ticker': t, 'tipo': 'bdr', 'nome': NOMES_BDR.get(us) or nome_bonito(em['companyName']), 'razao': em['companyName'], 'b3': t[:4],
             'cik': cik, 'us': us, 'isin': p['isin'], 'setor': setor, 'segmento': segmento}
        if estrangeira:
            e['estrangeira'] = True
        out.append(e)
    return out


# ---------------------------------------------------------------- ETFs (fundos de indice)
ETF_TIPOS = [  # pelo nome do fundo; o que nao casar fica so "ETF"
    (r'BITCOIN|CRIPTO|CRYPTO|ETHER|SOLANA|\bHASH|\bBLOCKCHAIN|\bXRP\b|\bDEFI\b|\bWEB3\b', 'Criptoativos'),
    (r'\bOURO\b|\bGOLD\b', 'Ouro'),
    (r'IMA-?B|\bIRF-?M\b|\bIDKA\b|TESOURO|RENDA FIXA|\bDEB[EÊ]NTURE|\bIMA\b|\bCDI\b|\bSELIC\b|\bPRE\b|INFLA[CÇ]|CREDITO PRIVADO|CRÉDITO PRIVADO', 'Renda fixa'),
    (r'S&P|NASDAQ|\bMSCI\b|EUROPA|EUROPE|CHINA|JAP[AÃ]O|JAPAN|\bEUA\b|\bUSA\b|GLOBAL|MUNDO|WORLD|EXTERIOR|EMERGENT|\bIE\b|INVESTIMENTO NO EXTERIOR|INTERNACIONAL', 'Exterior'),
]
SIGLAS_ETF = {'S&P', 'MSCI', 'ETF', 'ESG', 'BTG', 'XP', 'BB', 'IT', 'IA', 'AI', 'EUA', 'USA', 'IMA-B', 'IRF-M', 'IDKA', 'CDI', 'IPCA', 'IBOV', 'SMLL',
              'IDIV', 'IFIX', 'B3', 'BR', 'II', 'III', 'IV', 'NTN-B', 'DI', 'GPS', 'REIT', 'REITS', 'FTSE', 'PIMCO', 'BNP', 'UBS', 'JPM', 'AUVP'}


def nome_etf(longo, curto):
    """nome do ETF a partir do nome longo do Yahoo: "ISHARES S&P 500 CLASSE DE INDICE ..." vira "iShares S&P 500"."""
    s = (longo or curto or '').strip()
    s = re.split(r'\s+(?:-\s+)?(?:CLASSE|FUNDO|FDO|FI|FIC|FICFI|FUND)\b|\s+-\s+', s, maxsplit=1, flags=re.I)[0].strip(' -.,')
    pal = []
    for w in s.split():
        u = w.upper()
        pal.append('iShares' if u == 'ISHARES' else u if u in SIGLAS_ETF or re.search(r'\d', u) and len(u) <= 6 else w.capitalize())
    return ' '.join(pal) or curto


def etfs(neg):
    """fundos de indice (CODBDI 14 no arquivo da B3): nome pelo Yahoo, guardado por uma semana"""
    cands = sorted(t for t, p in neg.items() if p['bdi'] == '14' and p['isin'][6:9] == 'CTF' and re.fullmatch(r'[A-Z0-9]{4}1[1-3]', t))

    def meta(t):
        try:
            m = A.em_cache(f'yahoo/meta_{t}', 24 * 7, lambda: json.loads(A.baixar(
                f'https://query1.finance.yahoo.com/v8/finance/chart/{t}.SA?range=5d&interval=1d', headers={'User-Agent': 'Mozilla/5.0'}, timeout=30))['chart']['result'][0]['meta'])
            return t, m
        except Exception as ex:
            print('  aviso: Yahoo sem o nome de', t, repr(ex)[:100])
            return t, {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        metas = dict(ex.map(meta, cands))
    out = []
    for t in cands:
        m = metas.get(t) or {}
        longo = (m.get('longName') or '').strip()
        nome = nome_etf(longo, (m.get('shortName') or neg[t].get('nomres') or t).strip())
        alvo = (longo or nome).upper()
        segmento = next((g for rx, g in ETF_TIPOS if re.search(rx, alvo)), 'Ações Brasil' if re.search(r'IBOV|BOVESPA|SMALL|SMLL|DIVIDEND|IDIV|BRASIL|\bB3\b', alvo) else 'ETF')
        out.append({'ticker': t, 'tipo': 'etf', 'nome': nome, 'razao': longo.title() if longo else nome, 'b3': t[:4], 'isin': neg[t]['isin'],
                    'setor': 'ETF', 'segmento': segmento})
    return out


def main():
    if os.path.exists(ARQ) and '--forcar' not in sys.argv:
        guardada = json.load(open(ARQ, encoding='utf-8'))
        idade = (time.time() - guardada.get('_em', 0)) / 86400
        if idade < 7 and guardada.get('versao') == VERSAO:
            print(f'universo.json tem {idade:.1f} dia(s): fica como esta (use --forcar para refazer)')
            return
    inicio = time.time()
    neg = pregoes()
    if len(neg) < 500:
        sys.exit('a B3 trouxe poucos pregoes; a lista anterior continua valendo')
    partes = {}
    for nome, func in (('acoes', acoes), ('FIIs', fiis), ('BDRs', bdrs), ('ETFs', etfs)):
        try:
            partes[nome] = func(neg)
            print(f' {nome}: {len(partes[nome])}')
        except Exception as ex:  # uma fonte fora do ar: essa parte fica como estava na lista anterior
            print(f' ERRO montando {nome}: {ex!r}')
            partes[nome] = None
    if any(v is None for v in partes.values()) and os.path.exists(ARQ):
        antes = json.load(open(ARQ, encoding='utf-8'))['ativos']
        tipo = {'acoes': 'acao', 'FIIs': 'fii', 'BDRs': 'bdr', 'ETFs': 'etf'}
        for nome, v in partes.items():
            if v is None:
                partes[nome] = [e for e in antes if e['tipo'] == tipo[nome]]
    ativos = [e for v in partes.values() for e in (v or [])]
    # os mais negociados primeiro (a primeira carga do robo comeca por eles)
    ativos.sort(key=lambda e: -neg.get(e['ticker'], {}).get('volume', 0))
    A.gravar_atomico(ARQ, json.dumps({'_em': time.time(), 'versao': VERSAO, 'gerado': dt.date.today().isoformat(), 'ativos': ativos},
                                     ensure_ascii=False, indent=0))
    print(f'universo.json: {len(ativos)} ativos em {round(time.time() - inicio)} s')


if __name__ == '__main__':
    main()
