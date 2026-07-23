# Correção Dinâmica da Ocupação de Buffer em Streaming com Codificação VVC via Aprendizado por Reforço

## Visão Geral do Projeto

Este repositório contém scripts e materiais relacionados ao trabalho de conclusão de curso que propõe uma arquitetura para a correção dinâmica da ocupação de buffer em aplicações de streaming que utilizam o padrão de codificação Versatile Video Coding (VVC). A solução é baseada em Aprendizado por Reforço, empregando o algoritmo Q-Learning para otimizar a estabilidade do buffer e a Qualidade de Experiência (QoE) em transmissões de vídeo sob condições de rede instáveis.

## Objetivos

O objetivo geral deste projeto é desenvolver e avaliar metodologicamente uma arquitetura de controle adaptativo para streaming VVC, empregando o algoritmo Q-Learning para a gestão dinâmica da ocupação do buffer. Os objetivos específicos incluem:

*   Modelar o agente de Aprendizado por Reforço.
*   Projetar a integração dos módulos técnicos.
*   Descrever a lógica de implementação do agente de decisão.
*   Definir cenários de avaliação experimental.
*   Estabelecer critérios para uma análise comparativa inicial.

## Metodologia

A metodologia fundamenta-se na construção de uma arquitetura experimental composta por sete módulos integrados:

1.  **Fonte de Vídeo:** Em formato YUV.
2.  **Codificador VVC (VVenC):** Utiliza a ferramenta VVenC para codificação de vídeo.
3.  **Controlador Adaptativo de Taxa:** Baseado em Q-Learning, ajusta o bitrate da transmissão em tempo real.
4.  **Simulador de Rede:** Emprega o utilitário `tc/netem` do Linux para simular flutuações de rede.
5.  **Monitor de Buffer:** Monitora a ocupação do buffer no cliente.
6.  **Mecanismo de Feedback:** Fornece feedback contínuo ao agente de Q-Learning.
7.  **Reprodutor de Vídeo:** Com suporte ao padrão VVC.

O agente de IA opera em um modelo tabular, tomando decisões de ajuste de bitrate para maximizar uma função de recompensa que penaliza severamente eventos de *rebuffering* e situações de overflow.

## Detalhes Técnicos Adicionais

### Métricas de Avaliação de QoE

Para avaliar a eficácia da proposta, são utilizadas as seguintes métricas:

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

*   **Espaço de Estados:** Composto pela ocupação atual do buffer (discretizada em N níveis) e o bitrate atual da transmissão (M níveis).
*   **Espaço de Ações:** {Diminuir Bitrate, Manter Bitrate, Aumentar Bitrate}.
*   **Função de Recompensa:** Projetada para penalizar interrupções de reprodução (rebuffering) e recompensar a manutenção do buffer em uma zona de segurança técnica.

## Estrutura do Repositório

*   `q_learning_agent.py`: Implementação do agente Q-Learning em Python.
*   `qoe_metrics.py`: Script para cálculo de métricas de QoE.
*   `tc_netem_config.sh`: Script para configurar o simulador de rede `tc/netem`.
*   `vvenc_config.sh`: Script para exemplificar o uso do codificador `VVenC`.
*   `results/`: Pasta contendo os resultados preliminares e dados experimentais.
*   `DOCS.md`: Documentação técnica detalhada sobre o dataset e versões das ferramentas.
*   `LICENSE`: Licença de uso do projeto (MIT).
*   `README.md`: Este arquivo, descrevendo o projeto.

## Integração e Uso do Agente Q-Learning

O script `q_learning_agent.py` implementa a lógica central do agente Q-Learning. Para integrá-lo e utilizá-lo em um ambiente de streaming VVC, siga as diretrizes abaixo:

1.  **Definição do Espaço de Estados e Ações:**
    *   O espaço de estados é uma combinação da ocupação do buffer e do bitrate atual. O espaço de ações inclui diminuir, manter ou aumentar o bitrate.
    *   Ajuste os parâmetros `num_buffer_levels` e `num_bitrate_levels` dentro do script `q_learning_agent.py` para definir a granularidade da discretização do estado.
    *   Os `buffer_levels` e `bitrate_levels` devem ser configurados com base nos ranges reais e nas especificações do seu sistema de streaming.

2.  **Inicialização do Agente:**
    *   Instancie a classe `QLearningAgent` com os parâmetros apropriados para o seu ambiente (taxa de aprendizado, fator de desconto, epsilon).

3.  **Loop de Treinamento/Operação em Tempo Real:**
    *   Este é o ponto de integração principal com o seu sistema de streaming adaptativo.
    *   A cada intervalo de tempo (e.g., a cada segmento de vídeo processado ou a cada segundo):
        *   **Observação do Estado:** Obtenha a `current_buffer_occupancy` do reprodutor de vídeo e o `current_bitrate` da transmissão.
        *   **Cálculo da Recompensa:** Determine a `reward` com base na QoE observada (e.g., penalidade por rebuffering, recompensa por alta qualidade, estabilidade do buffer).
        *   **Discretização:** Use `agent.discretize_state()` para converter os valores contínuos em um `state_index`.
        *   **Escolha da Ação:** Chame `agent.choose_action(current_state_index)` para obter a ação a ser tomada.
        *   **Aplicação da Ação:** Traduza a `action` escolhida (e.g., `decrease_bitrate`, `maintain_bitrate`, `increase_bitrate`) em um comando para o seu sistema de streaming, ajustando o bitrate da próxima requisição de segmento de vídeo.
        *   **Observação do Próximo Estado:** Após a aplicação da ação e o avanço do tempo, observe o `next_buffer_occupancy`, `next_bitrate` e `next_reward`.
        *   **Atualização da Q-table:** Use `agent.update_q_table()` para atualizar a tabela de valores Q do agente.

4.  **Persistência da Q-table:**
    *   Para que o agente mantenha o conhecimento adquirido, a Q-table deve ser salva periodicamente (e.g., `np.save("q_table.npy", agent.q_table)`) e carregada ao iniciar (e.g., `agent.q_table = np.load("q_table.npy")`).

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
