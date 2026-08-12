# Etapa 5.3a — seleção da recompensa DVB em validação

## Escopo

Esta etapa seleciona uma única recompensa antes da avaliação final. Os seis candidatos usam o manifesto DVB-DASH UHD1 HFR, cinco sementes, 4000 episódios e os mesmos hiperparâmetros. Apenas os traces de treino e validação são carregados.

## Regra de seleção

1. Calcular, por semente, a média dos dois traces de validação.
2. Estimar o IC95% pareado de `Q-Learning - Estático` entre sementes.
3. Aceitar somente candidatos cujo limite superior do IC95% da taxa de rebuffering seja ≤ 0 ponto percentual.
4. Entre os elegíveis, maximizar o bitrate útil médio; em caso de empate, usar o menor limite superior de rebuffering e o identificador.
5. Se nenhum for elegível, minimizar o limite superior de rebuffering.

## Resultado

| Candidato | `wr` | `wb` | Δ rebuffering (p.p.) | IC95% (p.p.) | Δ payload (kbps) | Elegível |
| :--- | ---: | ---: | ---: | :--- | ---: | :---: |
| `wr10_wb2` | 10 | 2 | 0,00 | [0,00; 0,00] | 0,00 | Sim |
| `wr20_wb2` | 20 | 2 | 0,00 | [0,00; 0,00] | 0,00 | Sim |
| `wr30_wb2` | 30 | 2 | 0,00 | [0,00; 0,00] | 0,00 | Sim |
| `wr10_wb1` | 10 | 1 | 14,59 | [4,46; 24,71] | 1382,57 | Não |
| `wr20_wb1` | 20 | 1 | 14,59 | [4,46; 24,71] | 1224,05 | Não |
| `wr30_wb1` | 30 | 1 | 10,94 | [-1,46; 23,34] | 918,03 | Não |

Foi selecionado `wr10_wb2`, a alteração mínima em relação à recompensa original: apenas `low_buffer_weight` passa de 1 para 2. Os três candidatos elegíveis produziram a mesma política conservadora e empataram nas métricas; por isso, o critério determinístico escolheu o menor identificador após o empate.

O resultado não demonstra superioridade sobre o baseline: ele remove, na validação, a degradação de rebuffering ao custo de também remover o ganho de bitrate. A próxima etapa deve executar `dvb_uhd1_hfr_selected_protocol_config.json` uma única vez nos três traces finais e preservar o resultado, favorável ou não.

## Integridade experimental

- avaliação executada durante a seleção: **não**;
- traces reservados: `evaluation_gradual.csv`, `evaluation_bursty.csv`, `evaluation_challenging.csv`;
- resultados completos: `candidate_selection.csv`, `validation_paired_differences.csv`, `validation_raw_runs.csv` e `training_summary.csv`;
- configuração final: `dvb_uhd1_hfr_selected_protocol_config.json`.
