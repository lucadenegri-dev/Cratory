import time, json, anthropic
from app.core.config import settings

client = anthropic.Anthropic(api_key=settings.ai_api_key, timeout=90.0)
model = settings.ai_model or "claude-opus-4-8"
print("model:", model)

schema = {
  "type":"object","additionalProperties":False,
  "properties":{
    "set_title":{"type":"string"},
    "tracks":{"type":"array","items":{
      "type":"object","additionalProperties":False,
      "properties":{"position":{"type":"integer"},"track_id":{"type":"integer"},"risk_level":{"type":"string","enum":["low","medium","high"]}},
      "required":["position","track_id","risk_level"]}}
  },
  "required":["set_title","tracks"]
}
payload = {"candidate_tracks":[{"id":i,"bpm":128+i,"key":"7A"} for i in range(10)]}

def run(label, **extra):
    t0=time.time()
    try:
        with client.messages.stream(
            model=model, max_tokens=4000,
            system="Scegli 5 tracce e ordinale. Usa solo gli id forniti. Rispondi in JSON.",
            messages=[{"role":"user","content":json.dumps(payload)}],
            output_config={"format":{"type":"json_schema","schema":schema}},
            **extra,
        ) as s:
            m=s.get_final_message()
        dt=time.time()-t0
        txt=next((b.text for b in m.content if b.type=="text"),"")
        u=m.usage
        print(f"[{label}] OK {dt:.1f}s in={u.input_tokens} out={u.output_tokens} stop={m.stop_reason} json_ok={bool(json.loads(txt))}")
    except Exception as e:
        print(f"[{label}] ERR {time.time()-t0:.1f}s {type(e).__name__}: {str(e)[:300]}")

run("adaptive", thinking={"type":"adaptive"})
run("no-thinking", thinking={"type":"disabled"})
run("effort-low", thinking={"type":"adaptive"}, output_config={"effort":"low","format":{"type":"json_schema","schema":schema}})
