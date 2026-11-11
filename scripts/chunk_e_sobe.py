"""Chunking do PDF 'ouro vturb' -> embeddings e5 locais -> Firestore (scraping-renda / RAG-OURO-VTURB).

Uso (de dentro de backend/):
    uv run python ../scripts/chunk_e_sobe.py "C:/Users/ryanr/Documents/ouro vturb.pdf"            # chunk + embed + sobe
    uv run python ../scripts/chunk_e_sobe.py "<pdf>" --so-chunks                                    # só gera dados/chunks.json

Processo:
1. pdftotext -layout (mantém as tabelas alinhadas). Cada página perde o cabeçalho corrido (= capítulo) e o número.
2. Linhas com colunas (3+ espaços no meio) viram linhas de tabela "a | b | c"; o resto é prosa, reflowada,
   com a hifenização desfeita.
3. Parágrafos são agrupados em chunks de ~1400 caracteres (máx. 1800), quebrando de preferência num título
   ("Padrão N —", títulos curtos). Cada chunk carrega capítulo, seção e páginas, e repete o último parágrafo
   curto do anterior (sobreposição) para não cortar contexto.
4. Embedding: intfloat/multilingual-e5-large (1024 dim, normalizado, prefixo "passage: "), o mesmo modelo do
   agente-criativo. O texto embedado leva "Capítulo / Seção" na frente.
5. Firestore: um documento por chunk (chunk_0001...), campo `embedding` como Vector, para busca com find_nearest.
   A coleção é apagada e recriada a cada rodada (idempotente).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ALVO = 1400
MAXIMO = 1800
SOBREPOSICAO_MAX = 400
COLECAO = "RAG-OURO-VTURB"
PROJETO = "scraping-renda"
MODELO = "intfloat/multilingual-e5-large"
FONTE = "ouro vturb.pdf — Engenharia reversa de 165 entrevistas (Segredos da Escala / VTurb), ago/2026"

GAP = re.compile(r"\S {3,}\S")
TITULO_PADRAO = re.compile(r"^(Padrão|Lei|Hack|Divergência|Benchmark|Arsenal)\s*\d*", re.I)


def extrair_paginas(pdf: Path) -> list[str]:
    exe = shutil.which("pdftotext") or "C:/Program Files/Git/mingw64/bin/pdftotext.exe"
    saida = subprocess.run([exe, "-layout", "-enc", "UTF-8", "-eol", "unix", str(pdf), "-"],
                           capture_output=True, check=True).stdout.decode("utf-8")
    return saida.split("\f")


def limpar_pagina(texto: str) -> tuple[str, list[str]]:
    linhas = texto.split("\n")
    nao_vazias = [i for i, l in enumerate(linhas) if l.strip()]
    if not nao_vazias:
        return "", []
    cabecalho = linhas[nao_vazias[0]].strip()
    corpo = linhas[nao_vazias[0] + 1:]
    # número da página no rodapé
    while corpo and not corpo[-1].strip():
        corpo.pop()
    if corpo and corpo[-1].strip().isdigit():
        corpo.pop()
    return cabecalho, corpo


def paragrafos(linhas: list[str]) -> list[str]:
    """Junta linhas em parágrafos; linhas de tabela ficam uma por linha, com ' | ' entre colunas."""
    saida, atual, tabela = [], "", []

    def fecha_prosa():
        nonlocal atual
        if atual.strip():
            saida.append(atual.strip())
        atual = ""

    def fecha_tabela():
        nonlocal tabela
        if tabela:
            saida.append("\n".join(tabela))
        tabela = []

    for bruta in linhas:
        l = bruta.strip()
        if not l:
            fecha_prosa()
            fecha_tabela()
            continue
        if GAP.search(l):
            fecha_prosa()
            tabela.append(re.sub(r" {3,}", " | ", l))
            continue
        if tabela:  # continuação de célula quebrada: anexa à última linha da tabela
            tabela[-1] += " " + l
            continue
        if atual.endswith(("‐", "-")) and len(atual) > 1 and atual[-2].isalpha():
            atual = atual[:-1] + l
        else:
            atual = (atual + " " + l) if atual else l
    fecha_prosa()
    fecha_tabela()
    return saida


def eh_titulo(p: str) -> bool:
    if "\n" in p:
        return False
    if TITULO_PADRAO.match(p) and len(p) < 260:
        return True
    return len(p) < 90 and not p.endswith((".", ",", ";", ":", ")", "\"", "”")) and p[:1].isupper()


def montar_chunks(paginas: list[str]) -> list[dict]:
    blocos = []  # (capitulo, secao, pagina, paragrafo)
    capitulo, secao = "ABERTURA", ""
    for n, pag in enumerate(paginas, start=1):
        cab, corpo = limpar_pagina(pag)
        if not cab:
            continue
        ps = paragrafos(corpo)
        if cab.upper().startswith("SUMÁRIO"):
            continue  # índice: só ruído para a busca
        if cab.upper().startswith("CAPÍTULO") and ps:
            capitulo = f"{cab} — {ps[0]}"
            secao = ""
            ps = ps[1:]
        elif n > 1 and cab.isupper():
            if capitulo.split(" — ", 1)[-1].upper() != cab:
                capitulo = cab
        for p in ps:
            if eh_titulo(p):
                secao = p
            blocos.append((capitulo, secao, n, p))

    chunks, atual = [], None

    def novo(cap, sec, pag, sobra=None):
        return {"capitulo": cap, "secao": sec, "paginas": [pag], "partes": [sobra] if sobra else []}

    def fecha():
        if atual and atual["partes"]:
            chunks.append(atual)

    for cap, sec, pag, p in blocos:
        # parágrafo gigante (tabela longa): fatia por linhas/frases
        pedacos = [p]
        if len(p) > MAXIMO:
            sep = "\n" if "\n" in p else " "
            partes = p.split("\n") if "\n" in p else re.split(r"(?<=[.;!?])\s+", p)
            pedacos, buf = [], ""
            for parte in partes:
                if buf and len(buf) + len(parte) > ALVO:
                    pedacos.append(buf)
                    buf = ""
                buf = (buf + sep + parte) if buf else parte
            if buf:
                pedacos.append(buf)
        for pd in pedacos:
            tamanho = sum(len(x) for x in atual["partes"]) if atual else 0
            mudou_cap = atual is not None and cap != atual["capitulo"]
            quebra_titulo = atual is not None and eh_titulo(pd) and tamanho > 300
            so_titulos = atual is not None and all(eh_titulo(x) for x in atual["partes"])
            estourou = (tamanho + len(pd) > MAXIMO or tamanho >= ALVO) and not so_titulos
            if atual is None or mudou_cap or quebra_titulo or estourou:
                ultimo = atual["partes"][-1] if atual and atual["partes"] else None
                sobra = ultimo if (ultimo and not mudou_cap and not quebra_titulo
                                   and len(ultimo) <= SOBREPOSICAO_MAX) else None
                fecha()
                atual = novo(cap, sec, pag, sobra)
            atual["partes"].append(pd)
            if pag not in atual["paginas"]:
                atual["paginas"].append(pag)
            atual["secao"] = atual["secao"] or sec
    fecha()

    saida = []
    for i, c in enumerate(chunks, start=1):
        texto = "\n\n".join(c["partes"])
        saida.append({
            "id": f"chunk_{i:04d}",
            "ordem": i,
            "capitulo": c["capitulo"],
            "secao": c["secao"],
            "pagina_inicio": c["paginas"][0],
            "pagina_fim": c["paginas"][-1],
            "texto": texto,
            "caracteres": len(texto),
        })
    return saida


def texto_para_embedding(c: dict) -> str:
    cab = f"Capítulo: {c['capitulo']}" + (f" | Seção: {c['secao']}" if c["secao"] else "")
    return f"passage: {cab}\n{c['texto']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--so-chunks", action="store_true")
    args = ap.parse_args()

    dados = Path(__file__).resolve().parent.parent / "dados"
    dados.mkdir(exist_ok=True)
    chunks = montar_chunks(extrair_paginas(args.pdf))
    (dados / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    tam = [c["caracteres"] for c in chunks]
    print(f"{len(chunks)} chunks | média {sum(tam) // len(tam)} car. | min {min(tam)} | max {max(tam)}")
    if args.so_chunks:
        return

    from sentence_transformers import SentenceTransformer
    from google.cloud import firestore
    from google.cloud.firestore_v1.vector import Vector

    print("gerando embeddings (CPU)...", flush=True)
    modelo = SentenceTransformer(MODELO, device="cpu")
    vetores = modelo.encode([texto_para_embedding(c) for c in chunks], normalize_embeddings=True,
                            batch_size=16, show_progress_bar=True)

    db = firestore.Client(project=PROJETO)
    col = db.collection(COLECAO)
    apagados = 0
    for doc in col.list_documents():
        doc.delete()
        apagados += 1
    if apagados:
        print(f"{apagados} documentos antigos apagados")

    lote, n = db.batch(), 0
    for c, v in zip(chunks, vetores):
        dados_doc = {k: c[k] for k in c if k != "id"}
        dados_doc.update({"embedding": Vector(v.tolist()), "modelo_embedding": MODELO, "fonte": FONTE})
        lote.set(col.document(c["id"]), dados_doc)
        n += 1
        if n % 200 == 0:
            lote.commit()
            lote = db.batch()
    lote.commit()
    print(f"{n} chunks gravados em {PROJETO}/{COLECAO}")


if __name__ == "__main__":
    sys.exit(main())
