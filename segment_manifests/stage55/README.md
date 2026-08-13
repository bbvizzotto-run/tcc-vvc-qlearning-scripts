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

## Segundo conteúdo: Elephants Dream

A Etapa 5.5c mantém resolução, frequência, duração e posição temporal do
primeiro conteúdo, alterando somente a obra:

- fonte: `elephants_dream_1080p24.y4m.xz`, publicada pelo Xiph;
- URL: <https://media.xiph.org/video/derf/y4m/elephants_dream_1080p24.y4m.xz>;
- licença: Creative Commons Attribution 2.5;
- página oficial da obra: <https://orange.blender.org/press/>;
- SHA-256 oficial do XZ:
  `aef14c7ff450cd44e75760b6c0bef5ed9dc62f6af4d8c68816128ea74fb782b4`;
- recorte: quadros 2880–4319, equivalentes a 120–180 s;
- saída: 1440 quadros, 1920×1080, 24 fps, YUV 4:2:0 de 8 bits;
- tamanho esperado do trecho normalizado: `4478976000` bytes.

O arquivo XZ possui cerca de 7,1 GB e o Y4M completo, cerca de 45 GB. O comando
abaixo verifica todo o XZ e o descomprime em fluxo para o FFmpeg, gravando
somente os 60 s necessários:

```powershell
python prepare_y4m_source.py `
  --config y4m_source_config.elephants_dream.json `
  --input "D:\vvc-stage55\sources\originals\elephants_dream_1080p24.y4m.xz" `
  --output "D:\vvc-stage55\sources\normalized\elephants_dream_1080p24_60s.yuv" `
  --provenance "D:\vvc-stage55\sources\normalized\elephants_dream_1080p24_60s.provenance.json"
```

O script rejeita hash, geometria, frequência, entrelaçamento, chroma ou tamanho
de saída divergentes e registra configuração efetiva, cabeçalho Y4M, FFmpeg,
runtime, commit Git e hashes em uma proveniência própria. O próximo pipeline
VVC deve partir do exemplo `vvc_pipeline_config.elephants_dream.example.json`.
