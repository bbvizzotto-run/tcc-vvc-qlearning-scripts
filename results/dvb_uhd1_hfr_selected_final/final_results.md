# Etapa 5.3b — avaliação final da recompensa DVB

## Protocolo congelado

- candidato: `wr10_wb2`;
- pesos `(wq, wr, ws, wb)`: `(1, 10, 0,25, 2)`;
- buffer-alvo: 8 s;
- sementes: 11, 23, 37, 53 e 71;
- treinamento: 4000 episódios por semente;
- avaliação: `evaluation_gradual`, `evaluation_bursty` e `evaluation_challenging`;
- configuração selecionada apenas nos traces independentes de validação;
- execuções desta avaliação final: uma.

## Resultado geral

| Métrica | Estático | Q-Learning | Δ QL − estático | IC95% da diferença |
| :--- | ---: | ---: | ---: | :--- |
| Atraso inicial (s) | 2,453 | 2,453 | 0,000 | [0,000; 0,000] |
| Rebuffering (s) | 2,816 | 2,816 | 0,000 | [0,000; 0,000] |
| Taxa de rebuffering (%) | 9,885 | 9,885 | 0,000 | [0,000; 0,000] |
| Bitrate selecionado (kbps) | 11.092 | 12.479 | +1.386 | [1.024; 1.749] |
| Bitrate útil (kbps) | 13.272 | 14.741 | +1.468 | [1.068; 1.868] |
| Buffer médio (s) | 3,884 | 3,909 | +0,024 | [−0,017; 0,066] |
| Desvio-padrão do buffer (s) | 1,740 | 1,534 | −0,207 | [−0,248; −0,166] |

O Q-Learning igualou o baseline nas métricas de interrupção e apresentou maior bitrate útil e menor variabilidade do buffer. Os IC95% dessas duas diferenças secundárias excluem zero.

## Heterogeneidade entre traces

O ganho não foi uniforme. Em `evaluation_gradual`, o bitrate útil aumentou 4.405 kbps e o desvio-padrão do buffer diminuiu 0,620 s. Em `evaluation_bursty` e `evaluation_challenging`, todas as métricas foram idênticas às do baseline. A média geral distribui o ganho do cenário gradual pelos três traces.

## Leitura científica

A política anterior obtinha bitrate maior ao custo de rebuffering significativamente pior. A recalibração removeu essa degradação na avaliação congelada: rebuffering e atraso inicial passaram a empatar com o baseline, enquanto parte do ganho de bitrate foi preservada.

Isso não demonstra superioridade universal. A conclusão é restrita ao pacote DVB-DASH UHD1 HFR, à escada de duas representações, aos traces escalados e às cinco sementes. Não há PSNR-Y porque o master YUV exato não acompanha o pacote.

Os CSV preservam dados brutos, agregações e diferenças pareadas. `evaluation_attestation.json` registra os hashes e o comando da execução única. Os modelos NPZ são artefatos reproduzíveis e não são versionados.
