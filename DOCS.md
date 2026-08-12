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
- **Python:** Versão 3.8+ (utilizado para o agente Q-Learning e scripts de métricas).
- **NumPy:** Versão 1.19.0+ (para processamento de matrizes e Q-table).

## Parâmetros de Codificação (VVenC)

Para os experimentos, o VVenC foi configurado com os seguintes parâmetros base:
- **Preset:** `medium` (equilíbrio entre eficiência e tempo de codificação).
- **GOP Size:** 32 ou 64 (conforme a duração do segmento).
- **Bitrate:** Variável conforme as ações do agente Q-Learning.
- **Format:** YUV 4:2:0 8-bit ou 10-bit.
