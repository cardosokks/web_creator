# Gerador de Páginas

Aplicação Flask para gerar, listar, renomear e excluir páginas salvas em disco.

## Rodar localmente

```bash
python -m venv .env
.env\Scripts\activate
pip install -r requirements.txt
python web.py
```

## Deploy no EasyPanel

Este repositório já vem preparado para deploy via Docker.

Configurações recomendadas:

```env
PORT=8000
DATA_DIR=/data/paginas_geradas
DEFAULT_WEBHOOK_URL=http://seu-webhook:porta/webhook/generate_page
```

No EasyPanel, aponte um volume persistente para `/data` para não perder as páginas geradas ao recriar o container.

Use o `Dockerfile` da raiz do projeto como build.