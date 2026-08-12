# Generalização a Rajadas — Etapa 4

A Etapa 4 introduz randomização de domínio somente durante o treinamento. Cada episódio parte de `stable.csv` ou `fluctuating.csv` e pode receber deslocamento circular, escala de capacidade, jitter multiplicativo e quedas curtas. Os traces de validação e os três traces congelados de avaliação nunca são fornecidos a `train_q_learning`.

Foram avaliadas três intensidades predefinidas nos traces independentes `validation_bursty` e `validation_mixed`. O critério foi: **maximizar o bitrate médio entre candidatos cujo IC95% da diferença de rebuffering frente ao baseline não ultrapassasse zero**. A configuração moderada foi selecionada antes da interpretação final dos benchmarks congelados.

## Seleção na validação

| Intensidade | Delta de rebuffering vs. estático (s) [IC95%] | Delta de bitrate (kbps) [IC95%] | Decisão |
| :--- | ---: | ---: | :--- |
| Forte | -15,084 [-15,084; -15,084] | -175,00 [-237,50; -112,50] | Rejeitada: perda clara de qualidade |
| Moderada | -11,030 [-17,324; -4,737] | +156,67 [0,73; 312,61] | Selecionada |
| Leve | -4,608 [-14,625; 5,409] | +371,67 [139,57; 603,76] | Rejeitada: restrição de rebuffering não garantida |

## Resultado nos benchmarks congelados

| Métrica | Estático | Q-Learning original | Q-Learning robusto | Robusto - estático [IC95%] |
| :--- | ---: | ---: | ---: | ---: |
| Atraso inicial (s) | 0,444 | 1,255 | 1,029 | +0,584 [0,208; 0,961] |
| Rebuffering (s) | 16,645 | 19,778 | 2,767 | -13,878 [-18,150; -9,606] |
| Taxa de rebuffering (%) | 27,741 | 32,963 | 4,611 | -23,130 [-30,251; -16,010] |
| Bitrate médio (kbps) | 1433,33 | 1820,00 | 1304,44 | -128,89 [-330,82; 73,04] |
| Desvio padrão do buffer (s) | 3,418 | 2,188 | 2,890 | -0,528 [-1,096; 0,041] |

O treinamento robusto reduziu o rebuffering frente ao baseline e à política original. Comparado ao Q-Learning original, a redução foi de 17,011 s [IC95% -23,108; -10,915], acompanhada por redução de 515,56 kbps no bitrate médio [IC95% -894,97; -136,14]. Portanto, a melhora de robustez possui um custo de qualidade claramente mensurável.

## Resultado por trace congelado

| Trace | Delta de rebuffering robusto-estático (s) [IC95%] | Delta de bitrate (kbps) [IC95%] |
| :--- | ---: | ---: |
| Gradual | -0,318 [-0,318; -0,318] | -450,00 [-915,43; 15,43] |
| Bursty | -22,169 [-34,984; -9,355] | +176,67 [9,47; 343,87] |
| Challenging | -19,147 [-19,153; -19,142] | -113,33 [-155,74; -70,93] |

No cenário `evaluation_bursty`, que motivou a etapa, o controlador robusto simultaneamente reduziu rebuffering e aumentou bitrate frente ao baseline estático. Nos demais traces, a segurança adicional veio acompanhada por bitrate menor ou inconclusivo.

## Limitações

- apenas cinco sementes e traces sintéticos de 30 segmentos;
- a política robusta não prevê uma queda futura; ela aprende uma reserva de segurança;
- os parâmetros da randomização foram selecionados em somente dois traces de validação;
- a seleção compara três candidatos e não aplica correção para comparações múltiplas;
- os benchmarks já eram conhecidos da Etapa 3, embora não tenham sido usados pelo critério de seleção;
- continuam ausentes tamanhos reais de segmentos VVC, atraso, jitter, perda e execução com `tc/netem`.

## Reprodução

```bash
python run_generalization.py \
  --config generalization_config.json \
  --output-dir results/generalization
```

Os snapshots versionados são `generalization_raw_runs.csv`, `generalization_paired_differences.csv`, `generalization_training_summary.csv` e `generalization_candidate_selection.csv`.
