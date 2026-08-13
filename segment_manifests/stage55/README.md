# Etapa 5.5 — conteúdo VVC controlado

Este diretório registra o primeiro conteúdo da avaliação multi-conteúdo. Os
bitstreams `.266` e a fonte YUV permanecem fora do Git; tamanhos, PSNR-Y,
hashes, comandos e versões das ferramentas são versionados para auditoria.

## Big Buck Bunny

- fonte: `big_buck_bunny_1080p24.y4m.xz`, publicada pelo Xiph;
- URL: <https://media.xiph.org/video/derf/y4m/big_buck_bunny_1080p24.y4m.xz>;
- obra: *Big Buck Bunny*, copyright 2008 Blender Foundation;
- licença da obra publicada: Creative Commons Attribution 3.0;
- página da licença: <https://creativecommons.org/licenses/by/3.0/>;
- transformação: trecho contínuo de 60 s iniciado no quadro 2880 (120 s),
  totalizando 1440 quadros a 1920×1080, 24 fps, YUV 4:2:0, 8 bits;
- SHA-256 da fonte Y4M descompactada:
  `31c2c73ef1d198db6e7b7890b6b1c7b02b16056913eb4348c255129b0685a6b7`;
- SHA-256 do trecho YUV normalizado:
  `4c6fd0d193ca6316b0e4f56bc73c01b8dd2de4ad9b1fe4d24c4d0406ff5aff2e`.

A codificação usa VVenC 1.14.0, VVdeC 3.2.0, preset `medium`, duas passagens,
QPA, `idr_no_radl`, `POC0IDR=1`, oito threads e 60 segmentos independentes de
1 s. Os alvos do encoder são `[1000, 2000, 4000, 8000]` kbps.

`raw/big_buck_bunny_full.csv` é a saída imutável do pipeline e usa esses alvos
como rótulos. `big_buck_bunny_measured.csv` é derivado automaticamente: mantém
os alvos em `encoder_target_kbps`, identifica os níveis como `L0`–`L3` e usa a
taxa média efetiva arredondada como `bitrate_kbps` operacional:

| Nível | Alvo VVenC (kbps) | Taxa média medida (kbps) | Rótulo operacional (kbps) | PSNR-Y médio (dB) |
| :--- | ---: | ---: | ---: | ---: |
| L0 | 1000 | 1019,437733 | 1019 | 42,874798 |
| L1 | 2000 | 1691,558800 | 1692 | 45,345438 |
| L2 | 4000 | 2609,748267 | 2610 | 47,128067 |
| L3 | 8000 | 3631,538533 | 3632 | 48,384195 |

Os caminhos em `source_file` registram o layout local original da codificação;
os bitstreams não integram o repositório. Integridade e reprodução são
ancoradas pelos SHA-256 individuais e pela proveniência bruta.

A taxa operacional é usada por estado, recompensa e penalidade de troca dos
controladores. O tempo de download continua sendo calculado com o `size_bytes`
individual de cada segmento. O PSNR-Y medido fica disponível para análise de
qualidade, sem modificar nesta etapa a recompensa congelada da Etapa 5.4.

## Reproduzir a canonicalização

```bash
python canonicalize_vvc_manifest.py \
  --input segment_manifests/stage55/raw/big_buck_bunny_full.csv \
  --source-provenance segment_manifests/stage55/raw/big_buck_bunny_full.provenance.json \
  --output segment_manifests/stage55/big_buck_bunny_measured.csv \
  --provenance segment_manifests/stage55/big_buck_bunny_measured.provenance.json \
  --overwrite
```

O algoritmo calcula `sum(size_bytes) × 8 / sum(duration_s) / 1000` para cada
representação e arredonda para o inteiro mais próximo com `ROUND_HALF_UP`. A
execução também exige matriz completa, PSNR-Y e SHA-256 preenchidos,
monotonicidade estrita de tamanho/PSNR por segmento e cobertura de todos os
240 comandos na proveniência.

## Observação de auditoria

A proveniência bruta registra `git_commit=d35d8ab...` e `git_dirty=true`, pois o
JSON de configuração local não era versionado. O hash registrado do módulo,
`2cee8323...`, coincide com `vvc_segment_pipeline.py` desse commit usando finais
de linha CRLF do Windows. Essa observação é mantida; os resultados não são
apresentados como provenientes de um checkout limpo.
