# Correção Dinâmica da Ocupação de Buffer em Streaming com Codificação VVC via Aprendizado por Reforço

## Visão Geral do Projeto

Este repositório contém scripts e materiais relacionados ao trabalho de conclusão de curso que propõe uma arquitetura para a correção dinâmica da ocupação de buffer em aplicações de streaming que utilizam o padrão de codificação Versatile Video Coding (VVC). A solução é baseada em Aprendizado por Reforço, empregando o algoritmo Q-Learning para otimizar a estabilidade do buffer e a Qualidade de Experiência (QoE) em transmissões de vídeo sob condições de rede instáveis.

## Status da Implementação

O desenvolvimento está organizado em etapas verificáveis. As Etapas 1 e 2 implementam o ambiente, o baseline e o Q-Learning. A Etapa 3 adiciona o protocolo estatístico, a Etapa 4 melhora a generalização a rajadas e a Etapa 5.1 conecta tamanhos medidos ao simulador. A **Etapa 5.2** automatiza a codificação controlada com VVenC, a **Etapa 5.2b** importa pacotes DVB-DASH VVC reais, a **Etapa 5.3** seleciona a recompensa em validação e a avalia uma única vez nos benchmarks congelados, a **Etapa 5.4a** adiciona baselines competitivos, a **Etapa 5.4b** corrige o objetivo de startup e congela um novo holdout e a **Etapa 5.4c** executa esse holdout uma única vez.

| Componente | Estado atual |
| :--- | :--- |
| Ambiente de segmentos, buffer, atraso inicial e rebuffering | Implementado |
| Traces de banda estável e flutuante | Implementado |
| Controlador por limiares estáticos | Implementado |
| Logs CSV e resumo JSON | Implementado |
| Testes automatizados do simulador e baseline | Implementado |
| Treinamento e avaliação do Q-Learning | Implementado |
| Persistência da Q-table e metadados experimentais | Implementado |
| Comparação automatizada com o baseline | Implementado |
| Protocolo multi-semente com IC95% | Implementado |
| Análise pareada por trace e geral | Implementado |
| Treinamento robusto com randomização de domínio | Implementado |
| Validação independente de intensidade de rajadas | Implementado |
| Manifesto e simulação com tamanhos reais de segmentos | Implementado |
| Pipeline de geração e medição de segmentos VVC reais | Implementado |
| Importador de MPD, segmentos e byte ranges DVB-DASH | Implementado |
| Proveniência, licença e configuração de protocolo DVB | Implementado |
| Dataset DVB-DASH UHD1 HFR e manifesto medido | Implementado |
| Ajuste controlado da recompensa apenas em validação | Implementado |
| Avaliação final da recompensa selecionada | Implementado (Etapa 5.3b) |
| Comparação com throughput, BOLA-BASIC e RobustMPC | Implementado (Etapa 5.4a) |
| Recompensa com startup e guarda pré-reprodução | Selecionada em validação (Etapa 5.4b) |
| Avaliação no novo holdout de 60 segmentos | Executada uma única vez (Etapa 5.4c) |
| Dataset VVC real e resultados completos | Pendente de execução com as fontes YUV |
| Rede `tc/netem` | Pendente |

### Instalação e testes

Requer Python 3.10 ou superior. Na raiz do repositório, execute:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

### Treinamento do Q-Learning

```bash
python train_q_learning.py \
  --trace bandwidth_traces/stable.csv \
  --trace bandwidth_traces/fluctuating.csv \
  --episodes 4000 \
  --model models/q_learning.npz \
  --history results/training/q_learning.csv \
  --seed 42
```

O arquivo NPZ armazena a Q-table, os hiperparâmetros e os metadados necessários para reconstruir o estado e a recompensa. Os modelos gerados não são versionados porque devem ser reproduzidos pelo comando acima.

### Avaliação sem exploração

```bash
python run_experiment.py \
  --controller q-learning \
  --model models/q_learning.npz \
  --trace bandwidth_traces/evaluation_challenging.csv \
  --output results/runs/q_learning_challenging_seed42.csv \
  --seed 42
```

Para executar o baseline no mesmo trace:

```bash
python run_experiment.py \
  --controller static \
  --trace bandwidth_traces/evaluation_challenging.csv \
  --output results/runs/static_challenging_seed42.csv \
  --seed 42
```

Ou gere diretamente uma tabela comparativa:

```bash
python compare_controllers.py \
  --model models/q_learning.npz \
  --trace bandwidth_traces/evaluation_challenging.csv \
  --output results/comparisons/challenging.csv \
  --seed 42
```

Cada execução produz dados por segmento em CSV e um arquivo `*.summary.json` com métricas agregadas e parâmetros.

### Protocolo experimental multi-semente

O protocolo versionado executa cinco sementes, três traces reservados para avaliação e os dois controladores:

```bash
python run_protocol.py \
  --config protocol_config.json \
  --output-dir results/protocol
```

São produzidos:

- `raw_runs.csv`: métricas de cada combinação semente–trace–controlador;
- `aggregate.csv`: médias, desvios padrão e IC95% por trace e gerais;
- `paired_differences.csv`: diferenças Q-Learning–estático pareadas;
- `training_summary.csv`: diagnóstico de cada treinamento;
- `manifest.json`: configuração e método estatístico;
- `models/`: Q-tables geradas para cada semente.

O resultado geral é calculado entre sementes após obter a média dos traces dentro de cada semente. Assim, medições repetidas nos mesmos traces não aumentam artificialmente o tamanho amostral.

### Generalização a rajadas

A comparação entre o treinamento original e o robusto utiliza os mesmos hiperparâmetros, recompensa e sementes. A única diferença é o aumento determinístico dos traces de treinamento com escala, jitter, deslocamento e quedas curtas:

```bash
python run_generalization.py \
  --config generalization_config.json \
  --output-dir results/generalization
```

O experimento avalia três controladores — baseline estático, Q-Learning original e Q-Learning robusto — em dois traces independentes de validação e nos três benchmarks congelados. A configuração moderada em `robust_protocol_config.json` foi escolhida na validação por reduzir rebuffering sem sacrificar bitrate frente ao baseline. Os detalhes e intervalos estão em `results/generalization_results.md`.

### Tamanhos medidos de segmentos

Quando `--segment-manifest` é informado, o simulador deixa de estimar o tamanho como `bitrate × duração` e usa `size_bytes` e `duration_s` registrados para cada par segmento–representação:

```bash
python run_experiment.py \
  --controller static \
  --trace bandwidth_traces/stable.csv \
  --segment-manifest segment_manifests/example_segments.csv \
  --segments 4 \
  --output results/runs/manifest_example.csv
```

Sem esse argumento, o comportamento nominal anterior permanece inalterado. O exemplo versionado é sintético e serve somente para validar o formato e o fluxo. O contrato completo está em `segment_manifests/README.md`.

### Geração de segmentos VVC reais

O pipeline da Etapa 5.2 codifica cada segmento de cada representação como um bitstream independente, mede o tamanho em bytes, calcula SHA-256 e, quando o VVdeC está habilitado, decodifica o segmento e calcula PSNR-Y contra o recorte correto da fonte.

Primeiro, copie e ajuste a configuração versionada. Os caminhos relativos são resolvidos em relação ao próprio JSON:

```bash
cp vvc_pipeline_config.example.json vvc_pipeline_config.local.json
python generate_vvc_segments.py \
  --config vvc_pipeline_config.local.json \
  --dry-run
```

Após conferir os comandos, execute:

```bash
python generate_vvc_segments.py \
  --config vvc_pipeline_config.local.json
```

O resultado inclui:

- bitstreams `.266` organizados por sequência e representação;
- logs separados de codificação e decodificação;
- manifesto CSV aceito diretamente por `--segment-manifest`;
- arquivo `*.provenance.json` com hashes, versões e comandos executados.

O pipeline exige VVenC 1.13 ou superior porque usa `idr_no_radl`, modo apropriado para segmentos independentemente decodificáveis. A versão recomendada para congelar o experimento é a 1.14.0. O bitrate fornecido ao `vvencapp` é convertido de kbps para bits por segundo e o controle de taxa usa duas passagens por padrão. A configuração fixa oito threads e `mt_profile=0`; qualquer alteração fica registrada na proveniência.

O pipeline verifica o tamanho da fonte YUV antes de codificar e **não repete conteúdo automaticamente**. Os traces de avaliação possuem 30 segmentos de 2 s; portanto, o protocolo completo requer 60 s de conteúdo após `start_frame`. O exemplo BQTerrace contém cinco segmentos apenas como ensaio de integração, devendo ser ajustado à fonte efetivamente disponível. Se uma execução longa for interrompida, `--resume` reutiliza apenas bitstreams cujo comando salvo no log coincide exatamente com a configuração atual. Consulte `segment_manifests/README.md` para o procedimento completo.

### Importação de pacotes DVB-DASH VVC

A Etapa 5.2b usa os pacotes de teste publicados na página [DVB VVC Test Content](https://dvb.org/specifications/verification-validation/vvc-test-content/). O download é feito manualmente porque a DVB exige o preenchimento de um formulário. Extraia o ZIP em `datasets/dvb/`, identifique o MPD e copie literalmente da página a atribuição e a licença específicas daquele pacote.

Exemplo para um pacote já extraído:

```bash
python import_dvb_dash.py \
  --mpd datasets/dvb/vvc_uhd1_hfr/path/to/stream.mpd \
  --archive datasets/dvb/vvc_uhd1_hfr.zip \
  --output segment_manifests/dvb_uhd1_hfr.csv \
  --package-name "DVB-DASH VVC UHD1 HFR" \
  --attribution "ATRIBUIÇÃO EXATA INFORMADA PELA DVB" \
  --license-name "LICENÇA INFORMADA PARA O PACOTE" \
  --license-url "URL DA LICENÇA" \
  --protocol-template protocol_config.json \
  --protocol-config dvb_protocol_config.local.json \
  --bandwidth-scale 10
```

O importador:

- lê `SegmentTemplate`, `SegmentTimeline`, `SegmentList` ou `SegmentBase`/`sidx` do MPD;
- ignora o segmento de inicialização e mede cada segmento de mídia completo;
- registra bytes, duração, caminho e SHA-256 de cada segmento ou byte range;
- preserva os valores `bandwidth` declarados pelo MPD como a escada do agente;
- deixa PSNR-Y vazio, pois o pacote não contém necessariamente o master YUV exato;
- grava um `*.provenance.json` com MPD, ZIP, licença, atribuição e seleção;
- gera, opcionalmente, uma cópia do protocolo com a escada descoberta.

Se o pacote contiver mais representações do que as desejadas, repita `--representation ID`. Use `--segments N` para um ensaio curto. Uma única representação valida a importação, mas são necessárias pelo menos duas para avaliar adaptação de bitrate. O número importado de segmentos também deve ser suficiente para os traces usados no protocolo.

O pacote UHD1 HFR selecionado contém dois MP4 com índices `sidx`, 63 segmentos em 60 s e representações declaradas de 10.026 e 58.015 kbps. O manifesto versionado registra os byte ranges transferíveis dentro de cada MP4; os arquivos de vídeo e o ZIP não são incluídos no Git. Como os traces originais têm máximo de 5.200 kbps, `dvb_uhd1_hfr_protocol_config.json` aplica `bandwidth_scale: 10` a cada trace. A escala preserva o formato temporal dos traces e evita um cenário degenerado em que nem a representação inferior seria sustentável.

Depois da importação, execute o protocolo gerado:

```bash
python run_protocol.py \
  --config dvb_protocol_config.local.json \
  --output-dir results/protocol_dvb
```

A execução congelada do pacote UHD1 HFR está em `results/dvb_uhd1_hfr/`. O resultado inicial mostra um compromisso: o Q-Learning escolhe bitrate maior, mas também produz mais rebuffering que o baseline. Esse achado é preservado como baseline da política anterior e orienta a próxima etapa de recalibração da recompensa.

### Ajuste da recompensa DVB sem vazamento

A Etapa 5.3a compara uma grade declarada de seis candidatos usando somente `stable.csv` e `fluctuating.csv` no treinamento e `validation_bursty.csv` e `validation_mixed.csv` na seleção. As cinco sementes, 4000 episódios, ambiente, manifesto e demais hiperparâmetros permanecem constantes:

```bash
python run_reward_tuning.py \
  --config dvb_reward_tuning_config.json \
  --output-dir results/dvb_reward_tuning \
  --selected-protocol dvb_uhd1_hfr_selected_protocol_config.json
```

A regra exige que o limite superior do IC95% da diferença pareada `Q-Learning - Estático` na taxa de rebuffering seja menor ou igual a zero. Entre candidatos elegíveis, maximiza-se o bitrate útil médio; se nenhum for elegível, minimiza-se o limite superior de rebuffering. A seleção escolheu `wr10_wb2`, que mantém `rebuffering_weight=10` e aumenta `low_buffer_weight` de 1 para 2.

Na validação, a política escolhida igualou o baseline em todas as métricas, enquanto os candidatos com `low_buffer_weight=1` aumentaram o bitrate, mas falharam no critério de rebuffering. Esse resultado conservador é preservado em `results/dvb_reward_tuning/`; não se afirma ganho de QoE. O script apenas registra os nomes dos traces finais e não os carrega. A configuração selecionada permanece congelada em `dvb_uhd1_hfr_selected_protocol_config.json` para uma única avaliação na Etapa 5.3b.

### Avaliação final da recompensa selecionada

A Etapa 5.3b executa o protocolo congelado sem alterar a recompensa após a seleção:

```bash
python run_protocol.py \
  --config dvb_uhd1_hfr_selected_protocol_config.json \
  --output-dir results/dvb_uhd1_hfr_selected_final
```

Na média dos três traces finais, o Q-Learning e o baseline apresentaram os mesmos 2,816 s de rebuffering e taxa de 9,885%. O Q-Learning aumentou o bitrate útil de 13.272 para 14.741 kbps, diferença pareada de +1.468 kbps com IC95% [1.068; 1.868], e reduziu o desvio-padrão do buffer de 1,740 para 1,534 s, diferença de −0,207 s com IC95% [−0,248; −0,166]. O ganho ocorreu no trace gradual; nos traces `bursty` e `challenging`, as políticas produziram métricas idênticas.

Esses resultados sustentam superioridade nas duas métricas secundárias citadas, mas não redução de rebuffering: nessa métrica crítica, a política apenas iguala o baseline. Os arquivos completos e a atestação da execução única estão em `results/dvb_uhd1_hfr_selected_final/`.

### Comparação com baselines ABR competitivos

A Etapa 5.4a reutiliza sem alteração a configuração final da Etapa 5.3b e acrescenta três comparadores: um controlador por throughput com média harmônica, BOLA-BASIC e RobustMPC. Os parâmetros foram versionados antes da primeira execução e não foram ajustados nos traces finais:

```bash
python run_abr_comparison.py \
  --config dvb_abr_comparison_config.json \
  --output-dir results/dvb_abr_comparison
```

O protocolo produz 75 avaliações pareadas. Q-Learning mantém o ganho sobre o baseline estático, mas fica estatisticamente empatado com BOLA-BASIC nas métricas principais. RobustMPC transfere mais bitrate e maximiza melhor a recompensa congelada, porém aumenta o atraso inicial médio de 2,453 para 10,995 s. Esse resultado expõe que a recompensa atual não inclui startup; por isso, os arquivos usam o nome `mean_objective_reward`, não QoE total.

Essa comparação é uma extensão *post hoc*, não uma confirmação pré-registrada. Ela não sustenta superioridade geral do Q-Learning e orienta a próxima etapa: incluir startup no desenho da recompensa e ampliar conteúdos e traces. Resultados, IC95%, hashes e limitações estão em `results/dvb_abr_comparison/`.

### Recompensa com startup e novo holdout

A Etapa 5.4b adiciona `startup_weight` à recompensa e gera seis traces independentes de 60 segmentos, sem reamostrar os conjuntos anteriores. Três traces são usados exclusivamente para validação e três formam um novo holdout congelado:

```bash
python generate_holdout_traces.py \
  --config stage54b_trace_synthesis_config.json \
  --provenance bandwidth_traces/stage54b_trace_provenance.json
```

As primeiras rodadas mostraram que elevar o peso até 5 não eliminava o startup adicional, porque o Q-Learning podia aumentar a representação antes de iniciar a reprodução. Foi então acrescentada uma guarda configurável que mantém a menor representação somente durante o preenchimento inicial.

Com a guarda, `startup_weight=0,5` foi selecionado em validação: startup idêntico ao estático, redução de 0,495 ponto percentual na taxa de rebuffering e diferença inconclusiva de −151 kbps no bitrate útil, IC95% [−1.227; 924]. As rodadas intermediárias foram preservadas para auditoria.

Durante a seleção, o holdout `stage54b_evaluation_*` **não foi executado**. A entrada congelada `dvb_uhd1_hfr_startup_guard_selected_protocol_config.json` foi posteriormente avaliada uma única vez na Etapa 5.4c.

```bash
python run_abr_comparison.py \
  --config dvb_startup_holdout_comparison_config.json \
  --output-dir results/dvb_startup_holdout_final
```

No holdout, o Q-Learning reduziu rebuffering frente ao estático e aumentou o bitrate útil frente ao BOLA-BASIC, mantendo startup equivalente a ambos. Throughput e RobustMPC obtiveram menos rebuffering e maior recompensa objetiva, enquanto o Q-Learning entregou mais bitrate útil e buffer menos variável. A conclusão é de competitividade parcial, não de superioridade geral. Resultados, IC95%, hashes e atestação estão em `results/dvb_startup_holdout_final/`.

## Objetivos

O objetivo geral deste projeto é desenvolver e avaliar metodologicamente uma arquitetura de controle adaptativo para streaming VVC, empregando o algoritmo Q-Learning para a gestão dinâmica da ocupação do buffer. Os objetivos específicos incluem:

*   Modelar o agente de Aprendizado por Reforço.
*   Projetar a integração dos módulos técnicos.
*   Descrever a lógica de implementação do agente de decisão.
*   Definir cenários de avaliação experimental.
*   Estabelecer critérios para uma análise comparativa inicial.

## Metodologia

A metodologia fundamenta-se na construção progressiva de uma arquitetura experimental planejada com sete módulos integrados:

1.  **Fonte de Vídeo:** YUV controlado ou pacote DVB-DASH VVC medido.
2.  **Codificador VVC (VVenC):** Utilizado na vertente controlada do experimento.
3.  **Controlador Adaptativo de Taxa:** Baseado em Q-Learning, ajusta o bitrate da transmissão em tempo real.
4.  **Simulador de Rede:** Emprega o utilitário `tc/netem` do Linux para simular flutuações de rede.
5.  **Monitor de Buffer:** Monitora a ocupação do buffer no cliente.
6.  **Mecanismo de Feedback:** Fornece feedback contínuo ao agente de Q-Learning.
7.  **Reprodutor de Vídeo:** Com suporte ao padrão VVC.

O agente opera em um modelo tabular e toma uma decisão por segmento. O estado contém ocupação do buffer, representação atual e throughput observado no segmento anterior. A largura de banda do segmento que será baixado não é apresentada ao agente antes da decisão.

## Detalhes Técnicos Adicionais

### Métricas de Avaliação de QoE

Para avaliar a eficácia da proposta, serão utilizadas as seguintes métricas:

*   **PSNR (Peak Signal-to-Noise Ratio):** Mede a fidelidade visual do vídeo reconstruído em relação ao original, calculando o PSNR médio do componente de luminância (Y) quadro a quadro entre os arquivos YUV original e codificado.
*   **Taxa de Rebuffering:** Porcentagem de tempo em que a reprodução foi interrompida devido ao esvaziamento do buffer.
*   **Estabilidade do Buffer:** Medida pelo desvio padrão da ocupação do buffer ao longo do tempo.

O script `qoe_metrics.py` fornece implementações para o cálculo dessas métricas, incluindo uma função robusta para PSNR.

### Cenários Experimentais

A arquitetura foi projetada para ser avaliada em diversos cenários de rede, simulados via `tc/netem`:

1.  **Rede Estável:** Largura de banda constante e baixa latência.
2.  **Rede com Flutuação de Banda:** Variações bruscas na largura de banda disponível.
3.  **Rede com Perda de Pacotes:** Simulação de congestionamento e interferências.
4.  **Rede com Jitter Elevado:** Variações significativas na latência.

### Modelagem do Agente Q-Learning

*   **Espaço de Estados:** Ocupação do buffer discretizada, bitrate atual e classe do throughput anterior. O primeiro segmento utiliza um estado exclusivo de throughput desconhecido.
*   **Espaço de Ações:** {Diminuir Bitrate, Manter Bitrate, Aumentar Bitrate}.
*   **Política de Treinamento:** Epsilon-greedy com desempate aleatório e decaimento de epsilon por episódio.
*   **Avaliação:** Política gulosa, sem exploração, utilizando trace separado dos traces de treinamento.

A recompensa por segmento é:

```text
r = wq * qualidade
    - wr * rebuffering_normalizado
    - ws * troca_de_qualidade
    - wb * déficit_do_buffer
```

Os valores padrão são `wq=1`, `wr=10`, `ws=0.25`, `wb=1` e buffer-alvo de 8 segundos. Todos são registrados no modelo e podem ser alterados pela interface de treinamento.

## Estrutura do Repositório

*   `q_learning_agent.py`: Implementação do agente Q-Learning em Python.
*   `q_learning_pipeline.py`: Estado, recompensa, treinamento e avaliação do agente.
*   `train_q_learning.py`: Interface de treinamento e persistência da Q-table.
*   `compare_controllers.py`: Comparação automatizada com o baseline.
*   `experimental_protocol.py`: Execuções repetidas, IC95% e diferenças pareadas.
*   `run_protocol.py`: Interface do protocolo experimental completo.
*   `protocol_config.json`: Traces, sementes e hiperparâmetros versionados.
*   `trace_augmentation.py`: Geração reprodutível de variantes de treinamento.
*   `generalization_experiment.py`: Comparação pareada entre treino original e robusto.
*   `run_generalization.py`: Interface do experimento de generalização.
*   `robust_protocol_config.json`: Configuração robusta selecionada na validação.
*   `generalization_config.json`: Separação entre treino, validação e avaliação.
*   `segment_manifest.py`: Leitura, validação e consulta dos segmentos medidos.
*   `segment_manifests/`: Contrato CSV e manifesto ilustrativo.
*   `vvc_segment_pipeline.py`: Codificação, decodificação, medição e proveniência VVC.
*   `generate_vvc_segments.py`: Interface de linha de comando da Etapa 5.2.
*   `vvc_pipeline_config.example.json`: Configuração reproduzível de exemplo.
*   `dvb_dash_importer.py`: Leitura do MPD, medição de segmentos/byte ranges e proveniência DVB.
*   `import_dvb_dash.py`: Interface de linha de comando da Etapa 5.2b.
*   `dvb_uhd1_hfr_protocol_config.json`: Protocolo de duas representações com traces escalados.
*   `reward_tuning.py`: Ajuste multi-semente da recompensa somente em validação.
*   `run_reward_tuning.py`: Interface da seleção de pesos da Etapa 5.3a.
*   `dvb_reward_tuning_config.json`: Grade e regra de não inferioridade congeladas.
*   `dvb_uhd1_hfr_selected_protocol_config.json`: Entrada congelada usada na avaliação final da Etapa 5.3b.
*   `results/dvb_uhd1_hfr_selected_final/`: Avaliação final congelada e sua atestação de integridade.
*   `streaming_env.py`: Ambiente de streaming segmentado e dinâmica do buffer.
*   `controllers.py`: Controladores usados como baseline experimental.
*   `experiment.py`: Orquestração, métricas agregadas e persistência dos resultados.
*   `run_experiment.py`: Interface de linha de comando dos experimentos.
*   `bandwidth_traces/`: Traces de largura de banda versionados.
*   `tests/`: Testes automatizados da implementação.
*   `qoe_metrics.py`: Script para cálculo de métricas de QoE.
*   `tc_netem_config.sh`: Script para configurar o simulador de rede `tc/netem`.
*   `vvenc_config.sh`: Script para exemplificar o uso do codificador `VVenC`.
*   `results/`: Pasta contendo os resultados preliminares e dados experimentais.
*   `DOCS.md`: Documentação técnica detalhada sobre o dataset e versões das ferramentas.
*   `LICENSE`: Licença de uso do projeto (MIT).
*   `README.md`: Este arquivo, descrevendo o projeto.

## Separação entre treinamento e avaliação

Os traces `stable.csv` e `fluctuating.csv` são as únicas fontes de treinamento. Suas variantes são geradas em memória e não copiam trechos dos demais conjuntos. `validation_bursty.csv` e `validation_mixed.csv` servem para escolher a intensidade da randomização. `evaluation_gradual.csv`, `evaluation_bursty.csv` e `evaluation_challenging.csv` permanecem reservados para a comparação final.

O protocolo atual utiliza múltiplos traces, sementes, intervalos de confiança e separação em três conjuntos. A vertente DVB já contém um manifesto e resultados reais de entrega, incluindo a avaliação única da configuração recalibrada; a vertente VVenC controlada ainda depende das fontes YUV declaradas. As conclusões permanecem restritas ao pacote DVB, à transformação de banda usada e aos traces versionados.

## Componentes Adicionais e Configuração (Opcional)

### 1. Simulador de Rede: `tc/netem`

O `tc/netem` é uma ferramenta do Linux para emular as propriedades da rede.

**Instalação:**
```bash
sudo apt update
sudo apt install iproute2
```

**Uso do Script `tc_netem_config.sh`:**
```bash
./tc_netem_config.sh <interface> [delay_ms] [loss_percent] [rate_kbit]
```

### 2. Codificador VVC: `VVenC`

O `VVenC` é um codificador VVC aberto e otimizado. O software de referência normativa do padrão é o VTM; neste projeto, o VVenC é adotado por oferecer controle de taxa e tempo de execução mais apropriados ao pipeline experimental.

**Instalação:**
```bash
git clone https://github.com/fraunhoferhhi/vvenc.git
cd vvenc
git checkout vvenc-v1.14.0
cmake -S . -B build/release-static \
  -DCMAKE_BUILD_TYPE=Release \
  -DVVENC_FFP_CONTRACT_OFF=On
cmake --build build/release-static -j
```

Também é necessário compilar o [VVdeC](https://github.com/fraunhoferhhi/vvdec) e deixar `vvencapp` e `vvdecapp` no `PATH`, ou informar seus caminhos absolutos no JSON. O `vvenc_config.sh` permanece como atalho para uma única codificação; a matriz experimental deve ser gerada por `generate_vvc_segments.py`.

**Uso isolado do Script `vvenc_config.sh`:**
```bash
./vvenc_config.sh <input.yuv> <output.266> [bitrate_kbps] [resolução] [fps] [preset] [quadros]
```

## Referência

Este projeto é baseado no Trabalho de Conclusão de Curso:

João Matheus Dalmolin Montanha. **Correção Dinâmica da Ocupação de Buffer em Streaming com Codificação VVC via Aprendizado por Reforço**. Universidade Federal do Pampa, Alegrete, 2026.
