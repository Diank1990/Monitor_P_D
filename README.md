# Acompanhamento – Subvenção FINEP em Fluxo Contínuo

Coleta diariamente o painel público da FINEP, compara com a coleta anterior, registra o que mudou e publica uma página única com todas as seleções públicas.

## O que fica registrado

- `index.html`: a página, com seletor de seleção pública, abas Aprovados / Não aprovados / Em análise / Alterações, busca e exportação em CSV.
- `data/atual.json`: a versão mais recente dos dados.
- `data/alteracoes.json`: o registro de alterações (novas propostas, mudança de situação, de status, de fase, de valor, número de referência atribuído, propostas retiradas do painel, novos editais, mudança de orçamento).
- `data/historico.json`: os indicadores de cada edital a cada coleta com alteração.
- `data/versoes/`: cópia compactada de cada versão anterior.

O robô só grava quando o painel muda. Cada gravação vira um commit no GitHub, o que preserva também o histórico completo dos arquivos.

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
