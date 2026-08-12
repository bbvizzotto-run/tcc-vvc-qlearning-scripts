# Etapa 5.4a — comparação com baselines ABR competitivos

## Escopo e congelamento

Esta é uma extensão *post hoc* da avaliação final da Etapa 5.3b. Ela não é
apresentada como comparação pré-registrada. Antes da primeira execução, o
commit local `d757a208e730e52e232c3480d2365f4fb5df53e4` congelou código, testes e
os seguintes parâmetros. Esse snapshot foi publicado sem alteração funcional
no commit `cbf067b1efc3edbe894dd703681f5965fb371270`:

- throughput: média harmônica das últimas 5 medições e fator de segurança 0,85;
- BOLA-BASIC: buffer mínimo de 10 s e alvo de 20 s;
- RobustMPC: horizonte 5, histórico 5 e pior erro das últimas 5 previsões;
- Q-Learning: configuração `wr10_wb2` já congelada na Etapa 5.3b;
- cinco sementes e os mesmos três traces finais, manifesto DVB e recompensa.

Todas as políticas recebem o buffer atual. Throughput e RobustMPC recebem
somente medições de downloads já concluídos. RobustMPC também consulta os
tamanhos futuros publicados no manifesto, como no desenho MPC para streaming,
mas nenhuma política vê a banda do segmento atual antes da decisão.

## Resultado geral

Os valores são médias dos três traces dentro de cada semente e, depois, das
cinco sementes. Os baselines determinísticos repetem o mesmo valor entre
sementes; a variação do Q-Learning vem dos treinamentos independentes.

| Controlador | Startup (s) | Rebuffering (s) | Bitrate útil (kbps) | DP buffer (s) | Recompensa do objetivo | Trocas |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| Estático | 2,453 | 2,816 | 13.272 | 1,740 | −2,018 | 0,667 |
| Throughput | 2,453 | 2,816 | 12.307 | 2,158 | −1,935 | 0,000 |
| BOLA-BASIC | 2,453 | 2,816 | 14.388 | 1,570 | −1,985 | 2,333 |
| RobustMPC | 10,995 | 2,816 | 21.147 | 1,752 | −1,874 | 2,333 |
| Q-Learning | 2,453 | 2,816 | 14.741 | 1,534 | −1,977 | 1,733 |

As diferenças abaixo seguem `Q-Learning − baseline`. Para startup, rebuffering,
desvio-padrão e trocas, valores negativos favorecem o Q-Learning; para bitrate
útil e recompensa, valores positivos o favorecem.

| Baseline | Δ startup (s) | Δ rebuffering (s) | Δ bitrate útil (kbps) | Δ DP buffer (s) | Δ recompensa | Δ trocas |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Estático | 0,000 [0,000; 0,000] | 0,000 [0,000; 0,000] | +1.468 [1.068; 1.868] | −0,207 [−0,248; −0,166] | +0,041 [0,032; 0,050] | +1,067 [0,387; 1,747] |
| Throughput | 0,000 [0,000; 0,000] | 0,000 [0,000; 0,000] | +2.434 [2.034; 2.834] | −0,625 [−0,666; −0,584] | −0,042 [−0,051; −0,033] | +1,733 [1,053; 2,413] |
| BOLA-BASIC | 0,000 [0,000; 0,000] | 0,000 [0,000; 0,000] | +353 [−47; 753] | −0,036 [−0,077; 0,005] | +0,008 [−0,001; 0,018] | −0,600 [−1,280; 0,080] |
| RobustMPC | −8,542 [−8,542; −8,542] | 0,000 [0,000; 0,000] | −6.406 [−6.806; −6.006] | −0,219 [−0,260; −0,178] | −0,103 [−0,112; −0,093] | −0,600 [−1,280; 0,080] |

## Interpretação

O ganho anterior sobre o baseline estático permanece reproduzido. Contra
throughput, o Q-Learning transfere mais bitrate e estabiliza melhor o buffer,
mas obtém recompensa interna menor e realiza mais trocas. Contra BOLA-BASIC,
nenhum IC95% das métricas principais exclui zero: neste protocolo, não há
evidência de superioridade entre BOLA e Q-Learning.

RobustMPC alcança bitrate útil e recompensa interna maiores, mas eleva o atraso
inicial de 2,453 para 10,995 s. O motivo é uma limitação objetiva do experimento:
a recompensa congelada inclui qualidade, rebuffering após o início, trocas e
buffer baixo, mas não inclui o atraso de startup. A métrica foi deliberadamente
nomeada `mean_objective_reward`, e não QoE total, para não ocultar esse escopo.
Não houve recalibração depois desse achado.

O resultado também continua heterogêneo. Q-Learning, estático, throughput e
BOLA coincidem nas métricas de interrupção; as diferenças adaptativas aparecem
principalmente no trace gradual. Nos traces `bursty` e `challenging`, o
Q-Learning volta à representação inferior e reproduz os baselines conservadores.

## Conclusão adequada

Esta etapa não sustenta superioridade geral do Q-Learning. Ela mostra que o
ganho contra um baseline estático é insuficiente para estabelecer vantagem
competitiva: BOLA-BASIC empata com o agente, e RobustMPC revela um compromisso
entre qualidade e startup que a recompensa atual não modela. Para uma alegação
publicável mais forte, a próxima etapa deve congelar uma recompensa que inclua
startup e repetir a comparação em mais conteúdos e traces independentes.

Os CSV contêm as 75 execuções, agregações e diferenças pareadas. `manifest.json`
registra parâmetros, referências, hashes e o escopo da recompensa;
`execution_attestation.json` documenta as duas gerações tecnicamente idênticas
quanto às decisões, sendo a segunda apenas a correção do nome da métrica e da
descrição de seu escopo.
