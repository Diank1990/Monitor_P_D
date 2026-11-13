#!/usr/bin/env python3
"""
Monitor do painel público FINEP – Subvenção Econômica à Inovação em Fluxo Contínuo.

A cada execução:
  1. consulta o painel Power BI público (a mesma fonte do link da FINEP);
  2. compara com a versão anterior salva em data/atual.json;
  3. se algo mudou, registra as alterações em data/alteracoes.json, guarda a versão
     anterior em data/versoes/ e regera index.html.
Se nada mudou nos dados, apenas regera index.html (para refletir mudanças em regras.json ou modelo.html).
"""
import base64, datetime, gzip, hashlib, json, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

PAINEL_URL = ("https://app.powerbi.com/view?r=eyJrIjoiYWFlMWVmMDAtMGQyZS00NjFiLTk1OWItY2U4NzVmMzMzZWJlIiwidCI6"
              "IjBlNjcyMWViLTczMDUtNDE2YS1hZDJiLWEyNDAwM2EwY2Q2OCJ9")
RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "data"
CLUSTERS_RESERVA = ["wabi-brazil-south-b-primary-api", "wabi-brazil-south-api",
                    "wabi-brazil-south-b-api", "wabi-us-north-central-api", "wabi-west-us-api"]
TIMEOUT = 120


# ----------------------------------------------------------------------------- Power BI
class PowerBI:
    def __init__(self, url):
        r = parse_qs(urlparse(url).query)["r"][0]
        r += "=" * (-len(r) % 4)
        cfg = json.loads(base64.b64decode(r))
        self.chave, self.tenant = cfg["k"], cfg["t"]
        self.h = {"X-PowerBI-ResourceKey": self.chave, "Accept": "application/json",
                  "Content-Type": "application/json;charset=UTF-8"}
        self.host, modelo = self._descobrir()
        self.model_id = modelo["models"][0]["id"]
        self.dataset = modelo["models"][0]["dbName"]
        self.report_id = modelo["exploration"]["reportId"]

    def _descobrir(self):
        hosts = []
        try:
            u = requests.get(f"https://api.powerbi.com/public/routing/cluster/{self.tenant}", timeout=30).json()
            h = urlparse(u["FixedClusterUri"]).netloc.replace("-redirect.", "-api.").replace("global-", "")
            hosts.append(h)
        except Exception:
            pass
        hosts += [f"{c}.analysis.windows.net" for c in CLUSTERS_RESERVA]
        for h in dict.fromkeys(hosts):
            try:
                r = requests.get(f"https://{h}/public/reports/{self.chave}/modelsAndExploration?preferReadOnlySession=true",
                                 headers=self.h, timeout=TIMEOUT)
                if r.ok and "models" in r.json():
                    return h, r.json()
            except Exception:
                continue
        raise RuntimeError("Não foi possível localizar o servidor do painel Power BI.")

    def consultar(self, origens, campos, filtros, ordem=None, janela=5000):
        sel = []
        for i, (tipo, origem, prop, *extra) in enumerate(campos):
            ref = {"Column": {"Expression": {"SourceRef": {"Source": origem}}, "Property": prop}}
            if tipo == "medida":
                ref = {"Measure": {"Expression": {"SourceRef": {"Source": origem}}, "Property": prop}}
            elif tipo == "agregado":
                ref = {"Aggregation": {"Expression": ref, "Function": extra[0]}}
            sel.append({**ref, "Name": f"c{i}"})
        consulta = {"Version": 2, "From": [{"Name": a, "Entity": e, "Type": 0} for a, e in origens.items()],
                    "Select": sel, "Where": filtros}
        if ordem:
            consulta["OrderBy"] = [{"Direction": 1, "Expression": {"Column": {
                "Expression": {"SourceRef": {"Source": ordem[0]}}, "Property": ordem[1]}}}]
        linhas, reinicio = [], None
        while True:
            janela_cfg = {"Count": janela}
            if reinicio:
                janela_cfg["RestartTokens"] = reinicio
            corpo = {"version": "1.0.0", "cancelQueries": [], "modelId": self.model_id, "queries": [{
                "Query": {"Commands": [{"SemanticQueryDataShapeCommand": {
                    "Query": consulta,
                    "Binding": {"Primary": {"Groupings": [{"Projections": list(range(len(sel)))}]},
                                "DataReduction": {"DataVolume": 3, "Primary": {"Window": janela_cfg}}, "Version": 1},
                    "ExecutionMetricsKind": 1}}]},
                "QueryId": "", "ApplicationContext": {"DatasetId": self.dataset, "Sources": [{"ReportId": self.report_id}]}}]}
            r = requests.post(f"https://{self.host}/public/reports/querydata?synchronous=true",
                              headers=self.h, data=json.dumps(corpo), timeout=TIMEOUT)
            r.raise_for_status()
            novas, reinicio = self._decodificar(r.json())
            linhas += novas
            if not reinicio:
                return linhas

    @staticmethod
    def _decodificar(resp):
        dsr = resp["results"][0]["result"]["data"]["dsr"]
        if "DataShapes" in dsr:
            raise RuntimeError(json.dumps(dsr["DataShapes"], ensure_ascii=False)[:800])
        ds = dsr["DS"][0]
        dic = ds.get("ValueDicts", {})
        dm = next((v for ph in ds["PH"] for k, v in ph.items() if k.startswith("DM")), [])
        esquema, anterior, linhas = None, None, []
        for item in dm:
            esquema = item.get("S", esquema)
            rep, nulos, comp = item.get("R", 0), item.get("Ø", 0), iter(item.get("C", []))
            vals = []
            for i, s in enumerate(esquema):
                if rep & (1 << i):
                    v = anterior[i]
                elif nulos & (1 << i):
                    v = None
                else:
                    v = item[s["N"]] if s["N"] in item else next(comp)
                    if "DN" in s and isinstance(v, int):
                        v = dic[s["DN"]][v]
                vals.append(v)
            anterior = vals
            linhas.append(vals)
        return linhas, ds.get("RT")


def condicao(origem, prop, valores, negar=False):
    c = {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": origem}}, "Property": prop}}],
                "Values": [[{"Literal": {"Value": "'" + v.replace("'", "''") + "'"}}] for v in valores]}}
    return {"Condition": {"Not": {"Expression": c}} if negar else c}


def num(v):
    return None if v in (None, "") else round(float(v), 2)


def txt(v):
    return None if v is None else str(v).strip()


# ----------------------------------------------------------------------------- Extração
def extrair():
    pbi = PowerBI(PAINEL_URL)
    base = lambda a: [condicao(a, "INSTRUMENTO", ["Subvenção Direta"]), condicao(a, "FORMASELECAOPROJ", ["FLUXO_CONTINUO"])]
    D, P, E, A, M = "T_SISGON_DEMANDA", "T_SISGON_PROJETO", "T_APLA_REL_SUBV_SISGON_ENTRADA", "Propostas em análise", "Medidas"

    nomes = [l[0] for l in pbi.consultar({"d": D}, [("coluna", "d", "NOMECURTO")], base("d"))]
    atualizado = pbi.consultar({"m": M, "d": D}, [("medida", "m", "Última Atualização")], base("d"))[0][0]
    painel_data = datetime.datetime.fromtimestamp(atualizado / 1000, datetime.timezone.utc).date().isoformat()

    editais, propostas = {}, []
    for ed in sorted(nomes):
        filtro = base("d") + [condicao("d", "NOMECURTO", [ed])]
        titulo, orcamento = pbi.consultar({"d": D}, [("agregado", "d", "TITULO", 3), ("agregado", "d", "VALORTR", 0)], filtro)[0]
        editais[ed] = {"titulo": txt(titulo), "orcamento_total": num(orcamento)}
        org = {"p": P, "e": E, "d": D}
        for l in pbi.consultar(org, [("coluna", "p", "REFE"), ("coluna", "e", "CNPJ Proponente"),
                                     ("coluna", "e", "Razão Social Proponente"), ("coluna", "e", "Linha Temática"),
                                     ("coluna", "e", "UF do projeto"), ("coluna", "p", "VALORFINEP"),
                                     ("coluna", "p", "STATUSPROJETO"), ("coluna", "p", "RESUMOPUBLICAVEL")],
                               filtro + [condicao("p", "STATUSPROJETO", ["Em análise", "Indeferido", "Reprovado"], True)],
                               ("p", "REFE")):
            propostas.append({"edital": ed, "ref": txt(l[0]), "cnpj": txt(l[1]), "proponente": txt(l[2]), "linha": txt(l[3]),
                              "uf": txt(l[4]), "situacao": "Aprovado", "status": txt(l[6]), "fase": None,
                              "valor_aprovado": num(l[5]), "valor_solicitado": None, "resumo": txt(l[7])})
        for l in pbi.consultar(org, [("coluna", "p", "REFE"), ("coluna", "e", "CNPJ Proponente"),
                                     ("coluna", "e", "Razão Social Proponente"), ("coluna", "e", "Linha Temática"),
                                     ("coluna", "e", "UF do projeto"), ("coluna", "p", "VALORFINEPSOLIC"),
                                     ("coluna", "p", "STATUSPROJETO")],
                               filtro + [condicao("p", "STATUSPROJETO", ["Indeferido", "Reprovado"])], ("p", "REFE")):
            propostas.append({"edital": ed, "ref": txt(l[0]), "cnpj": txt(l[1]), "proponente": txt(l[2]), "linha": txt(l[3]),
                              "uf": txt(l[4]), "situacao": txt(l[6]), "status": txt(l[6]), "fase": None,
                              "valor_aprovado": None, "valor_solicitado": num(l[5]), "resumo": None})
        for l in pbi.consultar({"a": A, "d": D}, [("coluna", "a", c) for c in
                               ["Ref.", "CNPJ", "Proponente", "Linha Temática", "UF do projeto", "Valor Finep Solicitado", "Fase", "Status"]],
                               filtro + [condicao("a", "Status", ["Em análise", "Enviado"])], ("a", "Ref.")):
            propostas.append({"edital": ed, "ref": txt(l[0]), "cnpj": txt(l[1]), "proponente": txt(l[2]), "linha": txt(l[3]),
                              "uf": txt(l[4]), "situacao": "Em análise", "status": txt(l[7]), "fase": txt(l[6]),
                              "valor_aprovado": None, "valor_solicitado": num(l[5]), "resumo": None})
    if not propostas:
        raise RuntimeError("O painel não retornou propostas; nada foi gravado.")
    return {"painel_atualizado_em": painel_data, "editais": editais, "propostas": propostas}


def indicadores(snap):
    out = {}
    for ed, info in snap["editais"].items():
        ps = [p for p in snap["propostas"] if p["edital"] == ed]
        aprov = round(sum(p["valor_aprovado"] or 0 for p in ps if p["situacao"] == "Aprovado"), 2)
        total = info["orcamento_total"] or 0
        out[ed] = {"orcamento_total": total, "valor_aprovado": aprov, "orcamento_disponivel": round(total - aprov, 2),
                   "aprovados": sum(p["situacao"] == "Aprovado" for p in ps),
                   "nao_aprovados": sum(p["situacao"] in ("Indeferido", "Reprovado") for p in ps),
                   "em_analise": sum(p["situacao"] == "Em análise" for p in ps),
                   "demanda_em_analise": round(sum(p["valor_solicitado"] or 0 for p in ps if p["situacao"] == "Em análise"), 2)}
    return out


# ----------------------------------------------------------------------------- Comparação
def comparar(ant, novo, data_exec):
    ev = []
    def add(tipo, p, de=None, para=None, ref=None):
        ev.append({"data": data_exec, "painel": novo["painel_atualizado_em"], "edital": p["edital"],
                   "ref": ref or p["ref"], "cnpj": p["cnpj"], "proponente": p["proponente"], "tipo": tipo, "de": de, "para": para})

    for ed in novo["editais"]:
        if ed not in ant["editais"]:
            ev.append({"data": data_exec, "painel": novo["painel_atualizado_em"], "edital": ed, "ref": None, "cnpj": None,
                       "proponente": None, "tipo": "Novo edital", "de": None, "para": novo["editais"][ed]["titulo"]})
        elif ant["editais"][ed]["orcamento_total"] != novo["editais"][ed]["orcamento_total"]:
            ev.append({"data": data_exec, "painel": novo["painel_atualizado_em"], "edital": ed, "ref": None, "cnpj": None,
                       "proponente": None, "tipo": "Orçamento do edital alterado",
                       "de": ant["editais"][ed]["orcamento_total"], "para": novo["editais"][ed]["orcamento_total"]})
    for ed in ant["editais"]:
        if ed not in novo["editais"]:
            ev.append({"data": data_exec, "painel": novo["painel_atualizado_em"], "edital": ed, "ref": None, "cnpj": None,
                       "proponente": None, "tipo": "Edital retirado do painel", "de": ant["editais"][ed]["titulo"], "para": None})

    A = {(p["edital"], p["ref"]): p for p in ant["propostas"]}
    N = {(p["edital"], p["ref"]): p for p in novo["propostas"]}
    sairam = [k for k in A if k not in N]
    entraram = [k for k in N if k not in A]
    pares = [(k, k) for k in A if k in N]

    # Propostas que trocaram o identificador provisório (#...) pelo número de referência
    sim = lambda p, q: p["cnpj"] == q["cnpj"] and p["linha"] == q["linha"]
    for k in [k for k in sairam if k[1] and k[1].startswith("#")]:
        cands = [n for n in entraram if n[0] == k[0] and not n[1].startswith("#") and sim(A[k], N[n])]
        rivais = [r for r in sairam if r != k and r[0] == k[0] and r[1].startswith("#") and sim(A[r], A[k])]
        if len(cands) == 1 and not rivais:
            n = cands[0]
            add("Número de referência atribuído", N[n], k[1], n[1])
            pares.append((k, n)); sairam.remove(k); entraram.remove(n)

    for k in entraram:
        p = N[k]
        add("Incluída no painel", p, None, p["situacao"] + (f" ({p['fase']})" if p["fase"] else ""))
    for k in sairam:
        p = A[k]
        add("Proposta retirada do painel", p, p["situacao"] + (f" ({p['fase']})" if p["fase"] else ""), None)

    for ka, kn in pares:
        a, n = A[ka], N[kn]
        if a["situacao"] != n["situacao"]:
            para = n["situacao"] + (f" ({n['status']})" if n["situacao"] == "Aprovado" and n["status"] else "")
            if n["situacao"] == "Aprovado" and n["valor_aprovado"] is not None:
                para += f" – valor aprovado {n['valor_aprovado']:.2f}"
            add("Mudança de situação", n, a["situacao"] + (f" ({a['fase']})" if a["fase"] else ""), para)
        else:
            if a["status"] != n["status"] and a["situacao"] != "Indeferido" and a["situacao"] != "Reprovado":
                add("Mudança de status", n, a["status"], n["status"])
            if a["fase"] != n["fase"]:
                add("Mudança de fase", n, a["fase"], n["fase"])
            for campo, rot in (("valor_aprovado", "Valor aprovado alterado"), ("valor_solicitado", "Valor solicitado alterado")):
                if a[campo] != n[campo]:
                    add(rot, n, a[campo], n[campo])
        for campo, rot in (("proponente", "Razão social"), ("cnpj", "CNPJ"), ("linha", "Linha temática"), ("uf", "UF")):
            if a[campo] != n[campo]:
                add(f"{rot} alterado(a)", n, a[campo], n[campo])
        if a["resumo"] and n["resumo"] and a["resumo"] != n["resumo"]:
            add("Resumo publicável alterado", n)
    return ev


# ----------------------------------------------------------------------------- Gravação
def ler(nome, padrao):
    f = DADOS / nome
    return json.loads(f.read_text("utf-8")) if f.exists() else padrao


def gravar(nome, obj):
    (DADOS / nome).write_text(json.dumps(obj, ensure_ascii=False, indent=1), "utf-8")


def impressao(snap):
    return hashlib.sha256(json.dumps(snap, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def gerar_html():
    modelo = (RAIZ / "modelo.html").read_text("utf-8")
    regras = RAIZ / "regras.json"
    pacote = {"atual": ler("atual.json", None), "alteracoes": ler("alteracoes.json", {}), "historico": ler("historico.json", []),
              "regras": json.loads(regras.read_text("utf-8")) if regras.exists() else {}}
    js = json.dumps(pacote, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    (RAIZ / "index.html").write_text(modelo.replace("/*__DADOS__*/null", js), "utf-8")


def main():
    DADOS.mkdir(exist_ok=True)
    agora = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
    data_exec = agora.strftime("%Y-%m-%d %H:%M")
    novo = extrair()
    anterior = ler("atual.json", None)
    if anterior and impressao({k: anterior[k] for k in ("painel_atualizado_em", "editais", "propostas")}) == impressao(novo):
        gerar_html()
        print(f"{data_exec}: nenhuma alteração no painel (atualizado em {novo['painel_atualizado_em']}).")
        return

    registro = ler("alteracoes.json", {"execucoes": [], "eventos": []})
    if anterior:
        eventos = comparar(anterior, novo, data_exec)
        (DADOS / "versoes").mkdir(exist_ok=True)
        nome = f"{anterior['painel_atualizado_em']}_{anterior['coletado_em'][:10]}.json.gz"
        with gzip.open(DADOS / "versoes" / nome, "wt", encoding="utf-8") as f:
            json.dump(anterior, f, ensure_ascii=False)
    else:
        eventos = []
    registro["execucoes"].insert(0, {"data": data_exec, "painel": novo["painel_atualizado_em"],
                                     "alteracoes": len(eventos), "carga_inicial": anterior is None})
    registro["eventos"] = eventos + registro["eventos"]
    novo["coletado_em"] = data_exec
    historico = ler("historico.json", [])
    historico.insert(0, {"data": data_exec, "painel": novo["painel_atualizado_em"], "editais": indicadores(novo)})

    gravar("atual.json", novo); gravar("alteracoes.json", registro); gravar("historico.json", historico)
    gerar_html()
    print(f"{data_exec}: {len(novo['propostas'])} propostas, {len(eventos)} alterações registradas.")


if __name__ == "__main__":
    if "--so-html" in sys.argv:
        gerar_html()
    else:
        main()
