# Validação da Integração — Etapa 2

Esta validação verifica se o treinamento, a persistência do modelo, a avaliação sem exploração e a comparação com o baseline funcionam de ponta a ponta. Ela utiliza somente o trace `evaluation_challenging.csv`, com semente 42, após treinamento nos traces `stable.csv` e `fluctuating.csv`.

| Controlador | Bitrate médio (kbps) | Atraso inicial (s) | Rebuffering (s) | Taxa de rebuffering (%) | Desvio padrão do buffer (s) |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Estático | 1200,00 | 0,5013 | 19,1506 | 31,9176 | 3,3544 |
| Q-Learning | 1700,00 | 1,5288 | 8,0880 | 13,4800 | 1,7831 |

## Interpretação restrita

Nesta execução, o Q-Learning combinou bitrate médio mais alto com menos rebuffering, mas apresentou atraso inicial maior. O trace contém períodos com capacidade inferior ao menor bitrate disponível, portanto alguma interrupção é inevitável.

Esses números **não constituem uma conclusão científica** sobre superioridade do controlador: representam um trace, uma semente e parâmetros ainda não submetidos a análise de sensibilidade. A etapa experimental completa deverá utilizar múltiplos traces, sementes, repetições e intervalos de confiança.

## Reprodução

```bash
python train_q_learning.py \
  --trace bandwidth_traces/stable.csv \
  --trace bandwidth_traces/fluctuating.csv \
  --model models/q_learning.npz \
  --history results/training/q_learning.csv \
  --seed 42

python compare_controllers.py \
  --model models/q_learning.npz \
  --trace bandwidth_traces/evaluation_challenging.csv \
  --output results/comparisons/challenging.csv \
  --seed 42
```
