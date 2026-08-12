#!/usr/bin/env bash

# Compatibilidade para uma codificação VVC isolada. Para gerar toda a matriz
# segmento × representação e o manifesto, use generate_vvc_segments.py.

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Uso: $0 <input.yuv> <output.266> [bitrate_kbps] [resolução] [fps] [preset] [quadros]" >&2
    echo "Exemplo: $0 input.yuv output.266 2000 1920x1080 60/1 medium 120" >&2
    exit 1
fi

input_yuv=$1
output_vvc=$2
bitrate_kbps=${3:-2000}
resolution=${4:-1920x1080}
fps=${5:-60/1}
preset=${6:-medium}
frames=${7:-0}

if ! command -v vvencapp >/dev/null 2>&1; then
    echo "Erro: vvencapp não foi encontrado no PATH." >&2
    exit 1
fi
if [[ ! -f "$input_yuv" ]]; then
    echo "Erro: fonte YUV não encontrada: $input_yuv" >&2
    exit 1
fi
if [[ ! "$bitrate_kbps" =~ ^[1-9][0-9]*$ ]]; then
    echo "Erro: bitrate_kbps deve ser um inteiro positivo." >&2
    exit 1
fi
if [[ ! "$frames" =~ ^[0-9]+$ ]]; then
    echo "Erro: quadros deve ser um inteiro não negativo." >&2
    exit 1
fi

command=(
    vvencapp
    --input "$input_yuv"
    --size "$resolution"
    --fps "$fps"
    --format yuv420
    --internal-bitdepth 8
    --preset "$preset"
    --bitrate "$((bitrate_kbps * 1000))"
    --passes 2
    --qpa 1
    --refreshtype idr_no_radl
    --mtprofile 0
    --output "$output_vvc"
)
if [[ "$frames" -gt 0 ]]; then
    command+=(--frames "$frames")
fi

printf 'Executando:'
printf ' %q' "${command[@]}"
printf '\n'
"${command[@]}"
