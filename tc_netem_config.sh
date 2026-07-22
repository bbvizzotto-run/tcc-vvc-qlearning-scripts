#!/bin/bash

# Script para configurar o simulador de rede tc/netem no Linux.
# Este script permite simular condições de rede como atraso, perda de pacotes e limitação de largura de banda.

# Uso: ./tc_netem_config.sh <interface> [delay_ms] [loss_percent] [rate_kbit]
# Exemplo: ./tc_netem_config.sh eth0 100 1 10000
# Para remover as regras: ./tc_netem_config.sh <interface> --clear

INTERFACE=$1
DELAY=${2:-0} # Atraso em milissegundos (padrão: 0ms)
LOSS=${3:-0} # Perda de pacotes em porcentagem (padrão: 0%)
RATE=${4:-0} # Largura de banda em kbit/s (padrão: ilimitado)

if [ -z "$INTERFACE" ]; then
    echo "Uso: $0 <interface> [delay_ms] [loss_percent] [rate_kbit]"
    echo "       $0 <interface> --clear"
    exit 1
fi

if [ "$2" == "--clear" ]; then
    echo "Removendo todas as regras tc/netem da interface $INTERFACE..."
    sudo tc qdisc del dev $INTERFACE root
    echo "Regras removidas."
    exit 0
fi

# Limpa quaisquer regras existentes para evitar conflitos
sudo tc qdisc del dev $INTERFACE root 2>/dev/null

echo "Configurando tc/netem na interface $INTERFACE com:
  Atraso: ${DELAY}ms
  Perda: ${LOSS}%
  Taxa: ${RATE}kbit/s"

# Adiciona a disciplina de enfileiramento raiz (qdisc) com netem
COMMAND="sudo tc qdisc add dev $INTERFACE root handle 1: netem"

if [ "$DELAY" -gt 0 ]; then
    COMMAND="$COMMAND delay ${DELAY}ms"
fi

if [ "$LOSS" -gt 0 ]; then
    COMMAND="$COMMAND loss ${LOSS}%"
fi

# Para limitar a taxa, precisamos de um qdisc adicional (tbf)
if [ "$RATE" -gt 0 ]; then
    # Primeiro, aplica o netem ao tráfego de saída
    sudo tc qdisc add dev $INTERFACE root handle 1: netem \
        $( [ "$DELAY" -gt 0 ] && echo "delay ${DELAY}ms" ) \
        $( [ "$LOSS" -gt 0 ] && echo "loss ${LOSS}%" )
    
    # Em seguida, adiciona um qdisc tbf (Token Bucket Filter) para limitar a taxa
    # Isso é aplicado como um filho do netem, mas para simplificar, vamos aplicar diretamente ao root
    # Uma abordagem mais robusta seria usar HTB ou ingress qdisc para controle de taxa de entrada
    # Para este script, vamos aplicar a taxa de saída diretamente ao root, substituindo o netem se houver conflito
    echo "Aplicando limitação de taxa de ${RATE}kbit/s..."
    sudo tc qdisc add dev $INTERFACE handle 80: tbf rate ${RATE}kbit buffer 10kbit/8 peakrate ${RATE}kbit/8 mtu 1500
    sudo tc qdisc add dev $INTERFACE parent 80:1 handle 1: netem \
        $( [ "$DELAY" -gt 0 ] && echo "delay ${DELAY}ms" ) \
        $( [ "$LOSS" -gt 0 ] && echo "loss ${LOSS}%" )
    echo "Configuração de taxa aplicada. Note que a combinação de netem e tbf pode exigir ajustes dependendo do cenário."
else
    # Se não houver limitação de taxa, aplica o netem diretamente ao root
    $COMMAND
fi

echo "Configuração tc/netem aplicada com sucesso."

# Verifica a configuração
tc qdisc show dev $INTERFACE
