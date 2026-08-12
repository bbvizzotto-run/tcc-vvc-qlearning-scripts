# Manifesto de Segmentos

O manifesto conecta representações pré-codificadas ao simulador sem exigir que os bitstreams, normalmente grandes, sejam versionados no repositório. Cada arquivo CSV descreve **uma sequência** e contém uma linha para cada par segmento–representação.

## Colunas obrigatórias

| Coluna | Tipo | Unidade | Descrição |
| :--- | :--- | :--- | :--- |
| `sequence` | texto | — | Identificador único da sequência |
| `segment` | inteiro | — | Índice consecutivo iniciado em zero |
| `bitrate_kbps` | inteiro | kbps decimais | Identificador da representação |
| `duration_s` | real | segundos | Duração reproduzível do segmento |
| `size_bytes` | inteiro | bytes | Tamanho efetivamente transferido |

`size_bytes` deve representar o payload usado no experimento. Para um arquivo `.vvc` transferido diretamente, é o tamanho desse arquivo. Se o experimento usar segmentos `.m4s`, deve incluir o tamanho do arquivo `.m4s`, inclusive seu overhead de contêiner. O mesmo critério deve ser mantido em toda a escada.

O simulador converte o tamanho para kilobits decimais:

```text
segment_size_kbits = size_bytes * 8 / 1000
download_time_s = segment_size_kbits / bandwidth_kbps
```

Além do bitrate nominal da representação, os resumos registram `average_payload_bitrate_kbps`, calculado por `soma(size_kbits) / soma(duration_s)`. Em protocolos com manifesto, essa taxa efetivamente transferida é incluída automaticamente nas agregações e nos IC95%.

## Colunas opcionais

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `psnr_y_db` | real | PSNR do componente Y; nesta etapa é registrado, mas ainda não altera a recompensa |
| `source_file` | texto | Caminho lógico ou relativo do payload |
| `sha256` | hexadecimal | SHA-256 do payload, com 64 caracteres |

As colunas opcionais podem existir com células vazias. Arquivos apontados por `source_file` não precisam estar no repositório.

## Invariantes validados

- exatamente uma sequência por manifesto;
- segmentos consecutivos a partir de zero;
- mesma escada de bitrates em todos os segmentos;
- uma única linha para cada par segmento–bitrate;
- mesma duração entre as representações de um segmento;
- duração e tamanho positivos;
- checksum SHA-256 válido quando informado;
- número de segmentos suficiente para o trace de banda executado.

O manifesto `example_segments.csv` é **somente ilustrativo**: seus tamanhos e valores de PSNR não foram obtidos de uma codificação VVC e não constituem resultado experimental.

## Uso direto

```bash
python run_experiment.py \
  --controller static \
  --trace bandwidth_traces/stable.csv \
  --segment-manifest segment_manifests/example_segments.csv \
  --segments 4 \
  --output results/runs/manifest_example.csv
```

Para treinamento, comparação ou avaliação Q-Learning, use o mesmo argumento `--segment-manifest`. Em um protocolo JSON, adicione no nível raiz:

```json
{
  "segment_manifest": "segment_manifests/sequence_segments.csv"
}
```

O hash do próprio manifesto, sua sequência, escada e quantidade de segmentos são armazenados nos resumos, modelos e manifestos experimentais.
