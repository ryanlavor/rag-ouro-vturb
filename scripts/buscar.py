"""Busca no RAG do Ouro VTurb sem servidor: imprime os trechos mais próximos da pergunta.

Uso (de dentro de backend/):
    uv run python ../scripts/buscar.py "sua pergunta" [-k 10]
"""

import argparse
import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.stdout.reconfigure(encoding="utf-8")

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

from google.cloud import firestore  # noqa: E402
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure  # noqa: E402
from google.cloud.firestore_v1.vector import Vector  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("pergunta", nargs="+")
ap.add_argument("-k", type=int, default=10)
args = ap.parse_args()
pergunta = " ".join(args.pergunta)

modelo = SentenceTransformer("intfloat/multilingual-e5-large", device="cpu")
vetor = modelo.encode(["query: " + pergunta], normalize_embeddings=True)[0].tolist()

col = firestore.Client(project="scraping-renda").collection("RAG-OURO-VTURB")
docs = col.find_nearest(vector_field="embedding", query_vector=Vector(vetor),
                        distance_measure=DistanceMeasure.COSINE, limit=args.k,
                        distance_result_field="distancia").get()

for i, d in enumerate(docs, start=1):
    t = d.to_dict()
    pags = f"p. {t['pagina_inicio']}" + (f"-{t['pagina_fim']}" if t["pagina_fim"] != t["pagina_inicio"] else "")
    print(f"[{i}] {t['capitulo']}" + (f" › {t['secao']}" if t.get("secao") else "")
          + f" ({pags}, sim {1 - t['distancia']:.3f})")
    print(t["texto"])
    print("\n---\n")
