#!/usr/bin/env python3
"""Robo do Tesouro Direto: grava dados/tesouro.json, que a pagina tesouro.html le.

Baixa (tudo publico, sem chave):
  - Tesouro Transparente: taxas e precos de todos os titulos do Tesouro Direto (arquivo de ~15 MB)
  - Banco Central SGS: CDI, Selic, poupanca, IPCA
  - Banco Central Focus: mediana do mercado para Selic e IPCA (usada nas simulacoes)

O GitHub Actions roda isto todo dia util, junto com o atualizar.py. Se alguma fonte falhar,
o arquivo de ontem fica como esta. Uso: python tesouro.py   (so biblioteca padrao do Python)
"""
import csv, io, json, os, statistics, sys, time, urllib.request, datetime as dt

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, 'dados', 'tesouro.json')
INICIO_SERIES = '01/01/2015'
ANOS_TESOURO = 5
UA = 'ComunidadeInvest dados-publicos'
TESOURO_CSV = ('https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/'
               'resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv')


def baixar(url, tentativas=4, timeout=240):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if i == tentativas - 1:
                raise
            print('  tentando de novo:', e)
            time.sleep(3 * (i + 1))


def sgs(codigo, ultimos=None, inicio=None):
    base = f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados'
    url = f'{base}/ultimos/{ultimos}?formato=json' if ultimos else f'{base}?formato=json&dataInicial={inicio}'
    out = [(dt.datetime.strptime(x['data'], '%d/%m/%Y').date(), float(x['valor'])) for x in json.loads(baixar(url, timeout=60))]
    return sorted(out)


def mensal(codigo, hoje):
    """serie mensal (%), sem o mes corrente (ainda pela metade)"""
    corte = hoje.replace(day=1)
    return [(d.strftime('%Y-%m'), v) for d, v in sgs(codigo, inicio=INICIO_SERIES) if d < corte]


def focus():
    q = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais?"
         "$top=40&$filter=(Indicador%20eq%20'Selic'%20or%20Indicador%20eq%20'IPCA')%20and%20baseCalculo%20eq%200"
         "&$orderby=Data%20desc&$format=json&$select=Indicador,Data,DataReferencia,Mediana")
    v = json.loads(baixar(q, timeout=60))['value']
    ult = max(x['Data'] for x in v)
    out = {'data': ult, 'selic': {}, 'ipca': {}}
    for x in v:
        if x['Data'] == ult:
            out[x['Indicador'].lower()][x['DataReferencia']] = round(x['Mediana'], 2)
    return out


def tesouro():
    raw = baixar(TESOURO_CSV).decode('latin-1')
    num = lambda s: float(s.replace('.', '').replace(',', '.')) if s.strip() else None
    dia = lambda s: dt.datetime.strptime(s, '%d/%m/%Y').date()
    linhas = []
    for r in csv.DictReader(io.StringIO(raw), delimiter=';'):
        linhas.append((dia(r['Data Base']), r['Tipo Titulo'], dia(r['Data Vencimento']),
                       num(r['Taxa Compra Manha']), num(r['Taxa Venda Manha']),
                       num(r['PU Compra Manha']), num(r['PU Venda Manha'])))
    ultimo = max(l[0] for l in linhas)
    hoje_l = [l for l in linhas if l[0] == ultimo and l[5]]  # a venda hoje = tem preco de compra no ultimo dia
    chaves = {(l[1], l[2]) for l in hoje_l}
    # historico: ultimo dia util de cada mes nos ultimos N anos
    ini = ultimo.replace(year=ultimo.year - ANOS_TESOURO)
    fim_mes = {}
    for l in linhas:
        if l[0] >= ini:
            k = l[0].strftime('%Y-%m')
            if l[0] > fim_mes.get(k, dt.date.min):
                fim_mes[k] = l[0]
    datas_hist = sorted(fim_mes.values())
    if datas_hist[-1] != ultimo:
        datas_hist.append(ultimo)
    idx = {d: i for i, d in enumerate(datas_hist)}
    hist = {k: [None] * len(datas_hist) for k in chaves}
    for l in linhas:
        k = (l[1], l[2])
        if k in hist and l[0] in idx:
            hist[k][idx[l[0]]] = l[3]
    titulos = []
    for l in sorted(hoje_l, key=lambda l: (l[1], l[2])):
        h = hist[(l[1], l[2])]
        validos = [x for x in h if x is not None]
        titulos.append({
            'tipo': l[1], 'vencimento': l[2].isoformat(),
            'taxa_compra': l[3], 'taxa_venda': l[4], 'pu_compra': l[5], 'pu_venda': l[6], 'hist': h,
            'min5': min(validos) if validos else None, 'max5': max(validos) if validos else None,
            'media5': round(statistics.mean(validos), 2) if validos else None,
            # % dos fins de mes em que a taxa esteve MAIS BAIXA que hoje (taxa alta = bom para quem compra)
            'pct_abaixo': round(100 * sum(1 for x in validos if x < l[3]) / len(validos)) if validos else None,
        })
    return {'data': ultimo.isoformat(), 'datas': [d.isoformat() for d in datas_hist], 'titulos': titulos}


def main():
    hoje = dt.date.today()
    print('Banco Central (SGS)...')
    cdi_aa = sgs(4389, ultimos=10)[-1]
    selic_meta = [x for x in sgs(432, inicio=(hoje - dt.timedelta(days=40)).strftime('%d/%m/%Y')) if x[0] <= hoje][-1]
    selic_over = sgs(1178, ultimos=10)[-1]
    poup = sgs(195, ultimos=10)[-1]
    ipca12 = sgs(13522, ultimos=10)[-1]
    cdi_mes = mensal(4391, hoje)
    ipca_mes = dict(mensal(433, hoje))
    print('Focus...')
    fc = focus()
    print('Tesouro Direto (arquivo de ~15 MB)...')
    td = tesouro()
    dados = {
        'atualizado': td['data'],
        'taxas': {
            'cdi_aa': cdi_aa[1], 'cdi_data': cdi_aa[0].isoformat(),
            'selic_meta': selic_meta[1], 'selic_over': selic_over[1],
            'poupanca_am': poup[1], 'poupanca_data': poup[0].isoformat(),
            'ipca_12m': ipca12[1], 'ipca_12m_ref': ipca12[0].strftime('%Y-%m'),
        },
        'focus': fc,
        'series': {'meses': [m for m, _ in cdi_mes], 'cdi': [v for _, v in cdi_mes], 'ipca': [ipca_mes.get(m) for m, _ in cdi_mes]},
        'tesouro': td,
        'dividas': None,
        'fontes': [
            {'texto': 'Banco Central do Brasil, SGS (CDI 4389 e 4391, Selic 432 e 1178, poupança 195, IPCA 433 e 13522)', 'url': 'https://www3.bcb.gov.br/sgspub/'},
            {'texto': 'Banco Central do Brasil, Focus (expectativas de mercado)', 'url': 'https://www.bcb.gov.br/publicacoes/focus'},
            {'texto': 'Tesouro Transparente, preços e taxas do Tesouro Direto', 'url': 'https://www.tesourotransparente.gov.br/ckan/dataset/taxas-dos-titulos-ofertados-pelo-tesouro-direto'},
        ],
    }
    novo = json.dumps(dados, ensure_ascii=False, separators=(',', ':'))
    if os.path.exists(SAIDA) and open(SAIDA, encoding='utf-8').read() == novo:
        print('Tesouro: nada mudou')
        return
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    open(SAIDA, 'w', encoding='utf-8').write(novo)
    t = dados['taxas']
    print(f"ok Tesouro de {td['data']}: {len(td['titulos'])} títulos; CDI {t['cdi_aa']}%, Selic {t['selic_meta']}%")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:  # mantem o tesouro.json de ontem
        sys.exit(f'ERRO no Tesouro (ficou o arquivo de ontem): {e!r}')
