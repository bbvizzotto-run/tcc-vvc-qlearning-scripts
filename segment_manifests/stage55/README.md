# Etapa 5.5 — conteúdo VVC controlado

Este diretório registra os três primeiros conteúdos da avaliação
multi-conteúdo e prepara o quarto. Os bitstreams `.266` e as fontes de vídeo
permanecem fora do
Git; tamanhos, PSNR-Y, hashes, comandos e versões das ferramentas são
versionados para auditoria.

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
monotonicidade estrita de tamanho e crescimento estrito de PSNR-Y por segmento,
exceto por empates no teto lossless de 100 dB usado pelo projeto. Empates abaixo
desse teto e qualquer queda continuam inválidos. A proveniência registra a
política, o número de empates lossless e a cobertura dos 240 comandos.

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
runtime, commit Git e hashes em uma proveniência própria. O trecho normalizado
produzido possui SHA-256
`8bc7a47e03d2fd1d2bd7f271a80563771579e7ce06f42cd2188a3a7a25790a80`.

A codificação usa o mesmo protocolo do Big Buck Bunny: VVenC 1.14.0, VVdeC
3.2.0, preset `medium`, duas passagens, QPA, `idr_no_radl`, `POC0IDR=1`, oito
threads, quatro alvos e 60 segmentos independentes de 1 s. A proveniência bruta
registra o merge `6f4829c...` e `git_dirty=false`.

`raw/elephants_dream_1080p24_60s.provenance.json` ancora a transformação do XZ
oficial no YUV normalizado. `raw/elephants_dream_full.csv` e sua proveniência
preservam a evidência original da codificação. `elephants_dream_measured.csv`
separa os alvos dos rótulos operacionais e liga criptograficamente as duas
etapas:

| Nível | Alvo VVenC (kbps) | Taxa média medida (kbps) | Rótulo operacional (kbps) | PSNR-Y médio (dB) |
| :--- | ---: | ---: | ---: | ---: |
| L0 | 1000 | 1063,544800 | 1064 | 42,562710 |
| L1 | 2000 | 1847,026533 | 1847 | 44,472146 |
| L2 | 4000 | 3096,570933 | 3097 | 46,183876 |
| L3 | 8000 | 5182,347067 | 5182 | 47,948724 |

Nos segmentos 30 e 31, todas as representações atingiram `100 dB`, convenção
do projeto para MSE zero. Isso gera seis empates adjacentes legítimos no PSNR,
sem empate de tamanho. A canonicalização v2 aceita igualdade somente nesse teto
lossless e registra `lossless_psnr_ties=6`; os dois segmentos permanecem no
conjunto para preservar o recorte contínuo previamente congelado.

Para reproduzir a derivação:

```bash
python canonicalize_vvc_manifest.py \
  --input segment_manifests/stage55/raw/elephants_dream_full.csv \
  --source-provenance segment_manifests/stage55/raw/elephants_dream_full.provenance.json \
  --source-preparation-provenance segment_manifests/stage55/raw/elephants_dream_1080p24_60s.provenance.json \
  --output segment_manifests/stage55/elephants_dream_measured.csv \
  --provenance segment_manifests/stage55/elephants_dream_measured.provenance.json \
  --overwrite
```

## Terceiro conteúdo: Sita Sings the Blues

A Etapa 5.5e congela a preparação do terceiro conteúdo sem antecipar resultados
de codificação:

- fonte: `sita_sings_the_blues_1080p24.y4m.xz`, publicada pelo Xiph;
- URL: <https://media.xiph.org/video/derf/y4m/sita_sings_the_blues_1080p24.y4m.xz>;
- licença da obra visual: CC0 1.0 Universal;
- página específica da licença: <https://www.sitasingstheblues.com/license.html>;
- ressalva: a página da obra documenta restrições separadas para algumas
  músicas; este pipeline descarta o áudio e processa somente os quadros;
- SHA-256 verificado do XZ:
  `e4e8945f967ad2451d6fb663e4ef93008fea75460e6c5c1033e255a526710902`;
- cadência declarada no Y4M: `24000/1001` fps (aproximadamente 23,976);
- recorte: quadros 2880–4319, correspondentes a 120,120–180,180 s na fonte;
- normalização temporal: os mesmos 1440 quadros são reinterpretados a 24 fps,
  sem duplicação ou descarte, produzindo exatamente 60 s (aceleração de fator
  1,001);
- saída esperada: 1440 quadros, 1920×1080, 24 fps, YUV 4:2:0 de 8 bits;
- tamanho esperado do trecho normalizado: `4478976000` bytes.

No Windows, a preparação é executada sem materializar o Y4M completo:

```powershell
python prepare_y4m_source.py `
  --config y4m_source_config.sita_sings_the_blues.json `
  --input "D:\vvc-stage55\sources\originals\sita_sings_the_blues_1080p24.y4m.xz" `
  --output "D:\vvc-stage55\sources\normalized\sita_sings_the_blues_1080p24_60s.yuv" `
  --provenance "D:\vvc-stage55\sources\normalized\sita_sings_the_blues_1080p24_60s.provenance.json"
```

O trecho YUV normalizado produzido possui SHA-256
`c37f429197f14e63524edc7c2625b9df3be5611e89c7b0e5a9e52dc901d68a91`.

A codificação usa o mesmo protocolo dos conteúdos anteriores: VVenC 1.14.0,
VVdeC 3.2.0, preset `medium`, duas passagens, QPA, `idr_no_radl`, `POC0IDR=1`,
oito threads, quatro alvos e 60 segmentos independentes de 1 s. A proveniência
bruta registra o merge `8f9a439...` e `git_dirty=false`.

`raw/sita_sings_the_blues_1080p24_60s.provenance.json` ancora a transformação
do XZ no YUV normalizado. `raw/sita_sings_the_blues_full.csv` e sua proveniência
preservam a evidência original da codificação. O manifesto canônico separa os
alvos dos rótulos operacionais:

| Nível | Alvo VVenC (kbps) | Taxa média medida (kbps) | Rótulo operacional (kbps) | PSNR-Y médio (dB) |
| :--- | ---: | ---: | ---: | ---: |
| L0 | 1000 | 973,430000 | 973 | 41,188243 |
| L1 | 2000 | 1800,619600 | 1801 | 43,208977 |
| L2 | 4000 | 3218,908400 | 3219 | 45,212999 |
| L3 | 8000 | 5583,115467 | 5583 | 47,367555 |

No segmento 4, todas as representações atingiram `100 dB`, convenção do
projeto para MSE zero. Os payloads continuam estritamente crescentes, de 1536 a
1590 bytes, e geram três empates adjacentes legítimos no PSNR. Isso explica as
taxas mínimas de 12,288–12,720 kbps sem indicar artefato ausente ou falha de
codificação. A canonicalização registra `lossless_psnr_ties=3` e mantém o
segmento para preservar o recorte contínuo congelado.

Para reproduzir a derivação:

```bash
python canonicalize_vvc_manifest.py \
  --input segment_manifests/stage55/raw/sita_sings_the_blues_full.csv \
  --source-provenance segment_manifests/stage55/raw/sita_sings_the_blues_full.provenance.json \
  --source-preparation-provenance segment_manifests/stage55/raw/sita_sings_the_blues_1080p24_60s.provenance.json \
  --output segment_manifests/stage55/sita_sings_the_blues_measured.csv \
  --provenance segment_manifests/stage55/sita_sings_the_blues_measured.provenance.json \
  --overwrite
```

## Quarto conteúdo: Tears of Steel

A Etapa 5.5g prepara uma fonte de natureza distinta das três anteriores:
*Tears of Steel* combina filmagem live-action e efeitos CGI. O Xiph publica
17.620 quadros lossless a 1920×800 e permite acesso HTTP a cada PNG:

- diretório: <https://media.xiph.org/tearsofsteel/tearsofsteel-1080bis-png/>;
- atribuição: `(CC) Blender Foundation | mango.blender.org`;
- licença: Creative Commons Attribution 3.0;
- recorte: arquivos `02881.png`–`04320.png`, correspondentes a 120–180 s;
- saída: 1440 quadros, 1920×1080, 24 fps, YUV 4:2:0 de 8 bits;
- transformação espacial: padding preto simétrico de 140 linhas, sem escala,
  corte ou conversão de frequência.

Não é necessário baixar o Y4M 4K de 66 GB nem a sequência PNG completa. O
preparador obtém somente os 1440 quadros selecionados, retoma arquivos válidos
do cache, verifica o IHDR e registra tamanho e SHA-256 de cada PNG. No Windows:

```powershell
python prepare_png_source.py `
  --config png_source_config.tears_of_steel.json `
  --cache-dir "D:\vvc-stage55\sources\originals\tears_of_steel_1080bis_png" `
  --output "D:\vvc-stage55\sources\normalized\tears_of_steel_1080p24_60s.yuv" `
  --provenance "D:\vvc-stage55\sources\normalized\tears_of_steel_1080p24_60s.provenance.json"
```

Como o Xiph não publica checksums por quadro para esse diretório, a primeira
aquisição local calculou e a Etapa 5.5g-b congelou:

- tamanho agregado dos PNGs: `2722906009` bytes;
- SHA-256 da sequência ordenada:
  `1fc3a3c62782b450294563125f7d5e400d4379c4dce9a00fc237ed37fda7f48a`;
- SHA-256 do YUV normalizado:
  `f6033935e2b1a8ef06d8f4d25a78b86147dcc6dfd3638c730a7ab18f59992844`;
- SHA-256 da proveniência da primeira aquisição, ainda não fixada:
  `3f17d1a09f4dbeffc5b2ae9bf2ef497dfce10a7873cac6b67c662ab751874b85`.

O protocolo versionado agora rejeita qualquer cache cujo digest agregado
divirja. Execute novamente o mesmo comando com `--overwrite`: os 1440 PNGs
válidos serão reutilizados, o YUV será reconstruído e a nova proveniência deve
registrar `integrity_pinned=true`.

O encoder mantém a matriz dos três conteúdos anteriores. Como a entrada
codificada precisa conservar 1920×1080, `decoder.quality_region` fixa
`(x=0, y=140, width=1920, height=800)`: o PSNR-Y ignora somente as barras
adicionadas pelo protocolo e permanece comparável na área visual efetiva.
