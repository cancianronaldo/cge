"""
CGE BI — Backend Server
Aceita upload de Excel, processa automaticamente e serve dados via API + SSE.
"""

import os, json, time, hashlib, threading
from pathlib import Path
from datetime import datetime

import pandas as pd
from flask import (
    Flask, request, jsonify, Response,
    send_from_directory, stream_with_context
)

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
UPLOAD_DIR  = BASE_DIR / "uploads"
STATIC_DIR  = BASE_DIR / "static"
DATA_FILE   = BASE_DIR / "data.json"
META_FILE   = BASE_DIR / "meta.json"
ALLOWED_EXT = {".xlsx", ".xls"}
MAX_MB      = 50

UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(STATIC_DIR))

# ── SSE broadcast ────────────────────────────────────────────────────────────
_listeners: list[threading.Event] = []
_listeners_lock = threading.Lock()

def broadcast_update():
    with _listeners_lock:
        for ev in _listeners:
            ev.set()

# ── Status normalization ─────────────────────────────────────────────────────
def norm_status(s: str | None) -> str:
    if not s:
        return "Outro"
    l = str(s).strip().lower()
    if any(k in l for k in ("produção", "em produção", "em producao", "producao")):
        return "Produção"
    if any(l == k or k in l for k in ("aberto/backlog", "open", "backlog")):
        return "Aberto/Backlog"
    if any(k in l for k in ("impedimento", "impeditivo")):
        return "Impedimento"
    if "homolog" in l:
        return "Homologação"
    if "desenvolv" in l:
        return "Em Desenvolvimento"
    if "encerrad" in l:
        return "Encerrado"
    if any(k in l for k in ("aguardando", "validar")):
        return "Aguardando/Validar"
    return str(s).strip()

# ── Excel processor ──────────────────────────────────────────────────────────
def safe_str(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return str(v).strip() or None

def safe_date(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None
        if ts.year < 1980 or ts.year > 2099:
            return None
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return None

def process_excel(path: Path) -> dict:
    xf = pd.ExcelFile(path)
    result = {}
    for sheet in xf.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        df.columns = [str(c).strip() for c in df.columns]

        # Skip sheets with no recognizable columns
        has_desc   = "Descrição" in df.columns
        has_titulo = any(c.strip().lower().startswith("titulo") for c in df.columns)
        if not has_desc and not has_titulo and "Status" not in df.columns:
            continue

        # Normalise column alias for FALA-SP style sheets
        titulo_col = next((c for c in df.columns if c.strip().lower().startswith("titulo")), None)

        records = []
        for _, row in df.iterrows():
            desc = safe_str(row.get("Descrição") or (row.get(titulo_col) if titulo_col else None))
            if not desc:
                continue

            rec: dict = {
                "Descrição": desc,
                "Código":    safe_str(row.get("Código") or row.get("Card")),
                "Status":    norm_status(safe_str(row.get("Status"))),
                "Categoria": safe_str(row.get("Categoria")),
                "Sistema":   safe_str(row.get("Sistema")),
                "Prioridade": safe_str(row.get("Prioridade")),
                "Responsável": safe_str(row.get("Responsável")),
                "Origem":    safe_str(row.get("Origem")),
                "Data de Abertura":    safe_date(row.get("Data de Abertura")),
                "Previsão Produção":   safe_date(row.get("Previsão Produção")),
                "Data de Impedimento": safe_date(row.get("Data de Impedimento")),
                "Estimativa Início":   safe_date(row.get("Estimativa Início")),
                "Estimativa Fim":      safe_date(row.get("Estimativa Fim")),
                "Observação": safe_str(row.get("Observação")),
            }
            records.append(rec)

        if records:
            result[sheet] = records

    return result

# ── Metadata helpers ─────────────────────────────────────────────────────────
def read_meta() -> dict:
    if META_FILE.exists():
        return json.loads(META_FILE.read_text())
    return {"uploads": []}

def write_meta(meta: dict):
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

def read_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}

# ── Routes ───────────────────────────────────────────────────────────────────

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")

@app.route("/api/data")
def api_data():
    return jsonify(read_data())

@app.route("/api/meta")
def api_meta():
    return jsonify(read_meta())

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Nome de arquivo vazio"}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": f"Extensão não suportada: {ext}. Use .xlsx ou .xls"}), 400

    # Read bytes, check size
    data_bytes = f.read()
    if len(data_bytes) > MAX_MB * 1024 * 1024:
        return jsonify({"error": f"Arquivo muito grande (máx {MAX_MB}MB)"}), 413

    # Save file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{ts}_{Path(f.filename).name}"
    dest = UPLOAD_DIR / fname
    dest.write_bytes(data_bytes)

    # Process
    try:
        sheets_data = process_excel(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        return jsonify({"error": f"Erro ao processar arquivo: {e}"}), 422

    if not sheets_data:
        return jsonify({"error": "Nenhuma aba válida encontrada no arquivo"}), 422

    # Count rows
    total_rows = sum(len(v) for v in sheets_data.values())
    file_hash = hashlib.md5(data_bytes).hexdigest()[:8]

    # Save data
    DATA_FILE.write_text(json.dumps(sheets_data, ensure_ascii=False, indent=2))

    # Update meta
    meta = read_meta()
    meta["uploads"].append({
        "filename": f.filename,
        "saved_as": fname,
        "uploaded_at": datetime.now().isoformat(),
        "sheets": list(sheets_data.keys()),
        "total_rows": total_rows,
        "hash": file_hash,
    })
    meta["last_update"] = datetime.now().isoformat()
    write_meta(meta)

    # Notify SSE clients
    broadcast_update()

    return jsonify({
        "ok": True,
        "sheets": list(sheets_data.keys()),
        "total_rows": total_rows,
        "filename": f.filename,
        "processed_at": datetime.now().isoformat(),
    })

@app.route("/api/history")
def api_history():
    meta = read_meta()
    return jsonify(meta.get("uploads", []))

@app.route("/api/stream")
def api_stream():
    """SSE endpoint — clientes ficam conectados e recebem eventos de update."""
    ev = threading.Event()
    with _listeners_lock:
        _listeners.append(ev)

    def generate():
        try:
            # Heartbeat a cada 25s para manter conexão viva
            while True:
                triggered = ev.wait(timeout=25)
                if triggered:
                    ev.clear()
                    yield "event: update\ndata: {}\n\n"
                else:
                    yield ": heartbeat\n\n"
        finally:
            with _listeners_lock:
                try:
                    _listeners.remove(ev)
                except ValueError:
                    pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

# ── Seed with existing data if present ───────────────────────────────────────
_SEED = Path("/mnt/user-data/uploads/RelatorioSolicitacoesCGE_30a03-04-2026V2_1_-_Copiar.xlsx")
if _SEED.exists() and not DATA_FILE.exists():
    try:
        seed_data = process_excel(_SEED)
        DATA_FILE.write_text(json.dumps(seed_data, ensure_ascii=False, indent=2))
        meta = read_meta()
        meta["uploads"].append({
            "filename": _SEED.name,
            "saved_as": _SEED.name,
            "uploaded_at": datetime.now().isoformat(),
            "sheets": list(seed_data.keys()),
            "total_rows": sum(len(v) for v in seed_data.values()),
            "hash": "seed",
        })
        meta["last_update"] = datetime.now().isoformat()
        write_meta(meta)
        print(f"[seed] Loaded {sum(len(v) for v in seed_data.values())} rows from seed file")
    except Exception as e:
        print(f"[seed] Error: {e}")

if __name__ == "__main__":
    print("CGE BI Server running → http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
