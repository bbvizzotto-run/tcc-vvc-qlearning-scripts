import numpy as np
import os

def calculate_psnr_yuv(original_yuv_path, encoded_yuv_path, width, height, num_frames, bit_depth=8):
    """
    Calcula o PSNR (Peak Signal-to-Noise Ratio) médio do componente de luminância (Y) 
    entre dois arquivos de vídeo YUV (formato 4:2:0 planar).
    
    Parâmetros:
    - original_yuv_path: Caminho para o arquivo YUV original.
    - encoded_yuv_path: Caminho para o arquivo YUV codificado/reconstruído.
    - width: Largura do frame em pixels.
    - height: Altura do frame em pixels.
    - num_frames: Número total de frames a serem analisados.
    - bit_depth: Profundidade de bits (padrão 8 bits).
    
    Retorna:
    - psnr_medio: O valor médio do PSNR em dB.
    """
    # Tamanho do componente Y em bytes por frame
    bytes_per_pixel = 1 if bit_depth <= 8 else 2
    y_size = width * height * bytes_per_pixel
    
    # Em YUV 4:2:0, os componentes U e V têm 1/4 do tamanho de Y cada
    frame_size = int(y_size * 1.5)
    
    max_pixel_value = (1 << bit_depth) - 1
    psnr_total = 0.0
    frames_processados = 0

    try:
        with open(original_yuv_path, 'rb') as f_orig, open(encoded_yuv_path, 'rb') as f_enc:
            for frame_idx in range(num_frames):
                # Lê apenas o componente Y (luminância) do frame atual
                y_orig_bytes = f_orig.read(y_size)
                y_enc_bytes = f_enc.read(y_size)
                
                if not y_orig_bytes or not y_enc_bytes:
                    break # Fim do arquivo
                
                # Pula os componentes U e V para avançar ao próximo frame
                f_orig.seek(frame_size - y_size, os.SEEK_CUR)
                f_enc.seek(frame_size - y_size, os.SEEK_CUR)
                
                # Converte bytes para array numpy
                dtype = np.uint8 if bit_depth <= 8 else np.uint16
                y_orig = np.frombuffer(y_orig_bytes, dtype=dtype).astype(np.float64)
                y_enc = np.frombuffer(y_enc_bytes, dtype=dtype).astype(np.float64)
                
                # Calcula o Erro Quadrático Médio (MSE)
                mse = np.mean((y_orig - y_enc) ** 2)
                
                if mse == 0:
                    # Se MSE for 0, os frames são idênticos. PSNR tende ao infinito.
                    psnr = 100.0 
                else:
                    psnr = 10 * np.log10((max_pixel_value ** 2) / mse)
                
                psnr_total += psnr
                frames_processados += 1
                
    except FileNotFoundError as e:
        print(f"Erro: Arquivo não encontrado. {e}")
        return None

    if frames_processados == 0:
        print("Erro: Nenhum frame foi processado.")
        return None

    psnr_medio = psnr_total / frames_processados
    return psnr_medio

def calculate_rebuffering_rate(total_playback_time, total_stalling_time):
    """
    Calcula a taxa de rebuffering.
    
    Parâmetros:
    - total_playback_time: Tempo total de reprodução do vídeo (em segundos).
    - total_stalling_time: Tempo total em que o vídeo ficou travado carregando (em segundos).
    
    Retorna:
    - Taxa de rebuffering em porcentagem.
    """
    if total_playback_time == 0:
        return 0.0
    return (total_stalling_time / total_playback_time) * 100.0

def calculate_buffer_stability(buffer_occupancy_history):
    """
    Calcula a estabilidade do buffer com base no desvio padrão da ocupação.
    
    Parâmetros:
    - buffer_occupancy_history: Lista ou array com os registros de ocupação do buffer ao longo do tempo.
    
    Retorna:
    - O desvio padrão da ocupação do buffer. Valores menores indicam maior estabilidade.
    """
    if not buffer_occupancy_history:
        return 0.0
    return np.std(buffer_occupancy_history)

if __name__ == "__main__":
    # Exemplo de uso das métricas
    
    # 1. Estabilidade do Buffer
    history = [10, 12, 11, 9, 8, 15, 20, 18, 12, 10]
    stability = calculate_buffer_stability(history)
    print(f"Estabilidade do Buffer (Desvio Padrão): {stability:.2f}")
    
    # 2. Taxa de Rebuffering
    playback_time = 300 # segundos
    stalling_time = 5 # segundos
    rate = calculate_rebuffering_rate(playback_time, stalling_time)
    print(f"Taxa de Rebuffering: {rate:.2f}%")
    
    # 3. PSNR (Exemplo de chamada - requer arquivos YUV reais para funcionar)
    # psnr_value = calculate_psnr_yuv("video_original.yuv", "video_codificado.yuv", 1920, 1080, 300)
    # if psnr_value:
    #     print(f"PSNR Médio (Y): {psnr_value:.2f} dB")
