# Resultados preliminares — DVB-DASH VVC UHD1 HFR

## Escopo

Esta execução valida de ponta a ponta a integração de um pacote DVB-DASH VVC real com o ambiente de streaming e o protocolo multi-semente. Os resultados são preliminares: avaliam a política existente sem reajuste específico para a escada DVB de apenas dois níveis e grande distância entre representações.

## Dataset e protocolo

- pacote: `DVB-DASH VVC UHD1 HFR`;
- resolução e taxa: 3840×2160, SDR, 100 fps;
- representações declaradas: 10.026 e 58.015 kbps;
- 63 segmentos alinhados, totalizando 60 s;
- durações: 0,65 s no primeiro segmento, 0,79 s no último e 0,96 s nos demais;
- tamanhos obtidos dos byte ranges `sidx` dos MP4;
- cinco sementes: 11, 23, 37, 53 e 71;
- 4.000 episódios de treinamento por semente;
- traces de banda multiplicados por 10 em memória, resultando em faixa de 3–52 Mbps;
- comparação pareada `Q-Learning − Estático`, com IC95% t de Student entre sementes.

O fator 10 é explícito em `dvb_uhd1_hfr_protocol_config.json`. Ele preserva a variação relativa dos traces originais e evita um cenário em que nem o nível inferior seria sustentável. Não é uma medição de uma rede UHD real e deve ser descrito como transformação experimental.

## Resultado geral

| Métrica | Estático | Q-Learning | Diferença QL − estático (IC95%) | Leitura |
| :--- | ---: | ---: | ---: | :--- |
| Atraso inicial (s) | 2,453 | 2,551 | +0,097 [−0,173; 0,367] | sem diferença conclusiva |
| Rebuffering (s) | 2,816 | 4,470 | +1,653 [0,506; 2,801] | pior para Q-Learning |
| Taxa de rebuffering (%) | 9,885 | 15,688 | +5,803 [1,776; 9,831] | pior para Q-Learning |
| Bitrate selecionado médio (kbps) | 11.092 | 13.652 | +2.559 [1.124; 3.995] | maior para Q-Learning |
| Taxa efetiva média (kbps) | 13.272 | 15.695 | +2.423 [1.324; 3.521] | maior para Q-Learning |
| Buffer médio (s) | 3,884 | 3,278 | −0,607 [−0,854; −0,359] | descritivo |
| Desvio-padrão do buffer (s) | 1,740 | 1,372 | −0,369 [−0,492; −0,245] | menor para Q-Learning |

## Interpretação

A política Q-Learning escolheu o nível de 58 Mbps com maior frequência e, por isso, aumentou o bitrate médio e a taxa efetivamente transferida. Esse ganho veio acompanhado de mais rebuffering. Portanto, esta execução não sustenta a conclusão de que a política atual supera o baseline na escada DVB.

A escada contém somente dois níveis separados por um fator aproximado de 5,8. Nessa condição, uma única ação de aumento salta de cerca de 10 para 58 Mbps. A recompensa e os limites de estado foram definidos originalmente para quatro representações mais próximas; o comportamento mais agressivo indica que eles precisam ser recalibrados antes da comparação final.

O menor desvio-padrão do buffer não deve ser interpretado isoladamente como melhoria: ele ocorre junto de buffer médio menor e mais interrupções. A taxa de rebuffering permanece a métrica crítica nesta etapa.

## Próxima etapa recomendada

1. realizar busca controlada dos pesos de rebuffering, troca e déficit de buffer usando somente os traces de validação;
2. testar treinamento robusto com quedas escaladas para a faixa do dataset;
3. comparar a política selecionada uma única vez nos três traces reservados de avaliação;
4. manter estes resultados como baseline honesto da política anterior, sem substituir ou ocultar o resultado desfavorável;
5. avaliar futuramente um pacote com três níveis ou uma escada controlada VVenC com intervalos menores.

Os CSV desta pasta preservam as execuções, agregações, diferenças pareadas e resumos de treinamento. Os modelos NPZ não são versionados e podem ser reproduzidos pelo protocolo congelado.
