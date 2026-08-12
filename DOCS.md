# Documentação Técnica e Dataset

Este documento detalha as especificações do ambiente experimental, incluindo o dataset de vídeos e as versões das ferramentas utilizadas para garantir a reprodutibilidade dos resultados.

## Dataset de Vídeos

Para a futura avaliação com conteúdo VVC real, foram selecionadas sequências de teste padronizadas do CTC (*Common Test Conditions*) do VVC. Os experimentos reproduzíveis com essas sequências ainda serão incorporados ao repositório.

### Sequências Planejadas:
| Sequência | Resolução | Taxa de Quadros (fps) | Classe | Descrição |
| :--- | :--- | :--- | :--- | :--- |
| **Tango** | 3840x2160 | 60 | A1 | Conteúdo de alta dinâmica e detalhes finos. |
| **Campfire** | 3840x2160 | 30 | A2 | Texturas complexas e movimento orgânico. |
| **BQTerrace** | 1920x1080 | 60 | B | Cenário urbano com detalhes estáticos e dinâmicos. |
| **BasketballDrive** | 1920x1080 | 50 | B | Movimento rápido e acompanhamento de câmera. |

**Nota:** As sequências originais estão em formato YUV 4:2:0 planar. Elas podem ser obtidas através dos repositórios oficiais do MPEG ou sites de datasets de vídeo acadêmicos como o [Xiph.org](https://media.xiph.org/video/derf/).

## Versões das Ferramentas

A arquitetura experimental prevê as seguintes versões de software, que deverão ser registradas novamente quando os experimentos reais forem executados:

- **Codificador VVC (VVenC):** Versão v1.7.0 (Fraunhofer HHI).
- **Simulador de Rede:** `tc/netem` integrado ao Kernel Linux 5.x ou superior.
- **Python:** Versão 3.10+ (utilizado para o agente Q-Learning e scripts de métricas).
- **NumPy:** Versão 1.24+ (para processamento de matrizes e Q-table).

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

## Parâmetros de Codificação (VVenC)

Para os experimentos, o VVenC foi configurado com os seguintes parâmetros base:
- **Preset:** `medium` (equilíbrio entre eficiência e tempo de codificação).
- **GOP Size:** 32 ou 64 (conforme a duração do segmento).
- **Bitrate:** Variável conforme as ações do agente Q-Learning.
- **Format:** YUV 4:2:0 8-bit ou 10-bit.
