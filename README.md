# Acompanhamento – Subvenção FINEP em Fluxo Contínuo

Coleta diariamente o painel público da FINEP, compara com a coleta anterior, registra o que mudou e publica uma página única com todas as seleções públicas.

## O que fica registrado

- `index.html`: a página, com seletor de seleção pública, abas Aprovados / Não aprovados / Em análise / Por linha e UF / Reserva regional / Simulação / Alterações / Histórico, busca e exportação em CSV. A aba Alterações mostra apenas as mudanças do dia da coleta mais recente em relação à versão anterior; as mais antigas ficam na aba Histórico, com filtro por dia.
- `data/atual.json`: a versão mais recente dos dados.
- `data/alteracoes.json`: o registro de alterações (propostas incluídas no painel, mudança de situação, de status, de fase, de valor, número de referência atribuído, propostas retiradas do painel, novos editais, mudança de orçamento).
- `data/historico.json`: os indicadores de cada edital a cada coleta com alteração.
- `data/versoes/`: cópia compactada de cada versão anterior.

O robô só grava quando o painel muda. Cada gravação vira um commit no GitHub, o que preserva também o histórico completo dos arquivos.

## Abas de análise

- **Por linha e UF:** aprovados, não aprovados e em análise (quantidade e valor) por linha temática e por região/estado da UF do projeto, com a taxa de aprovação.
- **Reserva regional:** para cada seleção pública (ou cada linha, quando configurado), o valor reservado a Norte, Nordeste e Centro-Oeste, quanto já foi aprovado nessas regiões, se a reserva foi atingida e o saldo disponível para cada grupo de regiões.
- **Simulação:** escolha uma proposta em análise (ou clique em "Simular" na aba Em análise) e veja se o saldo alcança a posição dela na fila, com a taxa de aprovação esperada das propostas à frente, o ponto de virada e a memória de cálculo.

## Regras dos editais (`regras.json`)

O arquivo `regras.json` guarda o que o painel da FINEP não informa:

- `reserva_regional.percentual_padrao`: percentual da reserva para N, NE e CO (padrão `0.30`).
- `editais.<nome>.percentual_reserva`: percentual diferente para uma seleção específica (opcional).
- `editais.<nome>.orcamento_por_linha`: orçamento de cada linha temática, para seleções em que orçamento e reserva valem por linha (hoje, Saúde). Os nomes das linhas devem ser iguais aos do painel.

O nome da seleção deve ser igual ao do seletor da página. Para editar, abra o arquivo no GitHub, clique no lápis, altere e salve: a página é regerada na próxima coleta (ou em **Actions > Run workflow**). A aba Reserva regional avisa quando a soma das linhas difere do orçamento do painel.

## Como atualizar a ferramenta

Para substituir o código por uma versão nova, envie em **Add file > Upload files** apenas `monitor.py`, `modelo.html`, `regras.json` e `README.md`. Não envie a pasta `data` nem o `index.html`: eles são mantidos pelo robô. Depois, rode **Actions > Atualizar painel FINEP > Run workflow** para regerar a página na hora.

## Como colocar no ar (GitHub, gratuito)

1. Crie um repositório público no GitHub, por exemplo `monitor-finep`.
2. Em **Add file > Upload files**, envie todo o conteúdo desta pasta.
   A pasta `.github` fica oculta no Windows e no macOS e às vezes não sobe ao arrastar. Se ela não aparecer no repositório, use **Add file > Create new file**, digite o nome `.github/workflows/atualizar.yml` e cole o conteúdo do arquivo.
3. Em **Settings > Pages**, escolha **Deploy from a branch**, ramo `main`, pasta `/ (root)`, e salve.
4. Em **Actions**, abra **Atualizar painel FINEP** e clique em **Run workflow** para a primeira execução.
5. A página fica em `https://SEU-USUARIO.github.io/monitor-finep/`.

Depois disso, a coleta roda sozinha todos os dias às 07:00 (Brasília). Para mudar o horário, edite a linha `cron` em `.github/workflows/atualizar.yml` (o horário é UTC: 10:00 UTC = 07:00 em Brasília).

## Se algo falhar

- Se a coleta falhar, o GitHub envia um e-mail ao dono do repositório e nada é gravado; a versão anterior continua no ar.
- A causa mais provável de falha é a FINEP reestruturar o painel (renomear tabelas ou colunas). Nesse caso, o arquivo `monitor.py` precisa de ajuste.
- Se o push falhar por permissão, ative **Settings > Actions > General > Workflow permissions > Read and write permissions**.
- Em repositórios públicos, o GitHub pausa agendamentos após 60 dias sem nenhuma atividade. Se o painel passar esse tempo sem mudanças, reative em **Actions**.

## Rodar no próprio computador

```
pip install requests
python monitor.py           # coleta, compara e regera index.html
python monitor.py --so-html # só regera index.html a partir de data/
```
