# Etapa 5.4c — avaliação única no novo holdout

## Protocolo

A configuração selecionada na Etapa 5.4b foi avaliada uma única vez nos três
traces `stage54b_evaluation_*`, com 60 segmentos cada. O Q-Learning usa
`startup_weight=0,5`, `startup_guard=true`, cinco sementes de treinamento e
4.000 episódios por semente. Os baselines mantêm os parâmetros congelados na
Etapa 5.4a: estático, throughput, BOLA-BASIC e RobustMPC.

O código e a configuração foram congelados no commit `680a16f`; hashes e
estado não executado foram registrados no commit `7403247`. A execução criou
uma trava persistente antes de carregar o holdout, produziu 75 avaliações e
não foi repetida. As diferenças abaixo são `Q-Learning − baseline`; os três
traces são primeiro promediados dentro de cada semente, e o IC95% é calculado
entre as cinco sementes.

## Resultados pareados gerais

| Baseline | Startup (s) | Rebuffering (s) | Bitrate útil (kbps) | Desvio do buffer (s) | Recompensa objetiva |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Estático | 0,000 [0,000; 0,000] | −1,015 [−1,481; −0,549] | +313 [−165; 791] | −0,382 [−0,477; −0,286] | +0,217 [0,125; 0,310] |
| Throughput | 0,000 [0,000; 0,000] | +2,385 [1,919; 2,851] | +4.499 [4.021; 4.977] | −1,862 [−1,957; −1,766] | −0,591 [−0,683; −0,498] |
| BOLA-BASIC | 0,000 [0,000; 0,000] | +0,089 [−0,377; 0,555] | +573 [95; 1.050] | −0,137 [−0,233; −0,042] | +0,021 [−0,072; 0,114] |
| RobustMPC | −1,310 [−1,310; −1,310] | +1,929 [1,463; 2,395] | +1.317 [840; 1.795] | −1,237 [−1,332; −1,141] | −0,521 [−0,614; −0,429] |

Contra o estático, o Q-Learning mantém o mesmo startup, reduz rebuffering e
variabilidade do buffer e melhora a recompensa objetiva; o ganho de bitrate
útil é inconclusivo. Ele realiza mais 5,8 trocas por execução, IC95%
[1,49; 10,11].

Contra o BOLA-BASIC, o Q-Learning aumenta o bitrate útil e reduz a variabilidade
do buffer, sem diferença conclusiva em startup, rebuffering, recompensa ou
número de trocas. Esse é o resultado competitivo mais favorável, mas não prova
superioridade geral.

Throughput e RobustMPC apresentam menos rebuffering e recompensa objetiva
superior ao Q-Learning. Em contrapartida, o Q-Learning entrega mais bitrate
útil e buffer menos variável; contra RobustMPC também reduz startup em 1,31 s.
Portanto, esses resultados expressam compromissos distintos, não dominância.

## Heterogeneidade entre traces

O resultado geral esconde comportamentos distintos. Contra o estático, no
trace de início baixo o Q-Learning reduz rebuffering em 3,045 s, mas perde
1.198 kbps de bitrate útil. No trace de início médio, mantém o rebuffering e
ganha 2.136 kbps; no início alto, os dois controladores coincidem. Isso reforça
a necessidade de ampliar a diversidade de redes e conteúdos.

## Limitações e conclusão

Os IC95% não têm correção por comparações múltiplas, a unidade independente é a
semente de treinamento (`n=5`), os baselines determinísticos não variam entre
sementes e o estudo usa um único conteúdo DVB com duas representações. A
Etapa 5.4c sustenta que a política aprendida é competitiva com BOLA-BASIC e
melhora o baseline estático, mas não sustenta que seja o melhor controlador em
geral. Todos os dados brutos, agregados, diferenças pareadas, hashes e a
atestação de execução estão neste diretório.
