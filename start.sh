#!/bin/bash
# ============================================================
#  CGE BI — Script de inicialização do servidor
# ============================================================
set -e

cd "$(dirname "$0")"

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║         CGE BI · Backend + Portal                ║"
echo "  ║   Controladoria Geral do Estado de São Paulo     ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
echo "  → Portal:   http://localhost:5000"
echo "  → Upload:   POST http://localhost:5000/api/upload"
echo "  → Dados:    GET  http://localhost:5000/api/data"
echo "  → Histórico:GET  http://localhost:5000/api/history"
echo "  → SSE:      GET  http://localhost:5000/api/stream"
echo ""
echo "  Pressione Ctrl+C para parar o servidor."
echo ""

python3 server.py
