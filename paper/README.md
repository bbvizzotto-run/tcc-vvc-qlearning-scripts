# Etapa 5.7a — pacote científico congelado

**Título do manuscrito:** *QoE-Aware Adaptive Streaming under Content-Dependent
VVC Segment Variability: Model-Based Control versus Tabular Reinforcement
Learning*

Esta etapa encerra a expansão experimental. Todas as tabelas e figuras são
derivadas exclusivamente da execução final da Etapa 5.6b, publicada no commit
`efc5aa3be155e5533cd16f17fc76354a73ae46c7`. O gerador valida os SHA-256 dos
resultados e dos quatro manifestos VVC antes de produzir qualquer artefato.

## Geração

```bash
python -m pip install -r requirements-paper.txt
python generate_paper_assets.py
```

Os arquivos vetoriais SVG e PDF são gravados em `paper/generated/figures/`.
As tabelas são produzidas simultaneamente em CSV, Markdown e LaTeX em
`paper/generated/tables/`. `asset_manifest.json` registra o hash de cada
entrada e saída.

## Figuras principais

1. Pipeline experimental completo.
2. Variabilidade taxa--qualidade dos 960 segmentos VVC independentes.
3. Comparação das seis métricas centrais entre os cinco controladores.
4. Forest plot do contraste primário Q-Learning − RobustMPC.
5. Compromisso entre atraso inicial e taxa de rebuffering.
6. Contraste primário por conteúdo e trace de avaliação.

`figure_s1_qlearning_state_coverage` é uma figura suplementar para discutir a
cobertura parcial do espaço tabular. A incerteza dos gráficos decorre das dez
sementes do Q-Learning; os baselines determinísticos repetem o mesmo valor.

## Regra de encerramento

Esta etapa não reexecuta o holdout, não altera parâmetros e não cria novos
resultados experimentais. Novas execuções somente deverão ocorrer se forem
solicitadas durante a revisão por pares e deverão ser identificadas como uma
análise adicional.
