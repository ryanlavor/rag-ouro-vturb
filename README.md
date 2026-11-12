# Ouro VTurb · chat RAG local (especialista em DR)

Chat sobre o compilado **"ouro vturb.pdf"** (165 entrevistas do Segredos da Escala). Roda só em `127.0.0.1`.

## Usar
```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\ryanr\rag-ouro-vturb\iniciar.ps1
```
Abre http://127.0.0.1:8765. A primeira pergunta demora uns segundos (o modelo de embedding carrega na subida).

## Rodar em outra máquina (colega do time)
1. Instale [uv](https://docs.astral.sh/uv/), Node.js e o [gcloud CLI](https://cloud.google.com/sdk/docs/install).
2. `git clone https://github.com/ryanlavor/rag-ouro-vturb.git` e entre na pasta.
3. **Acesso ao Firestore:** o Ryan precisa dar ao seu e-mail o papel *Cloud Datastore User* no projeto
   `scraping-renda`. Depois rode `gcloud auth application-default login`.
4. **Chave do modelo:** copie `backend/.env.exemplo` para `backend/.env` e preencha (Anthropic ou OpenRouter com créditos).
   O `.env` nunca vai para o GitHub.
5. Monte o front uma vez: `cd frontend; npm install; npm run build`.
6. Suba: `powershell -ExecutionPolicy Bypass -File iniciar.ps1`. Na primeira vez, rode sem o `HF_HUB_OFFLINE` do script
   para baixar o modelo de embedding (~2 GB).

## Como funciona (RAG)
1. **Chunking** (`scripts/chunk_e_sobe.py`): `pdftotext -layout`, sem o sumário; o cabeçalho de cada página
   indica o capítulo; as tabelas viram linhas `a | b | c`; a prosa é reflowada. Os chunks têm cerca de 1.400
   caracteres (máximo 1.800), quebram nos títulos ("Padrão N — ...") e repetem o último parágrafo curto do chunk
   anterior.
2. **Embeddings**: `intfloat/multilingual-e5-large` local (1024 dimensões, sem custo), o mesmo do agente-criativo.
3. **Firestore**: projeto `scraping-renda`, coleção `RAG-OURO-VTURB` (`chunk_0001`...), com os campos capitulo, secao,
   pagina_inicio/fim, texto e `embedding` (Vector), mais o índice vetorial flat por cosseno.
4. **Busca**: `find_nearest` com os 10 melhores. Se o índice falhar, a busca cai para o cosseno em memória.
5. **Resposta**: Claude Opus 5.5 em streaming, com prompt de especialista em DR, citações [n] e fallback do lado do servidor
   em caso de recusa. Os botões [n] mostram o trecho original.

## Reprocessar o PDF
```powershell
cd backend; uv run python ../scripts/chunk_e_sobe.py "C:/Users/ryanr/Documents/ouro vturb.pdf"
```
Apaga e recria a coleção.

## Front em modo dev
`cd frontend; npm run dev` (porta 5173, com proxy para o backend). Para atualizar o que o backend serve, rode `npm run build`.
