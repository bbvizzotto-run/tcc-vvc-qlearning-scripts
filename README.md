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
*   `README.md`: Este arquivo, descrevendo o projeto.

## Como Usar (Conceitual)

O script `q_learning_agent.py` é um componente central do controlador adaptativo. Para utilizá-lo em um ambiente de streaming VVC, seria necessário:

1.  **Integrar com o ambiente de streaming:** O agente precisaria receber informações sobre a ocupação do buffer e o bitrate atual do sistema de streaming.
2.  **Definir estados e ações:** A discretização dos estados (ocupação do buffer, bitrate) e a definição das ações (aumentar, manter, diminuir bitrate) devem ser ajustadas conforme as especificações do sistema.
3.  **Treinamento:** O agente seria treinado em um ambiente simulado ou real, onde aprenderia a política ótima para gerenciar o buffer.
4.  **Avaliação:** As métricas de QoE (PSNR, taxa de *rebuffering*, estabilidade do buffer) seriam usadas para avaliar a eficácia do controle.

## Referência

Este projeto é baseado no Trabalho de Conclusão de Curso:

João Matheus Dalmolin Montanha. **Correção Dinâmica da Ocupação de Buffer em Streaming com Codificação VVC via Aprendizado por Reforço**. Universidade Federal do Pampa, Alegrete, 2026.
