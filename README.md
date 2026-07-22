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

O agente de IA opera em um modelo tabular, tomando decisões de ajuste de bitrate para maximizar uma função de recompensa que penaliza severamente eventos de *rebuffering* e situações de *overflow*.

## Algoritmo Q-Learning (Pseudocódigo Adaptado)

O script `q_learning_agent.py` implementa a lógica central do agente Q-Learning. Abaixo está um pseudocódigo adaptado para ilustrar o processo:

```python
# Inicialização
Inicializar Q(s, a) arbitrariamente para todos os estados s e ações a
Definir taxa de aprendizado (alpha), fator de desconto (gamma), epsilon (para exploração)

# Para cada episódio:
  Observar estado inicial s
  Enquanto s não for um estado terminal:
    Escolher ação a a partir de s usando uma política derivada de Q (ex: epsilon-greedy)
    Executar ação a, observar recompensa r e novo estado s'
    Atualizar Q(s, a) usando a equação de Bellman:
      Q(s, a) = Q(s, a) + alpha * [r + gamma * max(Q(s', a')) - Q(s, a)]
    s = s'
```

## Estrutura do Repositório

*   `q_learning_agent.py`: Implementação do agente Q-Learning em Python.
*   `tc_netem_config.sh`: Script para configurar o simulador de rede `tc/netem`.
*   `vvenc_config.sh`: Script para exemplificar o uso do codificador `VVenC`.
*   `README.md`: Este arquivo, descrevendo o projeto.

## Como Usar (Conceitual)

O script `q_learning_agent.py` é um componente central do controlador adaptativo. Para utilizá-lo em um ambiente de streaming VVC, seria necessário:

1.  **Integrar com o ambiente de streaming:** O agente precisaria receber informações sobre a ocupação do buffer e o bitrate atual do sistema de streaming.
2.  **Definir estados e ações:** A discretização dos estados (ocupação do buffer, bitrate) e a definição das ações (aumentar, manter, diminuir bitrate) devem ser ajustadas conforme as especificações do sistema.
3.  **Treinamento:** O agente seria treinado em um ambiente simulado ou real, onde aprenderia a política ótima para gerenciar o buffer.
4.  **Avaliação:** As métricas de QoE (PSNR, taxa de *rebuffering*, estabilidade do buffer) seriam usadas para avaliar a eficácia do controle.

## Componentes Adicionais e Configuração (Opcional)

### 1. Simulador de Rede: `tc/netem`

O `tc/netem` é uma ferramenta do Linux para emular as propriedades da rede, como atraso, perda de pacotes, duplicação e corrupção. É essencial para simular condições de rede adversas em experimentos.

**Instalação:**

O `tc` (Traffic Control) geralmente vem pré-instalado em distribuições Linux modernas. O módulo `netem` faz parte do kernel Linux. Se não estiver disponível, pode ser necessário instalar o pacote `iproute2`:

```bash
sudo apt update
sudo apt install iproute2
```

**Uso do Script `tc_netem_config.sh`:**

Este script facilita a configuração de atraso, perda de pacotes e limitação de largura de banda em uma interface de rede específica.

```bash
./tc_netem_config.sh <interface> [delay_ms] [loss_percent] [rate_kbit]
```

*   `<interface>`: Nome da interface de rede (ex: `eth0`, `wlan0`).
*   `[delay_ms]`: Atraso em milissegundos (opcional, padrão: 0).
*   `[loss_percent]`: Porcentagem de perda de pacotes (opcional, padrão: 0).
*   `[rate_kbit]`: Largura de banda em kbit/s (opcional, padrão: ilimitado).

**Exemplos:**

*   Adicionar 100ms de atraso na `eth0`:
    ```bash
    sudo ./tc_netem_config.sh eth0 100
    ```
*   Adicionar 50ms de atraso e 1% de perda de pacotes na `eth0`:
    ```bash
    sudo ./tc_netem_config.sh eth0 50 1
    ```
*   Limitar a largura de banda para 10 Mbps (10000 kbit/s) na `eth0`:
    ```bash
    sudo ./tc_netem_config.sh eth0 0 0 10000
    ```
*   Remover todas as regras `tc/netem` da `eth0`:
    ```bash
    sudo ./tc_netem_config.sh eth0 --clear
    ```

### 2. Codificador VVC: `VVenC`

O `VVenC` (Versatile Video Encoder) é uma implementação de referência de código aberto do padrão de codificação de vídeo Versatile Video Coding (VVC/H.266). Ele é utilizado para codificar arquivos de vídeo no formato VVC.

**Instalação:**

Recomenda-se compilar o `VVenC` a partir do código-fonte para obter a versão mais recente e otimizada. As instruções básicas são:

```bash
git clone https://github.com/fraunhoferhhi/vvenc.git
cd vvenc
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

**Uso do Script `vvenc_config.sh`:**

Este script demonstra como usar o `VVenC` para codificar um arquivo YUV de entrada para o formato VVC, com opções para bitrate, resolução e preset de codificação.

```bash
./vvenc_config.sh <input_yuv_file> <output_vvc_file> [bitrate_kbps] [resolution] [preset]
```

*   `<input_yuv_file>`: Caminho para o arquivo de vídeo YUV de entrada.
*   `<output_vvc_file>`: Caminho para o arquivo de vídeo VVC de saída.
*   `[bitrate_kbps]`: Bitrate desejado em kbps (opcional, padrão: 2000).
*   `[resolution]`: Resolução do vídeo (ex: `1920x1080`) (opcional, padrão: `1920x1080`).
*   `[preset]`: Preset de codificação (ex: `fast`, `medium`, `slow`) (opcional, padrão: `medium`).

**Exemplos:**

*   Codificar `input.yuv` para `output.vvc` com bitrate de 2 Mbps e preset `fast`:
    ```bash
    ./vvenc_config.sh input.yuv output.vvc 2000 1920x1080 fast
    ```
*   Codificar `video.yuv` para `video.vvc` com resolução 1280x720 e preset `medium`:
    ```bash
    ./vvenc_config.sh video.yuv video.vvc 1500 1280x720 medium
    ```

**Observações:**

*   O `VVenC` possui diversas opções de parametrização avançadas. Consulte a documentação oficial para otimizações específicas.
*   A qualidade e o tamanho do arquivo de saída dependem diretamente do bitrate, resolução e preset escolhidos.

## Referência

Este projeto é baseado no Trabalho de Conclusão de Curso:

João Matheus Dalmolin Montanha. **Correção Dinâmica da Ocupação de Buffer em Streaming com Codificação VVC via Aprendizado por Reforço**. Universidade Federal do Pampa, Alegrete, 2026.
