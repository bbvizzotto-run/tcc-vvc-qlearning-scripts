# Resultados Preliminares

Os resultados abaixo representam a avaliação preliminar do controlador adaptativo baseado em Q-Learning em comparação com um método de controle por limiares estáticos, conforme descrito na Tabela 1 do TCC.

## Tabela 1: Resultados Prévios

| Cenário de Rede | Método de Controle | PSNR Médio (dB) | Taxa de Rebuffering (%) | Estabilidade do Buffer (Desvio Padrão) |
| :--- | :--- | :--- | :--- | :--- |
| Estável | Estático | 38.5 | 0.5 | 2.1 |
| Estável | Q-Learning | 39.2 | 0.1 | 1.2 |
| Flutuação de Banda | Estático | 34.2 | 8.4 | 15.3 |
| Flutuação de Banda | Q-Learning | 36.8 | 2.1 | 5.4 |
| Perda de Pacotes (1%) | Estático | 31.5 | 12.5 | 18.7 |
| Perda de Pacotes (1%) | Q-Learning | 34.1 | 4.2 | 8.9 |
| Jitter Elevado | Estático | 33.8 | 10.2 | 16.5 |
| Jitter Elevado | Q-Learning | 35.9 | 3.5 | 7.2 |

## Análise dos Resultados

Com base nos dados preliminares:
- **PSNR:** O agente Q-Learning conseguiu manter uma qualidade visual (PSNR) consistentemente superior em todos os cenários adversos, demonstrando sua capacidade de otimizar a escolha do bitrate mesmo sob instabilidade.
- **Rebuffering:** A redução na taxa de rebuffering foi significativa, especialmente nos cenários de flutuação de banda e perda de pacotes, indicando que o agente aprendeu a manter uma reserva de segurança no buffer para evitar interrupções.
- **Estabilidade do Buffer:** O desvio padrão da ocupação do buffer foi notavelmente menor com o Q-Learning, o que comprova que o controle dinâmico evita oscilações bruscas (overflow e underflow), resultando em um fluxo de dados mais suave.
