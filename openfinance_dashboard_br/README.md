# OpenFinance Dashboard BR

Dashboard financeiro pessoal open source para transformar CSVs de bancos/cartões brasileiros em um painel visual, intuitivo e autoexplicativo.

## O que ele faz

- Upload de um ou vários arquivos CSV.
- Leitura automática de colunas no padrão `date,title,amount` ou `data,descricao,valor`.
- Categorização automática de gastos.
- Cards com gastos líquidos, saldo estimado, score financeiro, maior categoria e parcelas futuras.
- Gráficos interativos por categoria, mês, lojista e fluxo acumulado.
- Detecção de parcelas e recorrências suspeitas.
- Diagnóstico financeiro com sugestões de melhoria e organização.
- Exportação dos dados tratados em CSV.

## Privacidade

Na versão local, o arquivo é processado na sua própria máquina. O projeto não salva dados em banco por padrão e não envia os dados para serviços externos.

## Como rodar

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Depois, abra o endereço exibido no terminal, normalmente:

```text
http://localhost:8501
```

## Como usar

1. Exporte o CSV da fatura ou conta no app do banco.
2. Abra o dashboard.
3. Suba um ou mais arquivos CSV.
4. Informe sua renda líquida mensal.
5. Veja o diagnóstico e siga o plano de ação.

## Formato de CSV suportado

Exemplo Nubank fatura:

```csv
date,title,amount
2026-06-22,Dm *Spotify,"23,90"
2026-06-17,Posto George,"85,40"
2026-06-13,Estorno de compra (Canva),"- 49,00"
```

Também aceita variações como:

```csv
data,descricao,valor
2026-06-22,Spotify,"23,90"
```

## Aviso importante

As sugestões são educativas e baseadas nas informações enviadas pelo usuário. O projeto não substitui consultoria financeira, contábil ou recomendação profissional de investimentos.

## Licença

MIT
