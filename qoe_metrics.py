
import numpy as np

def calculate_psnr(original_yuv, encoded_yuv, width, height):
    """
    Calcula o PSNR (Peak Signal-to-Noise Ratio) entre o vídeo original e o codificado.
    Nota: Esta é uma implementação simplificada para fins demonstrativos.
    Em um cenário real, o cálculo deve ser feito frame a frame para o componente Y.
    """
    # Carregar dados Y (simplificado)
    # mse = np.mean((original_y - encoded_y) ** 2)
    # if mse == 0: return 100
    # psnr = 20 * np.log10(255.0 / np.sqrt(mse))
    # return psnr
    pass

def calculate_rebuffering_rate(total_playback_time, total_stalling_time):
    """
    Calcula a taxa de rebuffering.
    """
    if total_playback_time == 0:
        return 0
    return (total_stalling_time / total_playback_time) * 100

def calculate_buffer_stability(buffer_occupancy_history):
    """
    Calcula a estabilidade do buffer (desvio padrão da ocupação).
    """
    if not buffer_occupancy_history:
        return 0
    return np.std(buffer_occupancy_history)

if __name__ == "__main__":
    # Exemplo de uso
    history = [10, 12, 11, 9, 8, 15, 20, 18, 12, 10]
    stability = calculate_buffer_stability(history)
    print(f"Estabilidade do Buffer (Desvio Padrão): {stability:.2f}")
    
    playback_time = 300 # segundos
    stalling_time = 5 # segundos
    rate = calculate_rebuffering_rate(playback_time, stalling_time)
    print(f"Taxa de Rebuffering: {rate:.2f}%")
