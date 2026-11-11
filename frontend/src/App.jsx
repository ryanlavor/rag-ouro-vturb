import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const SUGESTOES = [
  "Qual conversão de VSL é boa em tráfego frio e quando eu mato a oferta?",
  "Como estruturar os primeiros 5 minutos de uma VSL de nutra?",
  "Quais métricas de criativo olhar antes de escalar?",
  "Escala vertical ou horizontal: o que os grandes fazem?",
];

const CHAVE = "ouro-vturb-conversa";

function carregar() {
  try {
    return JSON.parse(localStorage.getItem(CHAVE)) || [];
  } catch {
    return [];
  }
}

export default function App() {
  const [msgs, setMsgs] = useState(carregar);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [fonteAberta, setFonteAberta] = useState(null);
  const fimRef = useRef(null);

  useEffect(() => {
    try {
      localStorage.setItem(CHAVE, JSON.stringify(msgs));
    } catch {}
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  async function enviar(pergunta) {
    const q = (pergunta ?? texto).trim();
    if (!q || enviando) return;
    setTexto("");
    setEnviando(true);
    const historico = [...msgs, { role: "user", content: q }];
    setMsgs([...historico, { role: "assistant", content: "", fontes: [] }]);

    const atualiza = (fn) =>
      setMsgs((m) => {
        const c = [...m];
        c[c.length - 1] = fn({ ...c[c.length - 1] });
        return c;
      });

    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: historico.map(({ role, content }) => ({ role, content })),
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const leitor = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await leitor.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const blocos = buf.split("\n\n");
        buf = blocos.pop();
        for (const b of blocos) {
          if (!b.startsWith("data: ")) continue;
          const ev = JSON.parse(b.slice(6));
          if (ev.tipo === "fontes") atualiza((u) => ({ ...u, fontes: ev.fontes }));
          if (ev.tipo === "texto") atualiza((u) => ({ ...u, content: u.content + ev.texto }));
          if (ev.tipo === "erro") atualiza((u) => ({ ...u, content: u.content + `\n\n⚠️ ${ev.erro}` }));
        }
      }
    } catch (e) {
      atualiza((u) => ({ ...u, content: u.content + `\n\n⚠️ Falha: ${e.message}` }));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Ouro VTurb</h1>
          <span>Especialista em Resposta Direta · 165 entrevistas, 440h</span>
        </div>
        {msgs.length > 0 && (
          <button className="limpar" onClick={() => setMsgs([])} disabled={enviando}>
            Nova conversa
          </button>
        )}
      </header>

      <main>
        {msgs.length === 0 && (
          <div className="vazio">
            <p>Pergunte sobre VSL, funil, copy, criativos, tráfego, ofertas ou operação.</p>
            <div className="sugestoes">
              {SUGESTOES.map((s) => (
                <button key={s} onClick={() => enviar(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" ? (
              <>
                {m.content ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                ) : (
                  <div className="pensando">Buscando no documento e pensando…</div>
                )}
                {m.fontes?.length > 0 && (
                  <div className="fontes">
                    {m.fontes.map((f) => (
                      <button
                        key={f.n}
                        title={`${f.capitulo}${f.secao ? " › " + f.secao : ""}`}
                        onClick={() => setFonteAberta(f)}
                      >
                        [{f.n}] p.{f.pagina_inicio}
                      </button>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p>{m.content}</p>
            )}
          </div>
        ))}
        <div ref={fimRef} />
      </main>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          enviar();
        }}
      >
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              enviar();
            }
          }}
          placeholder="Sua pergunta (Enter envia, Shift+Enter quebra linha)"
          rows={2}
        />
        <button type="submit" disabled={enviando || !texto.trim()}>
          {enviando ? "…" : "Enviar"}
        </button>
      </form>

      {fonteAberta && (
        <div className="modal" onClick={() => setFonteAberta(null)}>
          <div className="cartao" onClick={(e) => e.stopPropagation()}>
            <h3>
              [{fonteAberta.n}] {fonteAberta.capitulo}
            </h3>
            <small>
              {fonteAberta.secao && `${fonteAberta.secao} · `}p. {fonteAberta.pagina_inicio}
              {fonteAberta.pagina_fim !== fonteAberta.pagina_inicio && `-${fonteAberta.pagina_fim}`} ·
              similaridade {fonteAberta.similaridade}
            </small>
            <pre>{fonteAberta.texto}</pre>
            <button onClick={() => setFonteAberta(null)}>Fechar</button>
          </div>
        </div>
      )}
    </div>
  );
}
