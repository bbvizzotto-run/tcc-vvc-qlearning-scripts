# Resultados finais multicontéudo — Etapa 5.6b

## Estado da execução

O protocolo congelado na Etapa 5.6a foi executado uma única vez, sem alteração
de parâmetros após a observação dos traces finais. A matriz contém quatro
conteúdos VVC, dez sementes de treinamento, três traces de avaliação e cinco
controladores, totalizando 40 treinamentos específicos por conteúdo e 600
avaliações.

Os resultados abaixo usam a semente de treinamento como unidade estatística
independente (`n=10`). Os três traces são primeiro promediados dentro de cada
conteúdo e semente; os quatro conteúdos recebem peso igual dentro da semente;
o IC95% bilateral t de Student é então calculado entre as dez sementes.

## Contraste primário pré-especificado

O único contraste primário foi `Q-Learning − RobustMPC` na recompensa objetiva
média, no escopo balanceado entre conteúdos:

| Estimativa | Valor |
| :--- | ---: |
| Q-Learning | −0,647; IC95% [−0,746; −0,549] |
| RobustMPC | 0,028 |
| Diferença pareada | **−0,675; IC95% [−0,774; −0,577]** |

O intervalo está integralmente abaixo de zero. Portanto, o resultado primário
favorece RobustMPC e não sustenta superioridade ou não inferioridade do
Q-Learning no objetivo congelado.

O contraste foi negativo também quando cada conteúdo foi agregado
separadamente:

| Conteúdo | Q-Learning − RobustMPC | IC95% |
| :--- | ---: | :--- |
| Big Buck Bunny | −1,191 | [−1,356; −1,026] |
| Elephants Dream | −0,157 | [−0,221; −0,093] |
| Sita Sings the Blues | −0,438 | [−0,622; −0,253] |
| Tears of Steel | −0,916 | [−1,244; −0,588] |

## Médias gerais dos controladores

| Controlador | Recompensa | Rebuffering (%) | Startup (s) | Bitrate útil (kbps) | PSNR-Y (dB) | Desvio do buffer (s) | Trocas |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Estático | −0,133 | 1,242 | **1,736** | 2.305,1 | 44,426 | **3,382** | **3,92** |
| Throughput | −0,132 | **0,366** | 2,339 | 2.091,0 | 44,389 | 4,368 | 7,92 |
| BOLA-BASIC | −0,251 | 1,563 | **1,736** | 2.249,7 | 44,575 | 3,530 | 7,67 |
| RobustMPC | **0,028** | 0,446 | 2,913 | **2.364,8** | **44,777** | 3,711 | 7,50 |
| Q-Learning | −0,647 | 4,208 | **1,736** | 2.017,8 | 44,315 | 4,084 | 21,77 |

O destaque em cada coluna identifica o melhor valor orientado pela métrica;
empates de startup são mantidos.

## Diferenças secundárias

Em relação ao baseline estático, o Q-Learning:

- manteve o mesmo startup;
- aumentou a taxa de rebuffering em 2,966 pontos percentuais, IC95%
  [2,119; 3,813];
- reduziu o bitrate útil em 287,3 kbps, IC95% [−359,6; −214,9];
- reduziu PSNR-Y em 0,112 dB, IC95% [−0,220; −0,003];
- aumentou o desvio do buffer em 0,701 s, IC95% [0,553; 0,850];
- realizou 17,85 trocas adicionais, IC95% [16,74; 18,96].

Em relação ao controlador por throughput, o Q-Learning iniciou 0,602 s mais
rápido e reduziu o desvio do buffer em 0,284 s, IC95% [−0,432; −0,135]. Porém,
teve 3,842 pontos percentuais adicionais de rebuffering, bitrate útil 73,2 kbps
menor e 13,85 trocas adicionais. A diferença de PSNR-Y foi inconclusiva.

Em relação ao BOLA-BASIC e ao RobustMPC, o Q-Learning também apresentou menor
recompensa, mais rebuffering, menor bitrate útil, menor PSNR-Y, maior variação
do buffer e mais trocas. A vantagem observada foi o startup: igual ao BOLA e
1,176 s menor que o RobustMPC.

## Diagnóstico e interpretação

O resultado não confirma a hipótese de competitividade geral do Q-Learning
neste protocolo. A principal fragilidade foi a instabilidade da seleção: média
de 21,77 trocas em 60 segmentos, contra 3,92–7,92 nos comparadores. Essa
oscilação coexistiu com rebuffering elevado e não se converteu em maior bitrate
útil ou qualidade objetiva.

O treinamento visitou, conforme conteúdo e semente, aproximadamente 44,6% a
53,9% dos 168 estados tabulares. Essa cobertura parcial é uma hipótese
plausível para investigação futura, assim como a representação do estado e a
penalização de trocas, mas não demonstra causalidade e não autoriza ajuste
retroativo do experimento final.

Há uma exceção localizada: no trace de início baixo de Elephants Dream, o
Q-Learning superou RobustMPC em recompensa por 0,166, IC95% [0,095; 0,237].
Nos outros onze pares conteúdo–trace, o contraste primário foi negativo. Essa
exceção deve ser tratada como diagnóstico secundário, não como reversão da
conclusão geral.

## Limitações da inferência

- Os baselines são determinísticos e repetem o mesmo resultado nas dez
  sementes; por isso, seus ICs entre sementes têm largura zero. A incerteza dos
  contrastes reflete a variação do treinamento Q-Learning, não uma amostragem
  populacional de conteúdos ou redes.
- Os quatro conteúdos e três traces são conjuntos fixos. A inferência formal é
  entre sementes dentro desse benchmark, não para toda distribuição possível
  de vídeos e condições de rede.
- Os traces modelam largura de banda, mas não perda, RTT, concorrência ou
  jitter de pacotes.
- O agente foi treinado separadamente por conteúdo. Este experimento não mede
  generalização para um vídeo não observado.
- PSNR-Y é uma métrica de fidelidade e não substitui avaliação perceptual ou
  subjetiva.

## Conclusão

Sob o protocolo pré-registrado e os quatro conteúdos VVC medidos, RobustMPC
obteve desempenho significativamente superior ao Q-Learning no desfecho
primário. O Q-Learning preservou atraso inicial baixo, mas apresentou uma
política excessivamente oscilatória, com mais rebuffering e menor bitrate útil.
O achado deve ser publicado como resultado negativo metodologicamente
controlado e como evidência para redesenhar o estado/treinamento em uma nova
etapa exploratória, sem reusar estes traces como novo holdout.
