# CGE BI — Painel de Solicitações

Portal de Business Intelligence com backend automático para upload de planilhas Excel.

---

## ⚡ Início rápido

```bash
cd cge_bi
pip install flask openpyxl pandas
python3 server.py
```

Acesse: **http://localhost:5000**

---

## 🏗️ Estrutura do projeto

```
cge_bi/
├── server.py          ← Backend Flask (API + SSE + processamento)
├── start.sh           ← Script de inicialização
├── data.json          ← Dados processados (gerado automaticamente)
├── meta.json          ← Histórico de uploads (gerado automaticamente)
├── uploads/           ← Arquivos Excel recebidos
└── static/
    └── index.html     ← Portal BI (frontend completo)
```

---

## 📡 Endpoints da API

| Método | Rota              | Descrição                              |
|--------|-------------------|----------------------------------------|
| GET    | `/`               | Serve o portal BI                      |
| GET    | `/api/data`       | Retorna todos os dados processados     |
| GET    | `/api/meta`       | Retorna metadados e último upload      |
| GET    | `/api/history`    | Histórico de todos os uploads          |
| POST   | `/api/upload`     | Recebe e processa um arquivo Excel     |
| GET    | `/api/stream`     | SSE — notificações em tempo real       |

---

## 📤 Como fazer upload via linha de comando

```bash
# curl
curl -X POST http://localhost:5000/api/upload \
     -F "file=@/caminho/para/planilha.xlsx"

# httpie
http --form POST localhost:5000/api/upload file@planilha.xlsx
```

---

## 🔄 Funcionamento em tempo real

1. Você faz upload de um `.xlsx` (pelo portal ou via `curl`)
2. O servidor processa automaticamente todas as abas
3. O `data.json` é atualizado
4. O servidor notifica todos os clientes via **Server-Sent Events (SSE)**
5. O portal atualiza instantaneamente — sem precisar recarregar a página

---

## 📊 Estrutura esperada da planilha

Cada aba deve ter as colunas (exatas ou aproximadas):

| Coluna               | Obrigatório |
|----------------------|-------------|
| Descrição            | ✅           |
| Código               | —           |
| Status               | —           |
| Categoria            | —           |
| Prioridade           | —           |
| Responsável          | —           |
| Data de Abertura     | —           |
| Previsão Produção    | —           |
| Data de Impedimento  | —           |
| Observação           | —           |

Abas com coluna `Titulo ` (formato FALA-SP) também são suportadas.

---

## 🚀 Deploy em produção

Para rodar em produção, use **gunicorn**:

```bash
pip install gunicorn
gunicorn -w 1 -b 0.0.0.0:5000 --timeout 120 server:app
```

> ⚠️ Use `-w 1` (1 worker) para garantir que o SSE broadcast funcione corretamente.

Para HTTPS, coloque um **nginx** na frente como proxy reverso.
