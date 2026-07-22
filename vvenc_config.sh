#!/bin/bash

# Script para exemplificar o uso do codificador VVenC (Versatile Video Encoder).
# Este script demonstra como codificar um vídeo de entrada usando o padrão VVC com parâmetros básicos.

# Pré-requisitos:
# 1. VVenC deve estar instalado e acessível no PATH. Para instalar, siga as instruções em:
#    https://vvenc.fraunhofer.de/en/download.html ou compile a partir do código-fonte:
#    git clone https://github.com/fraunhoferhhi/vvenc.git
#    cd vvenc
#    mkdir build && cd build
#    cmake ..
#    make -j$(nproc)
#    sudo make install

# Uso: ./vvenc_config.sh <input_yuv_file> <output_vvc_file> [bitrate_kbps] [resolution] [preset]
# Exemplo: ./vvenc_config.sh input.yuv output.vvc 2000 1920x1080 fast

INPUT_YUV=$1
OUTPUT_VVC=$2
BITRATE=${3:-2000} # Bitrate em kbps (padrão: 2000 kbps)
RESOLUTION=${4:-1920x1080} # Resolução (ex: 1920x1080) (padrão: 1920x1080)
PRESET=${5:-medium} # Preset de codificação (ex: fast, medium, slow) (padrão: medium)

if [ -z "$INPUT_YUV" ] || [ -z "$OUTPUT_VVC" ]; then
    echo "Uso: $0 <input_yuv_file> <output_vvc_file> [bitrate_kbps] [resolution] [preset]"
    echo "Exemplo: $0 input.yuv output.vvc 2000 1920x1080 fast"
    exit 1
fi

echo "Iniciando codificação VVC com VVenC..."
echo "  Entrada: $INPUT_YUV"
echo "  Saída: $OUTPUT_VVC"
echo "  Bitrate: ${BITRATE} kbps"
echo "  Resolução: $RESOLUTION"
echo "  Preset: $PRESET"

# Extrai largura e altura da resolução
WIDTH=$(echo $RESOLUTION | cut -d'x' -f1)
HEIGHT=$(echo $RESOLUTION | cut -d'x' -f2)

# Comando VVenC
# Nota: Os parâmetros exatos podem variar dependendo da versão do VVenC e dos requisitos específicos.
# Consulte a documentação oficial do VVenC para uma lista completa de opções.

vvencapp -i $INPUT_YUV \
         --input-res ${WIDTH}x${HEIGHT} \
         --frames 100 \
         --preset $PRESET \
         --bitrate $BITRATE \
         -o $OUTPUT_VVC

# --frames 100 é um exemplo. Em um cenário real, você pode querer codificar o vídeo inteiro ou um número específico de frames.
# --input-chroma-format e --input-bit-depth podem ser necessários dependendo do seu arquivo YUV de entrada.

if [ $? -eq 0 ]; then
    echo "Codificação VVC concluída com sucesso!"
else
    echo "Erro durante a codificação VVC."
    exit 1
fi
