# Documentação Técnica e Dataset

Este documento detalha as especificações do ambiente experimental, incluindo o dataset de vídeos e as versões das ferramentas utilizadas para garantir a reprodutibilidade dos resultados.

## Dataset de Vídeos

Para a avaliação com conteúdo VVC real, foram selecionadas sequências de teste padronizadas do CTC (*Common Test Conditions*) do VVC. A Etapa 5.2 fornece a automação reproduzível, mas os arquivos YUV, bitstreams e resultados medidos não são versionados neste repositório.

### Sequências Planejadas:
| Sequência | Resolução | Taxa de Quadros (fps) | Classe | Descrição |
| :--- | :--- | :--- | :--- | :--- |
| **Tango** | 3840x2160 | 60 | A1 | Conteúdo de alta dinâmica e detalhes finos. |
| **Campfire** | 3840x2160 | 30 | A2 | Texturas complexas e movimento orgânico. |
| **BQTerrace** | 1920x1080 | 60 | B | Cenário urbano com detalhes estáticos e dinâmicos. |
| **BasketballDrive** | 1920x1080 | 50 | B | Movimento rápido e acompanhamento de câmera. |

**Nota:** As sequências originais estão em formato YUV 4:2:0 planar. Elas podem ser obtidas através dos repositórios oficiais do MPEG ou sites de datasets de vídeo acadêmicos como o [Xiph.org](https://media.xiph.org/video/derf/).

## Versões das Ferramentas

A arquitetura experimental congela as seguintes versões recomendadas. O arquivo de proveniência registra as versões realmente encontradas em cada execução:

- **Codificador VVC (VVenC):** versão 1.14.0 (mínimo 1.13.0 para `idr_no_radl`).
- **Decodificador VVC (VVdeC):** versão instalada registrada por `vvdecapp --version`.
- **Simulador de Rede:** `tc/netem` integrado ao Kernel Linux 5.x ou superior.
- **Python:** Versão 3.10+ (utilizado para o agente Q-Learning e scripts de métricas).
- **NumPy:** Versão 1.24+ (para processamento de matrizes e Q-table).

As opções de linha de comando seguem a [documentação oficial de uso do VVenC](https://github.com/fraunhoferhhi/vvenc/wiki/Usage), e a versão congelada pode ser conferida nas [releases oficiais](https://github.com/fraunhoferhhi/vvenc/releases).

## Controlador Q-Learning Simulado

Na segunda etapa, o agente é treinado no ambiente determinístico de segmentos. A configuração padrão utiliza:

- 4 representações: 500, 1000, 2000 e 4000 kbps;
- segmentos de 2 segundos;
- buffer inicial de 4 segundos e máximo de 20 segundos;
- 4000 episódios;
- taxa de aprendizado 0,1 e fator de desconto 0,95;
- epsilon inicial 1,0, mínimo 0,05 e decaimento 0,995;
- estado formado por buffer, bitrate e throughput anterior;
- três ações: diminuir, manter ou aumentar um nível.

Os arquivos de modelo são artefatos derivados e devem ser reproduzidos pelo script `train_q_learning.py`. Cada modelo contém os hiperparâmetros e pesos da recompensa usados no treinamento.

## Protocolo Estatístico

O arquivo `protocol_config.json` congela a configuração da terceira etapa:

- cinco sementes de treinamento independentes;
- dois traces exclusivos para treinamento;
- três traces exclusivos para avaliação;
- comparação pareada entre Q-Learning e baseline;
- IC95% bilateral da média com distribuição t de Student.

Para os resultados por trace, cada semente representa uma observação. Para o resultado geral, os traces são primeiro promediados dentro de cada semente e somente então é calculado o intervalo entre sementes. O protocolo não trata os três traces de uma mesma política como repetições independentes.

O sinal da diferença pareada segue `Q-Learning - Estático`. Assim, valores negativos favorecem o Q-Learning para rebuffering, atraso inicial e variabilidade do buffer; valores positivos o favorecem para bitrate médio.

## Protocolo de Generalização

A Etapa 4 mantém constantes o ambiente, a recompensa, o número de episódios e as cinco sementes. O treinamento robusto difere somente pela randomização de domínio aplicada em memória aos traces `stable.csv` e `fluctuating.csv`:

- escala global entre 0,85 e 1,15;
- jitter multiplicativo de até 8%;
- deslocamento circular do ponto inicial;
- uma ou duas quedas por episódio, com duração entre um e três segmentos;
- largura de banda durante a queda multiplicada por um fator entre 0,20 e 0,50;
- piso de 300 kbps.

A transformação é aplicada em 75% dos episódios e é reproduzível pela semente `training_seed * 1000003 + episode`. Dois traces exclusivos de validação foram usados para selecionar essa intensidade entre três candidatas. Os três traces de avaliação permanecem inalterados e nunca são fornecidos ao treinamento.

O resultado principal deve ser lido como um compromisso: a política robusta reduz interrupções, mas usa bitrate menor que a política Q-Learning original. A tabela completa e as limitações metodológicas estão em `results/generalization_results.md`.

## Manifesto de Segmentos — Etapa 5.1

O ambiente aceita um `SegmentManifest` opcional. Quando ausente, preserva o modelo nominal das etapas anteriores. Quando presente, cada decisão de bitrate consulta o par `(segmento, representação)` e usa o tamanho medido em bytes e a duração registrada.

O CSV exige `sequence`, `segment`, `bitrate_kbps`, `duration_s` e `size_bytes`. PSNR-Y, caminho do payload e SHA-256 são opcionais. O carregador rejeita segmentos não consecutivos, representações ausentes, duplicatas, durações divergentes entre representações e valores inválidos.

O tempo de download passa a ser:

```text
download_time_s = (size_bytes * 8 / 1000) / bandwidth_kbps
```

A duração medida também é usada no acréscimo ao buffer, no controle de overflow, na duração total do vídeo e na normalização da penalidade de rebuffering. A métrica `average_payload_bitrate_kbps` representa a taxa efetivamente transferida e entra automaticamente nos IC95% quando o protocolo usa manifesto. O hash do manifesto e seus metadados são persistidos nos modelos e resumos. `psnr_y_db` já aparece nos logs por segmento, mas sua incorporação à recompensa pertence a uma etapa posterior.

O contrato detalhado está em `segment_manifests/README.md`. `example_segments.csv` contém apenas dados ilustrativos e não deve ser citado como codificação VVC real.

## Pipeline VVC — Etapa 5.2

`generate_vvc_segments.py` lê `vvc_pipeline_config.example.json` e expande uma matriz completa de segmentos e representações. Cada item é codificado separadamente com VVenC em controle de taxa de duas passagens. O valor nominal em kbps é multiplicado por 1000, pois a opção `--bitrate` do VVenC recebe bits por segundo.

Cada comando fixa explicitamente resolução, taxa de quadros racional, formato de entrada, profundidade interna, número e deslocamento de quadros, preset, QPA, threads, perfil de multithreading e tipo de refresh. O padrão `idr_no_radl`, disponível desde o VVenC 1.13, inicia períodos com IDR sem imagens líderes e evita dependência externa ao segmento. Como cada arquivo `.266` é codificado isoladamente, o payload registrado é independentemente decodificável.

Essa escolha inclui em cada payload o custo de acesso aleatório, parameter sets e demais cabeçalhos do bitstream bruto. Ela representa um conjunto controlado de objetos VVC independentes, não um empacotamento DASH/CMAF. Uma avaliação posterior com `.m4s` deverá medir o arquivo de contêiner completo e declarar separadamente seu overhead.

Quando `compute_psnr_y` está ativo, o VVdeC reconstrói cada bitstream. O cálculo de PSNR-Y compara essa reconstrução com os quadros correspondentes na fonte completa, usando `start_frame + segment × frames_per_segment`. Quadros idênticos recebem 100 dB para manter a convenção histórica do projeto. As reconstruções podem ser removidas depois da medição; os bitstreams, logs, hashes e comandos permanecem rastreáveis.

O pipeline produz dois documentos:

1. `*.csv`: manifesto consumido pelo simulador, contendo tamanho, duração, PSNR-Y, caminho e SHA-256 de cada payload;
2. `*.provenance.json`: configuração normalizada, hash da fonte, do JSON e do módulo do pipeline, commit Git, versões das ferramentas, plataforma e comandos completos.

Antes da codificação, o tamanho do YUV deve ser múltiplo do tamanho esperado de um quadro 4:2:0. Também deve haver quadros suficientes para todos os segmentos. Não há repetição ou preenchimento silencioso de conteúdo. O modo `--dry-run` permite auditar todos os comandos sem exigir a presença da fonte ou dos executáveis.

O exemplo BQTerrace prevê cinco segmentos de 2 s. Isso é suficiente para validar o fluxo, não para executar os traces de avaliação de 30 segmentos. Para o experimento completo, deve-se usar uma fonte de pelo menos 60 s ou construir externamente uma sequência composta, registrando a composição e seu hash como parte do dataset.

## Parâmetros de Codificação (VVenC)

Para os experimentos, o VVenC é configurado com os seguintes parâmetros base:
- **Preset:** `medium` (equilíbrio entre eficiência e tempo de codificação).
- **Controle de taxa:** duas passagens, com QPA habilitado.
- **Refresh:** `idr_no_radl` para independência entre arquivos de segmento.
- **Paralelismo:** oito threads e `mt_profile=0` no exemplo versionado.
- **Bitrate:** escada nominal de 500, 1000, 2000 e 4000 kbps.
- **Formato:** YUV 4:2:0 de 8 ou 10 bits, sem conversão implícita de profundidade.
