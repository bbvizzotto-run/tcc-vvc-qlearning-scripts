# Protocolo Experimental Multi-Semente — Etapa 3

O protocolo executou cinco treinamentos independentes, com sementes 11, 23, 37, 53 e 71. Cada política foi avaliada, sem exploração, nos traces `evaluation_gradual`, `evaluation_bursty` e `evaluation_challenging`. O baseline estático foi executado nas mesmas condições, totalizando 30 execuções avaliativas.

Os valores gerais são calculados em duas etapas: primeiro é obtida, para cada semente, a média dos três traces; em seguida, o IC95% é calculado entre as cinco sementes usando a distribuição t de Student. A diferença pareada é sempre:

```text
delta = Q-Learning - Estático
```

## Resultado geral

| Métrica | Estático | Q-Learning | Delta médio [IC95%] | Interpretação |
| :--- | ---: | ---: | ---: | :--- |
| Atraso inicial (s) | 0,444 | 1,255 | +0,810 [0,556; 1,065] | Maior no Q-Learning |
| Rebuffering (s) | 16,645 | 19,778 | +3,133 [-5,100; 11,366] | Inconclusivo |
| Taxa de rebuffering (%) | 27,741 | 32,963 | +5,222 [-8,500; 18,943] | Inconclusivo |
| Bitrate médio (kbps) | 1433,33 | 1820,00 | +386,67 [86,33; 687,01] | Maior no Q-Learning |
| Desvio padrão do buffer (s) | 3,418 | 2,188 | -1,230 [-1,830; -0,629] | Menor no Q-Learning |

## Rebuffering por trace

| Trace | Delta médio Q-Learning–Estático (s) | IC95% | Leitura |
| :--- | ---: | ---: | :--- |
| Gradual | -0,318 | [-0,318; -0,318] | Q-Learning evitou a pequena interrupção do baseline |
| Bursty | +19,195 | [-6,506; 44,895] | Alta variabilidade; resultado inconclusivo |
| Challenging | -9,478 | [-11,735; -7,221] | Menos rebuffering no Q-Learning |

## Interpretação

O resultado de uma única semente da etapa anterior sugeria vantagem clara do Q-Learning. O protocolo repetido mostra um quadro mais cuidadoso:

- o agente escolhe bitrate médio maior;
- a ocupação do buffer oscila menos;
- o atraso inicial é maior;
- a vantagem de rebuffering depende do perfil do trace;
- o desempenho no cenário de rajadas é instável e impede concluir que há redução geral de rebuffering.

Esse comportamento indica limitação de generalização: os traces de treinamento estável e flutuante não representam adequadamente quedas curtas e severas. Os traces de avaliação devem permanecer congelados; melhorias posteriores devem introduzir novos traces de treinamento, sem reutilizar os traces reservados como dados de treino.

## Limites

- somente cinco sementes;
- traces sintéticos e curtos;
- tamanhos dos segmentos estimados pelo bitrate nominal;
- ausência de segmentos VVC reais, perda de pacotes, jitter e rede `tc/netem`;
- ICs descritivos para várias métricas, sem correção para comparações múltiplas;
- exclusão de zero do IC não deve ser tratada isoladamente como prova definitiva.

Os dados completos estão em:

- `protocol_raw_runs.csv`;
- `protocol_aggregate.csv`;
- `protocol_paired_differences.csv`;
- `protocol_training_summary.csv`.

## Reprodução

```bash
python run_protocol.py \
  --config protocol_config.json \
  --output-dir results/protocol
```
