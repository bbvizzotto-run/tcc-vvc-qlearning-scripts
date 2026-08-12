# Correção Dinâmica da Ocupação de Buffer em Streaming com Codificação VVC via Aprendizado por Reforço

## Visão Geral do Projeto

Este repositório contém scripts e materiais relacionados ao trabalho de conclusão de curso que propõe uma arquitetura para a correção dinâmica da ocupação de buffer em aplicações de streaming que utilizam o padrão de codificação Versatile Video Coding (VVC). A solução é baseada em Aprendizado por Reforço, empregando o algoritmo Q-Learning para otimizar a estabilidade do buffer e a Qualidade de Experiência (QoE) em transmissões de vídeo sob condições de rede instáveis.

## Status da Implementação

O desenvolvimento está organizado em etapas verificáveis. A **Etapa 1** implementa o ambiente determinístico e o baseline por limiares. A **Etapa 2** integra o treinamento, a persistência e a avaliação do controlador Q-Learning ao mesmo ambiente.

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
| Segmentos VVC reais e rede `tc/netem` | Pendente |

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

## Objetivos

O objetivo geral deste projeto é desenvolver e avaliar metodologicamente uma arquitetura de controle adaptativo para streaming VVC, empregando o algoritmo Q-Learning para a gestão dinâmica da ocupação do buffer. Os objetivos específicos incluem:

*   Modelar o agente de Aprendizado por Reforço.
*   Projetar a integração dos módulos técnicos.
*   Descrever a lógica de implementação do agente de decisão.
*   Definir cenários de avaliação experimental.
*   Estabelecer critérios para uma análise comparativa inicial.

## Metodologia

A metodologia fundamenta-se na construção progressiva de uma arquitetura experimental planejada com sete módulos integrados:

1.  **Fonte de Vídeo:** Em formato YUV.
2.  **Codificador VVC (VVenC):** Utiliza a ferramenta VVenC para codificação de vídeo.
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

Os traces `stable.csv` e `fluctuating.csv` são usados no exemplo de treinamento. O trace `evaluation_challenging.csv` fica reservado para avaliação. Essa divisão evita avaliar a política somente nas mesmas sequências de rede usadas para atualizar a Q-table.

Os resultados produzidos nesta etapa validam a integração do software, mas ainda não constituem uma avaliação científica completa. Essa avaliação exigirá múltiplos traces, diversas sementes, intervalos de confiança e representações VVC reais.

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

O `VVenC` é o codificador de referência para o padrão VVC.

**Instalação:**
```bash
git clone https://github.com/fraunhoferhhi/vvenc.git
cd vvenc
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

**Uso do Script `vvenc_config.sh`:**
```bash
./vvenc_config.sh <input_yuv_file> <output_vvc_file> [bitrate_kbps] [resolution] [preset]
```

## Referência

Este projeto é baseado no Trabalho de Conclusão de Curso:

João Matheus Dalmolin Montanha. **Correção Dinâmica da Ocupação de Buffer em Streaming com Codificação VVC via Aprendizado por Reforço**. Universidade Federal do Pampa, Alegrete, 2026.
