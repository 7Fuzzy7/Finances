# OpenFinance Dashboard BR

Dashboard financeiro pessoal open source para transformar CSVs de bancos/cartões brasileiros em um painel visual, intuitivo e autoexplicativo.

## Versão 2 — correções do engine

Esta versão reescreve o engine de leitura, classificação, deduplicação e análise financeira.

### Bugs corrigidos

- `Pagamento recebido` em fatura Nubank agora é classificado como **Ignorado / Pagamento de fatura**, não como gasto, entrada ou categoria de despesa.
- Pagamentos de fatura ficam fora dos totais por padrão para evitar gasto duplicado.
- Deduplicação por **conciliação segura**: casos como 3 cobranças iguais e 2 estornos iguais viram 1 cobrança líquida.
- Regex de Saúde/Farmácia não usa mais `sao paulo` de forma genérica; agora reconhece `Drogaria Sao Paulo` sem capturar qualquer ocorrência da cidade.
- `pix` sozinho não vira Transferência. Só é classificado como transferência quando a descrição indica `transferência enviada/recebida` ou `pix enviado/recebido`.
- Extração de parcelas não captura datas simples como `08/12`; slash só é aceito com contexto de parcela. O formato compacto do Nubank `08d12` continua funcionando.
- Cálculo de parcelas futuras usa `abs(valor)` e pega a parcela mais recente de cada compra parcelada.
- Dashboard agora possui filtro por **tipo de transação**, permitindo incluir/excluir pagamentos, transferências, estornos e entradas.

## O que ele faz

- Upload de um ou vários arquivos CSV.
- Leitura automática de colunas no padrão `date,title,amount` ou `data,descricao,valor`.
- Categorização automática de gastos.
- Cards com gastos líquidos, saldo estimado, score financeiro, maior categoria e parcelas futuras.
- Gráficos interativos por categoria, mês, lojista e fluxo acumulado.
- Detecção de parcelas e recorrências suspeitas.
- Diagnóstico financeiro com sugestões de melhoria e organização.
- Aba de qualidade de dados com linhas conciliadas, lançamentos ignorados e resumo por tipo.
- Exportação dos dados tratados em CSV.

## Privacidade

Na versão local, o arquivo é processado na sua própria máquina. O projeto não salva dados em banco por padrão e não envia dados para serviços externos.

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
4. Escolha a deduplicação recomendada.
5. Informe sua renda líquida mensal.
6. Confira diagnóstico, categorias, parcelas e sugestões.

## Formato de CSV suportado

Exemplo Nubank fatura:

```csv
date,title,amount
2026-06-22,Dm *Spotify,"23,90"
2026-06-17,Posto George,"85,40"
2026-06-13,Estorno de compra (Canva),"- 49,00"
2026-06-03,Pagamento recebido,"- 1.311,82"
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
