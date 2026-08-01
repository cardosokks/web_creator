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

No EasyPanel, use um volume persistente do próprio painel montado em `/data` para não perder as páginas geradas ao recriar o container.

Use o `Dockerfile` da raiz do projeto como build.

### Configuração exata no EasyPanel

- Build context: raiz do repositório
- Dockerfile: `Dockerfile`
- Porta pública/container: `8000`
- Volume persistente: volume gerenciado pelo painel montado em `/data` no container
- Variáveis de ambiente:
	- `PORT=8000`
	- `DATA_DIR=/data/paginas_geradas`
	- `DEFAULT_WEBHOOK_URL=http://seu-webhook:porta/webhook/generate_page`

Se o painel pedir o caminho do volume, use qualquer pasta persistente disponível no host e monte em `/data`. Não use `/data` como caminho de origem do host.

### Template pronto

Se o painel aceitar Docker Compose, importe o arquivo [docker-compose.yml](docker-compose.yml) e use a variável `DEFAULT_WEBHOOK_URL` no ambiente.

Se preferir deploy por Dockerfile, o comportamento é o mesmo, só apontar a raiz do repositório e usar o [Dockerfile](Dockerfile).