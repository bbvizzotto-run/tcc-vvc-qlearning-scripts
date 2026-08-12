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

Essa escolha inclui em cada payload o custo de acesso aleatório, parameter sets e demais cabeçalhos do bitstream bruto. Ela representa um conjunto controlado de objetos VVC independentes, não um empacotamento DASH/CMAF. A vertente DVB descrita adiante mede separadamente o payload ISO-BMFF transferível.

Quando `compute_psnr_y` está ativo, o VVdeC reconstrói cada bitstream. O cálculo de PSNR-Y compara essa reconstrução com os quadros correspondentes na fonte completa, usando `start_frame + segment × frames_per_segment`. Quadros idênticos recebem 100 dB para manter a convenção histórica do projeto. As reconstruções podem ser removidas depois da medição; os bitstreams, logs, hashes e comandos permanecem rastreáveis.

O pipeline produz dois documentos:

1. `*.csv`: manifesto consumido pelo simulador, contendo tamanho, duração, PSNR-Y, caminho e SHA-256 de cada payload;
2. `*.provenance.json`: configuração normalizada, hash da fonte, do JSON e do módulo do pipeline, commit Git, versões das ferramentas, plataforma e comandos completos.

Antes da codificação, o tamanho do YUV deve ser múltiplo do tamanho esperado de um quadro 4:2:0. Também deve haver quadros suficientes para todos os segmentos. Não há repetição ou preenchimento silencioso de conteúdo. O modo `--dry-run` permite auditar todos os comandos sem exigir a presença da fonte ou dos executáveis.

O exemplo BQTerrace prevê cinco segmentos de 2 s. Isso é suficiente para validar o fluxo, não para executar os traces de avaliação de 30 segmentos. Para o experimento completo, deve-se usar uma fonte de pelo menos 60 s ou construir externamente uma sequência composta, registrando a composição e seu hash como parte do dataset.

## Importação DVB-DASH — Etapa 5.2b

A vertente DVB complementa o pipeline controlado. Em vez de recodificar um YUV, `import_dvb_dash.py` recebe um MPD estático de um pacote local e produz o manifesto usado pelo mesmo ambiente. Isso permite avaliar o agente sobre objetos de entrega VVC efetivamente empacotados em ISO-BMFF/DASH, sejam arquivos `.m4s` ou byte ranges de um MP4.

O parser usa a biblioteca padrão do Python e cobre:

- herança de atributos entre `Period`, `AdaptationSet` e `Representation`;
- `BaseURL` local nos níveis do MPD;
- `SegmentTemplate` com `$RepresentationID$`, `$Bandwidth$`, `$Number$` e `$Time$`;
- especificadores numéricos, como `$Number%05d$`;
- `SegmentTimeline`, incluindo repetições positivas e `r=-1` com limite conhecido;
- `SegmentList` com duração fixa ou timeline;
- `SegmentBase` com caixa `sidx` e referências por byte range;
- seleção explícita de representações e limite opcional de segmentos.

MPDs dinâmicos, URLs remotas e múltiplos períodos de vídeo são rejeitados nesta versão para evitar uma composição temporal implícita. Todos os arquivos devem ser extraídos antes da medição. O importador também verifica codec VVC quando o atributo `codecs` está declarado.

Para cada segmento de mídia, são medidos tamanho e SHA-256. O segmento de inicialização é excluído porque o modelo atual toma uma decisão por segmento de mídia e não modela downloads de inicialização. A proveniência contém os hashes do MPD, do ZIP original quando fornecido, do importador e do manifesto, bem como os metadados das representações e os termos informados na linha de comando.

O atributo `bandwidth` é convertido de bits/s para kbps decimais e passa a identificar a ação no simulador. O agente e o baseline já aceitam qualquer quantidade de níveis, mas uma escada adaptativa exige pelo menos duas representações. O protocolo opcional gerado pelo importador copia o JSON-base e substitui `experiment_config.bitrates_kbps`, `segment_duration_s` e `segment_manifest`.

### Dataset DVB-DASH UHD1 HFR

O pacote oficial `vvc_uhd1_hfr.zip` tem SHA-256 `94325083843293ff06dc0403f3be1df881a70878a447be1ef1106817534f9695` e contém duas representações VVC de 3840×2160, SDR e 100 fps. O MPD declara 10.025.941 e 58.015.227 bit/s. Cada representação é um único MP4 com `SegmentBase`; os índices `sidx` descrevem 63 segmentos alinhados, totalizando exatamente 60 s.

Os segmentos variam entre 0,65 e 0,96 s. A representação inferior totaliza 75.251.762 bytes de mídia e taxa efetiva de 10.033,57 kbps; a superior totaliza 435.171.403 bytes e 58.022,85 kbps. Cabeçalhos anteriores ao primeiro byte range e áudio não entram no manifesto.

O conteúdo foi gravado por Martin Fähnrich (Panasonic), detentor dos direitos e licenciante sob Creative Commons Attribution 4.0. O texto, a URL da licença e os hashes estão preservados no arquivo de proveniência. O `psnr_y_db` fica vazio porque o master YUV exato não acompanha o pacote.

Os traces originais variam de 300 a 5.200 kbps, enquanto a menor representação exige cerca de 10 Mbps. O protocolo DVB aplica fator 10 às amostras de banda em memória, sem modificar os CSV. Essa escolha preserva as variações relativas e produz uma faixa de 3–52 Mbps, na qual a representação inferior é sustentável em parte do tempo e a superior apenas nos melhores intervalos. A escala é parte explícita do protocolo e dos metadados salvos.

PSNR-Y não é inferido. Sem o master YUV exato usado na produção do pacote, não existe referência válida para essa medição. Assim, a vertente DVB é usada para realismo de entrega e comportamento ABR; a vertente VVenC permanece responsável por controle de codificação e comparação objetiva com a fonte.

## Ajuste da Recompensa DVB — Etapa 5.3a

O ajuste varia somente `rebuffering_weight` em {10, 20, 30} e `low_buffer_weight` em {1, 2}. `quality_weight=1`, `switch_weight=0,25` e o buffer-alvo de 8 s permanecem fixos. Cada um dos seis candidatos usa as mesmas cinco sementes e 4000 episódios do protocolo DVB.

Treino, seleção e avaliação permanecem separados:

- treino: `stable.csv` e `fluctuating.csv`, ambos com fator 10;
- validação: `validation_bursty.csv` e `validation_mixed.csv`, ambos com fator 10;
- avaliação congelada: `evaluation_gradual.csv`, `evaluation_bursty.csv` e `evaluation_challenging.csv`.

O código de ajuste não abre os traces de avaliação. Um teste automatizado substitui o carregador por uma guarda que falha caso o caminho reservado seja acessado. Os nomes desses arquivos aparecem no manifesto apenas para auditar a separação experimental.

A unidade amostral é a semente. Primeiro se calcula, dentro de cada semente, a média das diferenças entre os dois traces de validação; depois se obtém o IC95% bilateral entre as cinco sementes. A regra pré-declarada considera elegível um candidato quando o limite superior do IC95% de `Q-Learning - Estático` para taxa de rebuffering é menor ou igual a zero. Entre elegíveis, o desempate primário maximiza a diferença média de bitrate útil.

O candidato `wr10_wb2` foi selecionado. Seus pesos são `(wq, wr, ws, wb) = (1, 10, 0,25, 2)`. Ele igualou o baseline em rebuffering e bitrate útil na validação. Os candidatos com `wb=1` selecionaram mais bitrate, mas o limite superior do IC95% da taxa de rebuffering ficou entre 23,34 e 24,71 pontos percentuais, portanto falharam na não inferioridade. A configuração segura não demonstrou ganho de QoE; sua utilidade nesta etapa é impedir a degradação observada no resultado preliminar.

`results/dvb_reward_tuning/manifest.json` registra a grade, a regra, os traces, os pesos escolhidos e a proteção contra vazamento. `dvb_uhd1_hfr_selected_protocol_config.json` é a entrada congelada para a Etapa 5.3b. Nenhuma métrica dos três traces finais foi consultada para essa escolha.

## Avaliação Final DVB — Etapa 5.3b

A configuração `wr10_wb2` foi executada uma única vez nos três traces reservados, depois de versionada na `main`. O arquivo usado corresponde ao Git blob `8116a8f7875e8de151dc9f16c92998f9c3b28f6f` e ao SHA-256 `f269dc48fd06a4de396602363b1d915ca88d94b286bd4a9504e43bac7c9a49e1`. Não houve ajuste posterior dos pesos.

### Resultado geral

| Métrica | Estático | Q-Learning | Diferença QL − estático (IC95%) | Interpretação |
| :--- | ---: | ---: | :--- | :--- |
| Atraso inicial (s) | 2,453 | 2,453 | 0,000 [0,000; 0,000] | empate |
| Rebuffering (s) | 2,816 | 2,816 | 0,000 [0,000; 0,000] | empate |
| Taxa de rebuffering (%) | 9,885 | 9,885 | 0,000 [0,000; 0,000] | empate |
| Bitrate selecionado (kbps) | 11.092 | 12.479 | +1.386 [1.024; 1.749] | maior no Q-Learning |
| Bitrate útil (kbps) | 13.272 | 14.741 | +1.468 [1.068; 1.868] | maior no Q-Learning |
| Buffer médio (s) | 3,884 | 3,909 | +0,024 [−0,017; 0,066] | sem diferença conclusiva |
| Desvio-padrão do buffer (s) | 1,740 | 1,534 | −0,207 [−0,248; −0,166] | menor no Q-Learning |

A unidade estatística continua sendo a semente: os três traces são promediados dentro de cada uma das cinco sementes antes do IC95%. A diferença de bitrate útil e a redução do desvio-padrão do buffer excluem zero. Rebuffering, taxa de rebuffering e atraso inicial são exatamente iguais entre as políticas.

### Resultado por cenário e comparação com a política anterior

Todo o ganho ocorreu em `evaluation_gradual`: +4.405 kbps de bitrate útil, IC95% [3.205; 5.605], e −0,620 s no desvio-padrão do buffer, IC95% [−0,743; −0,497]. Em `evaluation_bursty` e `evaluation_challenging`, o Q-Learning reproduziu as métricas do baseline. Portanto, o resultado geral não deve ser interpretado como ganho uniforme nos três cenários.

Na política anterior, o Q-Learning apresentava 4,470 s de rebuffering e 15,688% de taxa de rebuffering. A política selecionada reduziu descritivamente esses valores para 2,816 s e 9,885%, iguais ao baseline, enquanto manteve bitrate útil acima dele. Essa comparação com a política anterior é descritiva; a inferência principal permanece a comparação pareada da avaliação final.

O experimento ainda possui limitações: escada com apenas duas representações separadas por um fator de aproximadamente 5,8; traces de banda multiplicados por 10; cinco sementes; ausência de PSNR-Y; e um pacote DVB específico. Assim, a conclusão adequada é que a recalibração eliminou a degradação de rebuffering e obteve ganho secundário de bitrate útil e estabilidade nesse protocolo, não que o controlador seja universalmente superior.

`results/dvb_uhd1_hfr_selected_final/evaluation_attestation.json` registra o commit-base, o comando único e os hashes da configuração, dos traces e dos resultados. Os modelos NPZ são derivados e permanecem fora do Git.

## Parâmetros de Codificação (VVenC)

Para os experimentos, o VVenC é configurado com os seguintes parâmetros base:
- **Preset:** `medium` (equilíbrio entre eficiência e tempo de codificação).
- **Controle de taxa:** duas passagens, com QPA habilitado.
- **Refresh:** `idr_no_radl` para independência entre arquivos de segmento.
- **Paralelismo:** oito threads e `mt_profile=0` no exemplo versionado.
- **Bitrate:** escada nominal de 500, 1000, 2000 e 4000 kbps.
- **Formato:** YUV 4:2:0 de 8 ou 10 bits, sem conversão implícita de profundidade.
