# Etapa 5.4b — recompensa com startup e guarda pré-reprodução

## Objetivo

A Etapa 5.4a mostrou que o RobustMPC podia aumentar a qualidade às custas de
aproximadamente 8,54 s adicionais de startup, pois a recompensa não penalizava
o atraso inicial. Esta etapa acrescenta `startup_weight` à recompensa, cria
traces independentes e seleciona uma configuração sem abrir o novo holdout.

## Novos conjuntos

Seis traces de 60 segmentos foram gerados por regimes Markovianos com
suavização AR(1) no domínio logarítmico. Eles não reamostram os traces antigos.
As sementes 54101–54103 formam a validação; 54901–54903 formam o holdout final.
Cada conjunto contém inícios em regime baixo, médio e alto. O gerador,
parâmetros, hashes e estatísticas estão em
`bandwidth_traces/stage54b_trace_provenance.json`.

O protocolo passa a usar 60 dos 63 segmentos DVB, ampliando a cobertura
temporal em relação aos 30 segmentos da Etapa 5.4a. Isso não substitui a futura
necessidade de avaliar outro pacote de conteúdo VVC independente.

## Rodadas de validação

| Rodada | Alteração | Resultado |
| :--- | :--- | :--- |
| 1 | `startup_weight` em {0,05; 0,10; 0,25; 0,50} | nenhum candidato cumpriu não inferioridade de startup; 0,50 ficou no limite da grade |
| 2 | refinamento em {0,50; 1; 2; 5} | pesos maiores não reduziram o startup; 0,50 permaneceu melhor ranqueado |
| 3 | guarda na representação inferior antes do início + pesos da rodada 1 | todos os candidatos igualaram o startup estático; 0,50 maximizou o bitrate útil médio entre os elegíveis |

As duas primeiras rodadas foram preservadas. Elas mostraram que o problema não
era apenas um peso insuficiente: o agente podia aumentar a representação antes
de atingir o buffer inicial. A guarda força a representação inferior somente
durante esse período. Depois do início, as ações voltam a ser escolhidas pela
Q-table.

## Configuração selecionada

- candidato: `guard_wstartup050`;
- pesos `(qualidade, rebuffering, troca, buffer baixo, startup)`:
  `(1; 10; 0,25; 2; 0,5)`;
- buffer-alvo: 8 s;
- `startup_guard=true`;
- cinco sementes e 4000 episódios por semente;
- seleção somente nos três traces de validação.

## Resultado pareado na validação

As diferenças seguem `Q-Learning − estático`, com os três traces promediados
dentro de cada semente antes do IC95%.

| Métrica | Diferença média | IC95% | Leitura |
| :--- | ---: | :--- | :--- |
| Startup (s) | 0,000 | [0,000; 0,000] | empate exato |
| Rebuffering (s) | −0,284 | [−0,284; −0,284] | menor no Q-Learning |
| Taxa de rebuffering (p.p.) | −0,495 | [−0,495; −0,495] | menor no Q-Learning |
| Bitrate selecionado (kbps) | −160 | [−1.248; 928] | sem diferença conclusiva |
| Bitrate útil (kbps) | −151 | [−1.227; 924] | sem diferença conclusiva |
| Desvio-padrão do buffer (s) | −0,501 | [−0,694; −0,308] | menor no Q-Learning |

O candidato cumpriu simultaneamente as margens de startup e rebuffering. A
diferença de bitrate útil inclui zero, portanto não há evidência de perda ou
ganho nessa métrica durante a seleção.

## Estado do holdout

Os arquivos `stage54b_evaluation_*` estão congelados e registrados na
configuração selecionada, mas não foram carregados nem executados. A função de
ajuste não abre caminhos de avaliação e o comportamento é protegido por teste.

A avaliação final deve ocorrer somente após versionar e revisar
`dvb_uhd1_hfr_startup_guard_selected_protocol_config.json`. Nessa futura
execução, Q-Learning deverá ser comparado novamente com estático, throughput,
BOLA-BASIC e RobustMPC; nenhum peso poderá ser alterado depois.
