# Meu Plano Financeiro BR

Dashboard financeiro pessoal em Streamlit para transformar CSVs de bancos/cartões brasileiros em um painel visual, intuitivo e autoexplicativo.

## Versão 3 — Plano financeiro desde a primeira página

Esta versão deixa de ser apenas um analisador de CSV e passa a responder às perguntas principais de organização financeira pessoal:

- Qual é minha profissão e minha renda planejável?
- Qual é meu saldo atual da conta?
- Quanto da fatura/gastos já está comprometido?
- Qual é meu saldo prudente depois da fatura?
- Quanto falta para minha reserva mínima e saudável?
- Quanto devo colocar em reserva de emergência?
- Quanto devo investir agora?
- Quanto posso gastar comigo no mês?
- Quais categorias devo reduzir primeiro?

## Principais melhorias aplicadas

### 1. Nova primeira página: Plano do mês

A primeira aba agora é **🧭 Plano do mês** e mostra:

- Profissão.
- Renda planejável.
- Saldo da conta.
- Gastos/fatura analisados.
- Saldo pós-fatura.
- Reserva mínima.
- Reserva saudável.
- Valor que falta para a reserva.
- Aporte recomendado para reserva.
- Investimento sugerido.
- Limite para gastar consigo.
- Passo a passo do que fazer no mês.

### 2. Configuração pessoal mais completa

O menu lateral agora permite informar:

- Profissão.
- Salário líquido.
- Adiantamento/vale pago em dinheiro.
- Renda extra recorrente.
- Benefícios como Flash/VT/VR.
- Se benefícios entram ou não como renda livre.
- Saldo atual da conta.
- Reserva já separada.
- Custo essencial mensal.
- Meta de meses para reserva saudável.
- Gastos fixos fora do CSV.
- Aporte de reserva do mês.
- Aporte de investimento do mês.
- Sobra de segurança para imprevistos.

### 3. Correção de transferências nos totais

A versão anterior dizia que transferências ficavam fora dos totais por padrão, mas na prática apenas os itens ignorados eram removidos. Agora o padrão correto é:

```python
Gasto + Entrada + Estorno/Crédito
```

Transferências enviadas e recebidas aparecem na aba de qualidade, mas ficam fora dos totais por padrão para evitar distorções com PIX para si mesmo, transferências internas e pagamentos.

### 4. Nova aba: O que diminuir

A aba **✂️ O que diminuir** identifica as maiores categorias e sugere uma economia conservadora por categoria, como:

- Revisar seguro/proteções.
- Congelar novas parcelas.
- Cortar assinaturas sem uso.
- Criar teto para compras.
- Controlar combustível/transporte.

### 5. Exportação do plano do mês

A primeira aba tem botão para baixar o arquivo:

```text
plano_financeiro_do_mes.csv
```

Ele contém a ordem prática do mês: confirmar saldo, considerar fatura, separar reserva, investir somente o planejado e definir limite pessoal.

## Correções preservadas da versão 2

- `Pagamento recebido` em fatura Nubank é classificado como **Ignorado / Pagamento de fatura**.
- Pagamentos de fatura ficam fora dos totais para evitar duplicidade.
- Deduplicação por conciliação segura: 3 cobranças iguais e 2 estornos iguais viram 1 cobrança líquida.
- Regex de Saúde/Farmácia não usa mais `sao paulo` de forma genérica.
- `pix` sozinho não vira transferência.
- Extração de parcelas não captura datas simples como `08/12`.
- Cálculo de parcelas futuras usa `abs(valor)` e pega a parcela mais recente de cada compra parcelada.
- Dashboard possui filtro por tipo de transação.

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

1. Abra o app.
2. Atualize o menu lateral com sua renda, saldo, reserva e metas.
3. Suba o CSV da fatura ou extrato.
4. Veja primeiro a aba **🧭 Plano do mês**.
5. Depois confira categorias, gastos, cortes, parcelas e diagnóstico.
6. Use o valor de **Pode gastar consigo** como teto pessoal do mês.

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

## Privacidade

Na versão local, o arquivo é processado na sua própria máquina. O projeto não salva dados em banco por padrão e não envia dados para serviços externos.

## Testes

Execute:

```bash
pytest -q
```

## Streamlit Cloud

No Streamlit Cloud, use:

```text
Main file path: openfinance_dashboard_br/app.py
```

## Aviso importante

As sugestões são educativas e baseadas nas informações enviadas pelo usuário. O projeto não substitui consultoria financeira, contábil ou recomendação profissional de investimentos.

## Licença

MIT
