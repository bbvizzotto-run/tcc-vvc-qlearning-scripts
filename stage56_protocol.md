# Protocolo multicontéudo VVC — Etapa 5.6

## Estado e separação das etapas

Este documento foi versionado na Etapa 5.6a, antes da primeira execução nos
traces `stage56_evaluation_*`. Nessa etapa são permitidos somente geração
determinística, registro de hashes, validação estrutural e testes com fixtures
sintéticas. A Etapa 5.6b será a única execução da matriz final. Alterar qualquer
entrada congelada exige declarar um novo protocolo e novos traces; não é
permitido ajustar parâmetros após observar os resultados finais.

## Questão experimental

O controlador Q-Learning com recompensa e guarda de startup selecionadas nas
Etapas 5.3–5.4 mantém desempenho competitivo quando avaliado de forma
balanceada em quatro conteúdos VVC controlados, com escadas e tamanhos de
segmento medidos?

## Entradas congeladas

- Conteúdos: Big Buck Bunny, Elephants Dream, Sita Sings the Blues e Tears of
  Steel.
- Cada manifesto: 60 segmentos independentes de 1 s, quatro representações,
  tamanho real, SHA-256 e PSNR-Y.
- Sementes de treinamento: `11, 23, 37, 53, 71, 89, 107, 131, 149, 173`.
  As cinco primeiras preservam o protocolo anterior; as cinco seguintes são
  primos fixados antes da avaliação.
- Treino: `stable.csv` e `fluctuating.csv`, ambos com escala 1.
- Avaliação: três traces novos, gerados pelas sementes `56901`, `56902` e
  `56903`, com regimes iniciais baixo, médio e alto e escala 1.
- Validação técnica: três traces distintos, gerados por `56101`, `56102` e
  `56103`. Eles não serão usados para escolher parâmetros desta avaliação.
- Controladores: estático, throughput, BOLA-BASIC, RobustMPC e Q-Learning.
- Episódios por Q-table: 4000.
- Recompensa: `quality=1`, `rebuffering=10`, `switch=0,25`, `low_buffer=2`,
  `startup=0,5`, buffer-alvo de 8 s e guarda de startup ativa.

Os parâmetros completos e legíveis por máquina estão em
`stage56_multicontent_comparison_config.json`.

## Unidade de treino e avaliação

O treinamento é específico por conteúdo. Cada uma das dez sementes produz uma
Q-table independente para cada conteúdo, totalizando 40 treinamentos. Essa
escolha testa repetibilidade e desempenho dentro das escadas medidas, mas não
testa transferência para conteúdo não visto.

Cada política é avaliada nos três traces finais; os quatro baselines usam
exatamente as mesmas combinações conteúdo–semente–trace. A matriz contém 600
linhas agregadas de execução:

```text
4 conteúdos × 10 sementes × 3 traces × 5 controladores = 600
```

## Inferência pré-especificada

O contraste primário único é:

```text
Q-Learning − RobustMPC em mean_objective_reward
escopo: média balanceada dos quatro conteúdos por semente
intervalo: IC95% bilateral t de Student
```

O contraste favorece Q-Learning somente se todo o IC95% estiver acima de zero;
favorece RobustMPC se estiver abaixo de zero; caso contrário, é inconclusivo.
Como há um único contraste primário, não há família de testes primários que
exija correção de multiplicidade. Todas as demais comparações são secundárias
ou descritivas e não sustentam, isoladamente, alegação confirmatória.

As métricas secundárias são startup, rebuffering, taxa de rebuffering, bitrate
selecionado, bitrate útil medido, média e desvio-padrão do buffer, utilidade de
qualidade, PSNR-Y, trocas e fração na representação mais alta.

## Agregação

Para cada controlador e métrica:

1. calcula-se a média dos três traces dentro de cada conteúdo e semente;
2. calcula-se a média dos quatro conteúdos, com peso igual, dentro da semente;
3. calcula-se o IC95% entre as dez médias de semente.

A semente é a unidade estatística independente (`n=10`). Traces, conteúdos e
segmentos são medidas repetidas e não aumentam `n`. Também serão emitidos
resultados por conteúdo e por par conteúdo–trace para diagnóstico.

## Integridade e execução única

`run_multi_content_comparison.py` cria o diretório de saída e o arquivo
`.execution_started.json` de forma exclusiva antes de carregar valores dos
traces finais. Se o diretório já existir, a execução é recusada. A saída inclui
CSV bruto, agregações, diferenças pareadas, diagnóstico do treinamento e um
manifesto com hashes de entradas e artefatos.

O comando congelado é:

```bash
python run_multi_content_comparison.py \
  --config stage56_multicontent_comparison_config.json \
  --output-dir results/stage56_multicontent_final
```

Ele só deve ser executado depois que a Etapa 5.6a estiver revisada e integrada.

## Limites declarados

- Os traces são sintéticos e modelam capacidade de enlace, não perda, RTT ou
  concorrência de tráfego.
- O Q-Learning otimiza utilidade normalizada de bitrate; PSNR-Y é uma métrica
  observada, não um termo direto da recompensa.
- As políticas são treinadas por conteúdo. Generalização para vídeo não visto
  requer um protocolo separado, preferencialmente *leave-one-content-out*.
- PSNR-Y não mede sozinho qualidade perceptual. VMAF ou métricas subjetivas
  podem compor trabalhos posteriores, sem alterar retrospectivamente este
  protocolo.
